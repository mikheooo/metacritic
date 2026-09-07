from app.workers.tasks import ping


def test_celery_diagnostic_ping() -> None:
    """Verify Celery diagnostic ping task directly."""
    result = ping()
    assert result == "pong"
