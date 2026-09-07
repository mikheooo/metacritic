from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PipelineStage(StrEnum):
    QUEUED = "queued"
    DISCOVERING = "discovering"
    INGESTING = "ingesting"
    REVIEWS = "reviews"
    SUMMARIZING = "summarizing"
    EMBEDDING = "embedding"
    YOUTUBE = "youtube"
    SIMILARITY = "similarity"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class CrawlRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class CrawlRunEventRead(BaseModel):
    id: int
    crawl_run_id: int
    event_type: str
    stage: str
    game_id: int | None = None
    message: str
    payload: dict[str, Any] | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CrawlRunRead(BaseModel):
    id: int
    task_id: str | None = None
    status: str
    trigger_type: str
    target_count: int
    discovered_count: int
    processed_count: int
    failed_count: int
    reviews_processed_count: int
    summaries_generated_count: int
    embeddings_generated_count: int
    youtube_processed_count: int = 0
    current_stage: str | None = None
    current_game_id: int | None = None
    current_game_title: str | None = None
    started_at: datetime | None = None
    heartbeat_at: datetime | None = None
    finished_at: datetime | None = None
    error_summary: str | None = None
    created_at: datetime
    events: list[CrawlRunEventRead] = []

    model_config = ConfigDict(from_attributes=True)


class SchedulerStatus(BaseModel):
    enabled: bool
    timezone: str
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None


class WorkerStatus(BaseModel):
    online: bool
    workers: list[str] = Field(default_factory=list)


class MonitorStatusResponse(BaseModel):
    scheduler: SchedulerStatus
    worker: WorkerStatus
    active_run: CrawlRunRead | None = None
    last_run: CrawlRunRead | None = None


class RunNowRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=20)


class RunNowResponse(BaseModel):
    run_id: int
    task_id: str | None = None
    status: str
    trigger_type: str
