import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.ping")
def ping() -> str:
    """
    Diagnostic Celery task verifying broker and worker connectivity.
    """
    logger.info("Executing diagnostic ping task")
    return "pong"
