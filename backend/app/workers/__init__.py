from app.workers.celery_app import celery_app
from app.workers.tasks import ping

__all__ = ["celery_app", "ping"]
