from pydantic import BaseModel, ConfigDict


class YouTubeTranscriptMetadataRead(BaseModel):
    language: str
    is_generated: bool
    provider: str

    model_config = ConfigDict(from_attributes=True)


class YouTubeSummaryRead(BaseModel):
    text: str
    key_points: list[str]
    provider: str
    model: str
    prompt_version: str

    model_config = ConfigDict(from_attributes=True)


class YouTubeLetsPlayRead(BaseModel):
    youtube_video_id: str
    title: str
    channel_title: str | None = None
    url: str
    thumbnail_url: str | None = None
    view_count: int | None = None
    duration_seconds: int | None = None
    status: str
    selection_rank: int = 1
    selection_reason: str

    transcript: YouTubeTranscriptMetadataRead | None = None
    summary: YouTubeSummaryRead | None = None

    model_config = ConfigDict(from_attributes=True)
