from celery.schedules import crontab

from app.workers.celery_app import celery_app


def test_celery_beat_schedule_contains_metacritic_pipeline() -> None:
    """
    Verify Celery Beat schedule configuration:
    - Metacritic pipeline is registered
    - Schedule is hourly (minute=0, hour="*")
    - Production batch limit is 20
    - Trigger type is 'scheduled'
    - Timezone is UTC
    """
    schedule = celery_app.conf.beat_schedule
    assert "metacritic-pipeline-hourly" in schedule, (
        "Hourly Metacritic pipeline missing from beat_schedule"
    )

    entry = schedule["metacritic-pipeline-hourly"]
    assert entry["task"] == "tasks.process_metacritic_pipeline"
    assert entry["kwargs"] == {"limit": 20, "trigger_type": "scheduled"}

    cron = entry["schedule"]
    assert isinstance(cron, crontab)
    # Check that crontab fires once per hour at minute 0
    assert 0 in cron.minute
    assert len(cron.minute) == 1
    assert cron.hour == set(range(24))

    # Timezone verification
    assert celery_app.conf.timezone == "UTC"
    assert celery_app.conf.enable_utc is True
