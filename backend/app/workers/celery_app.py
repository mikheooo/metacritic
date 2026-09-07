"""
Celery Application and Beat Scheduler configuration.

IMPORTANT:
Only one Beat scheduler must run for this schedule.
Additional backend/worker replicas must not run Celery Beat to avoid duplicate task dispatches.
"""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "metacritic_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.tasks"],
)

beat_schedule = {}
if settings.CRAWL_SCHEDULE_ENABLED:
    beat_schedule["metacritic-pipeline-hourly"] = {
        "task": "tasks.process_metacritic_pipeline",
        "schedule": crontab(minute=settings.CRAWL_SCHEDULE_MINUTE, hour="*"),
        "kwargs": {
            "limit": settings.CRAWL_BATCH_LIMIT,
            "trigger_type": "scheduled",
        },
    }

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.CELERY_TIMEZONE,
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,
    broker_connection_retry_on_startup=True,
    beat_schedule=beat_schedule,
)
