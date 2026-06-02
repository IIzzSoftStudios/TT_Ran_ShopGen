"""Celery task: run N simulation ticks for a campaign as one atomic batch.

ACID model
----------
A "Year" run advances the campaign by 365 game days. Earlier versions
committed after each tick, which left the world partially advanced if the
worker died at tick 200 — a rerun then continued from the midpoint instead
of replaying the failed batch cleanly. The current model holds **one**
database transaction across the whole period and commits only after the
final tick succeeds. On any failure the entire batch (campaign state, sim
state, GMWorldState writes, **and** PriceHistory rows) rolls back together,
so a failed run leaves the world byte-for-byte where it started and the GM
can simply rerun.

Lock policy
-----------
Concurrency is enforced with the per-campaign Redis lock
``lock:sim:{campaign_id}``. The initial TTL is sized for the worst-case
period plus margin (``SIMULATION_LOCK_TTL_SECONDS``); the task also calls
``lock.refresh()`` between ticks (cadence ``SIMULATION_LOCK_REFRESH_SECONDS``)
so a long Year cannot expire the key mid-batch and let a second worker
acquire it. If a refresh discovers the lock was stolen — possible only on
extreme clock skew or operator intervention — the task aborts the
transaction and reports a ``failed`` job rather than continuing on stolen
authority.

Progress shape
--------------
Progress is written to Redis at ``sim_job:{task_id}`` so the polling UI can
read state without involving the DB. The status field follows a strict
contract; see :func:`SimJobStatus` for values. All Redis writes go through
``_safe_*`` helpers so a transient Redis outage degrades to a job-level
error rather than entering Celery's retry machinery.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Dict

from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError

from celery_app import celery
from app.extensions import db
from app.services.distributed_lock import (
    acquire_simulation_lock,
    get_redis_client,
)
from app.services.sim_metrics import (
    record_job_finished,
    record_job_rejected,
    record_job_started,
)
from app.models import Campaign
from app.services.market_overview import (
    aggregate_item_metrics,
    parse_start_metrics_json,
    persist_last_market_run_snapshot,
    start_metrics_json,
)
from app.services.simulation import SimulationEngine
from app.utils.safe_errors import public_error_message

logger = logging.getLogger(__name__)

TICKS_MAP: Dict[str, int] = {"day": 1, "week": 7, "month": 30, "year": 365}


def simulation_pause_key(campaign_id: int) -> str:
    return f"sim_pause:{int(campaign_id)}"


def _pause_requested(redis_client, campaign_id: int) -> bool:
    value = redis_client.get(simulation_pause_key(campaign_id))
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="ignore")
    return str(value).lower() in {"1", "true", "yes", "pause"}


# Job status contract (single source of truth for the polling UI).
# See deploy/README.md for the UX implications of each terminal state.
class SimJobStatus:
    QUEUED = "queued"          # accepted by the worker, lock not yet held
    RUNNING = "running"        # actively executing ticks under the lock
    SUCCESS = "success"        # all ticks committed
    BUSY = "busy"              # another batch is already running for this campaign
    ERROR = "error"            # batch rolled back; world is unchanged from start
    LOCK_LOST = "lock_lost"    # the campaign lock was stolen mid-batch; batch rolled back
    PAUSED = "paused"          # GM requested a stop; completed ticks were committed


@celery.task(bind=True)
def run_period_task(self, campaign_id: int, period: str) -> dict:
    """Run an ACID simulation batch for a campaign for the given period."""
    redis_client = get_redis_client()
    job_id = self.request.id
    job_key = f"sim_job:{job_id}"

    def _safe_hset(mapping: dict) -> bool:
        try:
            redis_client.hset(job_key, mapping=mapping)
            return True
        except (RedisConnectionError, RedisTimeoutError):
            return False

    def _safe_expire(ttl_seconds: int) -> bool:
        try:
            redis_client.expire(job_key, ttl_seconds)
            return True
        except (RedisConnectionError, RedisTimeoutError):
            return False

    ticks_total = TICKS_MAP.get(period)
    if ticks_total is None:
        _safe_hset(
            {
                "status": SimJobStatus.ERROR,
                "error": f"Invalid period: {period}",
                "ticks_done": 0,
                "ticks_total": 0,
            }
        )
        return {"status": SimJobStatus.ERROR, "error": f"Invalid period: {period}"}

    if not _safe_hset(
        {
            "status": SimJobStatus.QUEUED,
            "ticks_done": 0,
            "ticks_total": ticks_total,
            "campaign_id": int(campaign_id),
            "period": period,
        }
    ):
        return {
            "status": SimJobStatus.ERROR,
            "error": "Redis unavailable while initializing simulation job state",
        }
    _safe_expire(int(os.getenv("SIM_JOB_TTL_SECONDS", "86400")))

    # Lock TTL must exceed the worst-case period runtime; refresh runs between
    # ticks to keep the key alive without a separate heartbeat thread. Default
    # 7200s = 2h matches the worker --time-limit; tighten with profiling data.
    lock_ttl_seconds = int(os.getenv("SIMULATION_LOCK_TTL_SECONDS", "7200"))
    refresh_seconds = int(os.getenv("SIMULATION_LOCK_REFRESH_SECONDS", "60"))

    try:
        lock = acquire_simulation_lock(
            int(campaign_id), ttl_seconds=lock_ttl_seconds, blocking=False
        )
    except (RedisConnectionError, RedisTimeoutError):
        _safe_hset(
            {
                "status": SimJobStatus.ERROR,
                "error": "Redis unavailable while acquiring simulation lock",
            }
        )
        return {
            "status": SimJobStatus.ERROR,
            "error": "Redis unavailable while acquiring simulation lock",
        }

    if lock is None:
        _safe_hset(
            {"status": SimJobStatus.BUSY, "error": "Simulation already running"}
        )
        # Use record_job_rejected (terminal-only) here — no record_job_started
        # has run, so calling record_job_finished would decrement the
        # in-flight gauge without a paired increment and drift it negative.
        record_job_rejected(period, SimJobStatus.BUSY)
        return {
            "status": SimJobStatus.BUSY,
            "error": "Simulation already running",
        }

    started_at = record_job_started(job_id, period)
    last_refresh = time.monotonic()
    final_game_day = None
    terminal_status = SimJobStatus.ERROR
    try:
        from app import app as flask_app

        with flask_app.app_context():
            campaign_row = Campaign.query.get(int(campaign_id))
            game_day_start = (
                int(campaign_row.current_game_day)
                if campaign_row and campaign_row.current_game_day is not None
                else 0
            )
            start_metrics = parse_start_metrics_json(
                redis_client.hget(job_key, "start_metrics_json")
            )
            if start_metrics is None:
                start_metrics = aggregate_item_metrics(
                    int(campaign_id), in_stock_only=True
                )
                _safe_hset({"start_metrics_json": start_metrics_json(start_metrics)})

            engine = SimulationEngine()
            units_sold_total = 0
            shops_restocked_total = 0
            ticks_done = 0
            pause_requested = False
            try:
                for i in range(1, ticks_total + 1):
                    if _pause_requested(redis_client, int(campaign_id)):
                        pause_requested = True
                        break

                    # Refresh the lock between ticks so a multi-hour batch
                    # cannot expire the key while we still own it.
                    now = time.monotonic()
                    if now - last_refresh >= refresh_seconds:
                        if not lock.refresh():
                            raise _LockStolen(
                                f"Lost simulation lock at tick {i}/{ticks_total}"
                            )
                        last_refresh = now

                    stats = engine.run_tick(
                        campaign_id=int(campaign_id), flush_only=True
                    )
                    units_sold_total += int(stats.get("units_sold") or 0)
                    shops_restocked_total += int(stats.get("shops_restocked") or 0)
                    final_game_day = stats.get("current_game_day")
                    ticks_done = i

                    if not _safe_hset(
                        {
                            "status": SimJobStatus.RUNNING,
                            "ticks_done": i,
                            "ticks_total": ticks_total,
                            "current_game_day": final_game_day,
                        }
                    ):
                        raise _RedisProgressFailure(
                            "Redis unavailable while writing simulation progress"
                        )

                if pause_requested and ticks_done == 0:
                    db.session.rollback()
                else:
                    # All completed ticks are flushed; commit them together.
                    db.session.commit()
                    # Expire ORM cache so subsequent reads on the same context
                    # see the committed state.
                    db.session.expire_all()
            except Exception:
                # Single rollback unwinds every tick + every PriceHistory row.
                # The campaign is restored to its pre-batch state and the GM
                # can rerun without an off-by-N midpoint.
                db.session.rollback()
                raise

            if pause_requested and ticks_done == 0:
                _safe_hset(
                    {
                        "status": SimJobStatus.PAUSED,
                        "ticks_done": 0,
                        "ticks_total": ticks_total,
                        "current_game_day": game_day_start,
                        "units_sold_total": 0,
                        "shops_restocked_total": 0,
                        "world_changed": "false",
                    }
                )
                terminal_status = SimJobStatus.PAUSED
                return {
                    "status": SimJobStatus.PAUSED,
                    "current_game_day": game_day_start,
                    "ticks_done": 0,
                    "ticks_total": ticks_total,
                    "units_sold_total": 0,
                    "shops_restocked_total": 0,
                }

            game_day_end = final_game_day
            if game_day_end is None and campaign_row is not None:
                db.session.refresh(campaign_row)
                game_day_end = campaign_row.current_game_day
            try:
                end_metrics = aggregate_item_metrics(
                    int(campaign_id), in_stock_only=True
                )
                persist_last_market_run_snapshot(
                    int(campaign_id),
                    period,
                    game_day_start,
                    int(game_day_end or game_day_start),
                    start_metrics,
                    end_metrics,
                )
            except Exception as snap_exc:
                # Ticks are already committed; rollback only clears the failed
                # snapshot write. Do not report SUCCESS — the UI must surface
                # that market deltas were not recorded for this run.
                db.session.rollback()
                logger.exception(
                    "Failed to persist last_market_run snapshot for campaign %s",
                    campaign_id,
                )
                snap_msg = public_error_message(
                    snap_exc,
                    audience="redis_job",
                ) or (
                    "Simulation finished but the market overview snapshot could "
                    "not be saved. The world was updated; check server logs."
                )
                _safe_hset(
                    {
                        "status": SimJobStatus.ERROR,
                        "ticks_done": ticks_done,
                        "ticks_total": ticks_total,
                        "current_game_day": final_game_day,
                        "error": snap_msg,
                        "world_changed": "true",
                    }
                )
                terminal_status = SimJobStatus.ERROR
                return {
                    "status": SimJobStatus.ERROR,
                    "error": snap_msg,
                    "current_game_day": final_game_day,
                }

            final_status = SimJobStatus.PAUSED if pause_requested else SimJobStatus.SUCCESS
            _safe_hset(
                {
                    "status": final_status,
                    "ticks_done": ticks_done,
                    "ticks_total": ticks_total,
                    "current_game_day": final_game_day,
                    "units_sold_total": units_sold_total,
                    "shops_restocked_total": shops_restocked_total,
                    "world_changed": "true",
                }
            )
            terminal_status = final_status
            return {
                "status": final_status,
                "current_game_day": final_game_day,
                "ticks_done": ticks_done,
                "ticks_total": ticks_total,
                "units_sold_total": units_sold_total,
                "shops_restocked_total": shops_restocked_total,
            }
    except _LockStolen as exc:
        logger.error("Simulation lock lost mid-batch: %s", exc)
        lock_msg = "Simulation was interrupted. You can try running it again."
        _safe_hset({"status": SimJobStatus.LOCK_LOST, "error": lock_msg})
        terminal_status = SimJobStatus.LOCK_LOST
        return {"status": SimJobStatus.LOCK_LOST, "error": lock_msg}
    except _RedisProgressFailure as exc:
        _safe_hset({"status": SimJobStatus.ERROR, "error": str(exc)})
        terminal_status = SimJobStatus.ERROR
        return {"status": SimJobStatus.ERROR, "error": str(exc)}
    except (RedisConnectionError, RedisTimeoutError):
        _safe_hset(
            {
                "status": SimJobStatus.ERROR,
                "error": "Redis unavailable during simulation execution",
            }
        )
        terminal_status = SimJobStatus.ERROR
        return {
            "status": SimJobStatus.ERROR,
            "error": "Redis unavailable during simulation execution",
        }
    except Exception as e:
        logger.exception("Simulation batch failed; transaction rolled back")
        safe = public_error_message(e, audience="redis_job")
        _safe_hset({"status": SimJobStatus.ERROR, "error": safe})
        terminal_status = SimJobStatus.ERROR
        return {"status": SimJobStatus.ERROR, "error": safe}
    finally:
        try:
            redis_client.delete(simulation_pause_key(campaign_id))
        except Exception:
            pass
        try:
            lock.release()
        except Exception:
            pass
        record_job_finished(job_id, period, terminal_status, started_at)


class _LockStolen(RuntimeError):
    """Internal — raised when lock.refresh() finds the token has been overwritten."""


class _RedisProgressFailure(RuntimeError):
    """Internal — raised when sim_job HSET fails so the outer except can roll back."""
