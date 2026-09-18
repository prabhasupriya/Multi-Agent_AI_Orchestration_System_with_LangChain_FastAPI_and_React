"""
Celery application factory.

This is imported by BOTH the FastAPI process (so it can `.delay()` tasks)
and the standalone Celery worker process (so it can register/consume tasks).
Using Redis as broker AND result backend lets the FastAPI event loop poll
for a tool's result without blocking on the tool's actual execution.
"""
from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "multi_agent_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
)
