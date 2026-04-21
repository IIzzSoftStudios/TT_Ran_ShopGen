import os
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

# Celery instance used by task modules.
celery = Celery(
    "TT_Ran_ShopGen",
    broker=celery_broker_url,
    backend=celery_result_backend,
    include=["app.tasks.simulation_tasks"],
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Keep scheduling fair when many long-running tasks exist.
    worker_prefetch_multiplier=1,
)

