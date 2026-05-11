"""Lightweight Celery / simulation telemetry backed by Redis.

The Alpha goal is to replace "unknown concurrent load" with concrete numbers
(todo ``alpha-metrics-queue``):

* concurrent batches in flight (``running``)
* depth of the Celery broker queue (``queued``)
* recent batch durations for p50/p95/p99 (``recent_durations``)
* terminal-status counts over the last rolling window
  (``terminal_counts``) — feeds the "Hard No" decision in
  ``alpha-year-hard-no`` once SLOs are defined.

Everything lives in Redis to avoid pulling in a Prometheus exporter for a
solo-ops deployment. Helpers are crash-safe: a transient Redis blip causes
metric loss, never a job-execution error.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

from redis.exceptions import RedisError

from app.services.distributed_lock import get_redis_client

logger = logging.getLogger(__name__)

# Keys (single keyspace prefix so an operator can `KEYS metrics:sim:*`).
_RUNNING_KEY = "metrics:sim:running"            # INCR / DECR
_DURATIONS_KEY = "metrics:sim:durations"        # capped LIST of recent seconds
_TERMINAL_KEY = "metrics:sim:terminal:{status}" # INCR per terminal status
_BROKER_QUEUE = "celery"                        # Default Celery list name

_DURATIONS_CAP = int(os.getenv("METRICS_DURATIONS_CAP", "256"))
_TERMINAL_TTL_SECONDS = int(os.getenv("METRICS_TERMINAL_TTL_SECONDS", "86400"))


def _safe(fn, *args, **kwargs):
    """Best-effort Redis wrapper — never raise."""
    try:
        return fn(*args, **kwargs)
    except RedisError as exc:
        logger.warning("sim_metrics: %s failed: %s", fn.__name__, exc)
        return None


def record_job_started(job_id: str, period: str) -> float:
    """Increment in-flight count, return the start timestamp the caller stores.

    Must be paired with exactly one ``record_job_finished`` call. For paths
    that reject a job before any work runs (e.g. a busy lock), use
    :func:`record_job_rejected` instead so the in-flight gauge does not
    drift negative.
    """
    client = get_redis_client()
    started_at = time.monotonic()
    _safe(client.incr, _RUNNING_KEY)
    return started_at


def record_job_finished(
    job_id: str,
    period: str,
    status: str,
    started_at: float,
) -> None:
    """Decrement in-flight, push duration sample, bump terminal counter.

    Strict pair of :func:`record_job_started` — call exactly once per call to
    ``record_job_started`` and only with the ``started_at`` value it returned.
    """
    client = get_redis_client()
    _safe(client.decr, _RUNNING_KEY)

    duration = max(0.0, time.monotonic() - started_at)
    # Cap the rolling list in one round trip via LPUSH + LTRIM.
    try:
        pipe = client.pipeline(transaction=False)
        pipe.lpush(_DURATIONS_KEY, f"{period}:{status}:{duration:.3f}")
        pipe.ltrim(_DURATIONS_KEY, 0, _DURATIONS_CAP - 1)
        pipe.execute()
    except RedisError as exc:
        logger.warning("sim_metrics: durations push failed: %s", exc)

    _bump_terminal(client, status)


def record_job_rejected(period: str, status: str) -> None:
    """Bump terminal counter only — for jobs rejected before any work ran.

    Use this on paths where ``record_job_started`` was NOT called (e.g. a
    busy per-campaign lock, an invalid period). It deliberately does not
    touch the in-flight gauge so the running counter stays consistent with
    actually-running batches.
    """
    client = get_redis_client()
    _bump_terminal(client, status)


def _bump_terminal(client, status: str) -> None:
    terminal_key = _TERMINAL_KEY.format(status=status)
    _safe(client.incr, terminal_key)
    _safe(client.expire, terminal_key, _TERMINAL_TTL_SECONDS)


def _percentile(samples: list[float], q: float) -> Optional[float]:
    if not samples:
        return None
    samples = sorted(samples)
    idx = max(0, min(len(samples) - 1, int(round(q * (len(samples) - 1)))))
    return samples[idx]


def snapshot() -> Dict[str, Any]:
    """Return a JSON-serializable view of the current simulation metrics."""
    client = get_redis_client()
    running = _safe(client.get, _RUNNING_KEY)
    queue_depth = _safe(client.llen, _BROKER_QUEUE)
    raw_durations = _safe(client.lrange, _DURATIONS_KEY, 0, -1) or []

    durations: list[float] = []
    by_period: Dict[str, list[float]] = {}
    for entry in raw_durations:
        try:
            period, _status, dur = entry.split(":", 2)
            d = float(dur)
        except (ValueError, AttributeError):
            continue
        durations.append(d)
        by_period.setdefault(period, []).append(d)

    terminal_counts: Dict[str, int] = {}
    for status in ("success", "error", "lock_lost", "busy"):
        val = _safe(client.get, _TERMINAL_KEY.format(status=status))
        terminal_counts[status] = int(val) if val else 0

    return {
        "running": int(running) if running else 0,
        "queue_depth": int(queue_depth) if queue_depth else 0,
        "samples": len(durations),
        "durations_seconds": {
            "p50": _percentile(durations, 0.50),
            "p95": _percentile(durations, 0.95),
            "p99": _percentile(durations, 0.99),
            "by_period": {
                period: {
                    "samples": len(values),
                    "p50": _percentile(values, 0.50),
                    "p95": _percentile(values, 0.95),
                    "p99": _percentile(values, 0.99),
                }
                for period, values in by_period.items()
            },
        },
        "terminal_counts": terminal_counts,
    }
