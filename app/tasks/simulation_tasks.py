import os
from typing import Dict

from celery_app import celery
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError

from app.extensions import db
from app.services.distributed_lock import acquire_simulation_lock, get_redis_client
from app.services.simulation import SimulationEngine


TICKS_MAP: Dict[str, int] = {"day": 1, "week": 7, "month": 30, "year": 365}


@celery.task(bind=True)
def run_period_task(self, gm_profile_id: int, period: str) -> dict:
    """
    Run simulation for a GM for the given period.

    Progress is written to Redis under `sim_job:{task_id}` for the polling UI.
    Concurrency is enforced with a per-GM distributed lock `lock:sim:{gm_profile_id}`.
    """
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
                "status": "error",
                "error": f"Invalid period: {period}",
                "ticks_done": 0,
                "ticks_total": 0,
            }
        )
        return {"status": "error", "error": f"Invalid period: {period}"}

    if not _safe_hset(
        {
            "status": "queued",
            "ticks_done": 0,
            "ticks_total": ticks_total,
        }
    ):
        return {
            "status": "error",
            "error": "Redis unavailable while initializing simulation job state",
        }
    _safe_expire(int(os.getenv("SIM_JOB_TTL_SECONDS", "86400")))

    lock_ttl_seconds = int(os.getenv("SIMULATION_LOCK_TTL_SECONDS", "300"))
    try:
        lock = acquire_simulation_lock(
            int(gm_profile_id), ttl_seconds=lock_ttl_seconds, blocking=False
        )
    except (RedisConnectionError, RedisTimeoutError):
        _safe_hset(
            {"status": "error", "error": "Redis unavailable while acquiring simulation lock"}
        )
        return {
            "status": "error",
            "error": "Redis unavailable while acquiring simulation lock",
        }

    if lock is None:
        _safe_hset({"status": "busy", "error": "Simulation already running"})
        return {"status": "busy", "error": "Simulation already running"}

    stats = None
    try:
        from app import app as flask_app

        with flask_app.app_context():
            engine = SimulationEngine()
            for i in range(1, ticks_total + 1):
                stats = engine.run_tick(int(gm_profile_id), commit=True)
                db.session.expire_all()
                if not _safe_hset(
                    {
                        "status": "running",
                        "ticks_done": i,
                        "ticks_total": ticks_total,
                        "current_game_day": stats.get("current_game_day"),
                    }
                ):
                    return {
                        "status": "error",
                        "error": "Redis unavailable while writing simulation progress",
                    }

            if not _safe_hset(
                {
                    "status": "success",
                    "ticks_done": ticks_total,
                    "ticks_total": ticks_total,
                    "current_game_day": stats.get("current_game_day") if stats else None,
                }
            ):
                return {
                    "status": "error",
                    "error": "Redis unavailable while finalizing simulation job",
                }
            return {
                "status": "success",
                "current_game_day": stats.get("current_game_day") if stats else None,
            }
    except (RedisConnectionError, RedisTimeoutError):
        _safe_hset(
            {"status": "error", "error": "Redis unavailable during simulation execution"}
        )
        return {
            "status": "error",
            "error": "Redis unavailable during simulation execution",
        }
    except Exception as e:
        _safe_hset({"status": "error", "error": str(e)})
        return {"status": "error", "error": str(e)}
    finally:
        try:
            lock.release()
        except Exception:
            pass
