"""Celery application factory.

Loaded by the worker via `celery -A celery_app.celery worker ...` and by Flask
task callers via `from celery_app import celery`. Broker / backend resolve from
`REDIS_URL` (single canonical value) with optional `CELERY_BROKER_URL` and
`CELERY_RESULT_BACKEND` overrides for environments that split them.
"""

import os
import sys
from pathlib import Path

from celery import Celery
from dotenv import load_dotenv

# Same DB as Flask: load config.env from project root so workers see SQLALCHEMY_DATABASE_URI
# when started outside Docker. Does not override variables already set (e.g. docker-compose).
load_dotenv(Path(__file__).resolve().parent / "config.env")


def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    return v if v else default


REDIS_URL_DEFAULT = "redis://localhost:6379/0"

redis_url = _env("REDIS_URL", REDIS_URL_DEFAULT)
celery_broker_url = _env("CELERY_BROKER_URL", redis_url)
celery_result_backend = _env("CELERY_RESULT_BACKEND", redis_url)

celery = Celery(
    "TT_Ran_ShopGen",
    broker=celery_broker_url,
    backend=celery_result_backend,
    include=["app.tasks.simulation_tasks"],
)

_conf = {
    "task_serializer": "json",
    "accept_content": ["json"],
    "result_serializer": "json",
    "timezone": "UTC",
    "enable_utc": True,
    "worker_prefetch_multiplier": 1,
}

# Celery 5's default prefork pool relies on fork semantics that fail on Windows
# (fast_trace_task: "not enough values to unpack (expected 3, got 0)").
# Solo is fine for local dev (one simulation batch at a time). Linux/Docker
# production still uses prefork unless CELERY_WORKER_POOL is set.
if sys.platform == "win32":
    _conf["worker_pool"] = os.getenv("CELERY_WORKER_POOL", "solo")
elif os.getenv("CELERY_WORKER_POOL"):
    _conf["worker_pool"] = os.environ["CELERY_WORKER_POOL"]

celery.conf.update(**_conf)
