import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TranscriptResult:
    text: str
    language: str
    is_generated: bool
    provider: str
    segment_count: int


class TranscriptError(Exception):
    """Base exception for transcript operations."""


class TranscriptUnavailableError(TranscriptError):
    """Raised when no accessible transcript exists for a given video."""


class TranscriptProvider(Protocol):
    """Contract for retrieving blogger speech transcripts."""

    provider: str

    async def fetch_transcript(
        self,
        video_id: str,
        preferred_languages: list[str] | None = None,
    ) -> TranscriptResult: ...


class YouTubeTranscriptApiProvider:
    """
    Production transcript provider utilizing youtube-transcript-api.
    Safely retrieves manual or auto-generated captions with language fallback.
    """

    provider: str = "youtube-transcript-api"

    def __init__(self, preferred_languages: list[str] | None = None) -> None:
        self.preferred_languages = preferred_languages or settings.YOUTUBE_TRANSCRIPT_LANGUAGES

    def _sync_fetch(self, video_id: str, pref_langs: list[str]) -> TranscriptResult:
        try:
            from youtube_transcript_api import (
                CouldNotRetrieveTranscript,
                NoTranscriptFound,
                TranscriptsDisabled,
                VideoUnavailable,
                YouTubeTranscriptApi,
            )
        except ImportError as exc:
            raise TranscriptError(
                "youtube-transcript-api library is not installed in the environment"
            ) from exc

        try:
            api: Any = YouTubeTranscriptApi()
            if hasattr(api, "list"):
                transcript_list = api.list(video_id)
            else:
                transcript_list = api.list_transcripts(video_id)
        except (
            TranscriptsDisabled,
            NoTranscriptFound,
            VideoUnavailable,
            CouldNotRetrieveTranscript,
        ) as exc:
            logger.info("Transcript unavailable for video %s: %s", video_id, exc)
            raise TranscriptUnavailableError(
                f"Transcript not available for YouTube video '{video_id}': {exc}"
            ) from exc
        except Exception as exc:
            logger.warning("Unexpected error listing transcripts for %s: %s", video_id, exc)
            raise TranscriptUnavailableError(
                f"Failed to retrieve transcripts for video '{video_id}': {exc}"
            ) from exc

        all_transcripts: list[Any] = list(transcript_list)
        if not all_transcripts:
            raise TranscriptUnavailableError(f"No transcripts found for YouTube video '{video_id}'")

        manual_transcripts = [t for t in all_transcripts if not getattr(t, "is_generated", False)]
        generated_transcripts = [t for t in all_transcripts if getattr(t, "is_generated", False)]

        selected_transcript: Any = None

        # Priority 1: Manual transcript in preferred languages
        for lang in pref_langs:
            for t in manual_transcripts:
                if getattr(t, "language_code", "") == lang:
                    selected_transcript = t
                    break
            if selected_transcript:
                break

        # Priority 2: Auto-generated transcript in preferred languages
        if not selected_transcript:
            for lang in pref_langs:
                for t in generated_transcripts:
                    if getattr(t, "language_code", "") == lang:
                        selected_transcript = t
                        break
                if selected_transcript:
                    break

        # Priority 3: Any manual transcript
        if not selected_transcript and manual_transcripts:
            selected_transcript = manual_transcripts[0]

        # Priority 4: Any generated transcript
        if not selected_transcript and generated_transcripts:
            selected_transcript = generated_transcripts[0]

        if not selected_transcript:
            raise TranscriptUnavailableError(
                f"No suitable transcript could be selected for video '{video_id}'"
            )

        try:
            segments_obj = selected_transcript.fetch()
            raw_segments: list[Any] = (
                segments_obj.to_raw_data()
                if hasattr(segments_obj, "to_raw_data")
                else list(segments_obj)
            )
        except Exception as exc:
            raise TranscriptUnavailableError(
                f"Failed to fetch caption segments for video '{video_id}': {exc}"
            ) from exc

        if not raw_segments:
            raise TranscriptUnavailableError(f"Transcript for video '{video_id}' is empty")

        text_parts: list[str] = []
        for seg in raw_segments:
            if isinstance(seg, dict):
                t_val = seg.get("text", "")
            else:
                t_val = getattr(seg, "text", "")
            if t_val and str(t_val).strip():
                text_parts.append(str(t_val).strip())

        joined_text = " ".join(text_parts)
        if not joined_text.strip():
            raise TranscriptUnavailableError(f"Transcript text for video '{video_id}' is empty")

        return TranscriptResult(
            text=joined_text,
            language=getattr(selected_transcript, "language_code", "unknown"),
            is_generated=bool(getattr(selected_transcript, "is_generated", False)),
            provider=self.provider,
            segment_count=len(raw_segments),
        )

    async def fetch_transcript(
        self,
        video_id: str,
        preferred_languages: list[str] | None = None,
    ) -> TranscriptResult:
        langs = preferred_languages or self.preferred_languages
        return await asyncio.to_thread(self._sync_fetch, video_id, langs)


class FakeTranscriptProvider:
    """Hermetic test transcript provider."""

    provider: str = "fake-transcript-provider"

    def __init__(
        self,
        canned_transcripts: dict[str, TranscriptResult] | None = None,
        exception_to_raise: Exception | None = None,
    ) -> None:
        self.canned_transcripts: dict[str, TranscriptResult] = canned_transcripts or {}
        self.exception_to_raise = exception_to_raise
        self.fetched_video_ids: list[str] = []

    async def fetch_transcript(
        self,
        video_id: str,
        preferred_languages: list[str] | None = None,
    ) -> TranscriptResult:
        self.fetched_video_ids.append(video_id)
        if self.exception_to_raise:
            raise self.exception_to_raise
        if video_id in self.canned_transcripts:
            return self.canned_transcripts[video_id]
        raise TranscriptUnavailableError(f"No fake transcript found for video_id {video_id}")
