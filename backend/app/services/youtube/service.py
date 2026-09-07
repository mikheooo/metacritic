import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.game import Game
from app.models.youtube import GameYouTubeVideo, YouTubeSummary, YouTubeTranscript
from app.services.youtube.normalization import (
    compute_transcript_hash,
    compute_youtube_summary_fingerprint,
    normalize_transcript_text,
)
from app.services.youtube.relevance import (
    evaluate_candidate_relevance,
    sort_candidates_by_views,
)
from app.services.youtube.search_provider import (
    YouTubeConfigError,
    YouTubeDataApiProvider,
    YouTubeError,
    YouTubeQuotaError,
    YouTubeSearchProvider,
    YouTubeVideoCandidate,
)
from app.services.youtube.summarizer import (
    OpenRouterVideoSummarizer,
    VideoSummarizer,
    VideoSummaryResult,
)
from app.services.youtube.transcript_provider import (
    TranscriptProvider,
    TranscriptResult,
    TranscriptUnavailableError,
    YouTubeTranscriptApiProvider,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class YouTubeEnrichmentResult:
    game_id: int
    status: str  # generated, updated, skipped_fresh, skipped_disabled, transcript_unavailable, no_relevant_video, failed
    video_id: str | None = None
    selection_rank: int | None = None
    selection_reason: str | None = None
    transcript_status: str | None = None  # fetched, existing, unavailable, skipped
    summary_status: str | None = None  # generated, skipped_unchanged, failed, not_attempted
    error: str | None = None


class YouTubeEnrichmentService:
    """
    Application service orchestrating YouTube Let's Play candidate discovery,
    relevance filtering, view_count ranking, speech transcription,
    and structured AI summarization with strict failure isolation and cost controls.
    """

    def __init__(
        self,
        db: AsyncSession,
        search_provider: YouTubeSearchProvider | None = None,
        transcript_provider: TranscriptProvider | None = None,
        summarizer: VideoSummarizer | None = None,
    ) -> None:
        self.db = db
        self.search_provider = search_provider or YouTubeDataApiProvider()
        self.transcript_provider = transcript_provider or YouTubeTranscriptApiProvider()
        self.summarizer = summarizer or OpenRouterVideoSummarizer()

    async def enrich_game(
        self,
        game_id: int,
        force: bool = False,
    ) -> YouTubeEnrichmentResult:
        """
        Enrich a single game with the most popular relevant YouTube Let's Play,
        transcript, and structured AI summary.
        Entire method is isolated: returns structured result and does NOT raise.
        """
        # 1. Feature Flag Check
        if not settings.YOUTUBE_ENABLED:
            logger.info("YouTube enrichment skipped: YOUTUBE_ENABLED is false")
            return YouTubeEnrichmentResult(
                game_id=game_id,
                status="skipped_disabled",
                error="YouTube enrichment is disabled by configuration",
            )

        # 2. Strict Credential Check for live provider
        if (
            isinstance(self.search_provider, YouTubeDataApiProvider)
            and not self.search_provider.api_key
        ):
            logger.warning(
                "YouTube enrichment skipped for game_id=%d: YOUTUBE_API_KEY is not configured",
                game_id,
            )
            return YouTubeEnrichmentResult(
                game_id=game_id,
                status="skipped_disabled",
                error="YOUTUBE_API_KEY is not configured",
            )

        # 3. Load Game & existing YouTube video
        try:
            stmt = select(Game).where(Game.id == game_id)
            res = await self.db.execute(stmt)
            game = res.scalar_one_or_none()
            if not game:
                return YouTubeEnrichmentResult(
                    game_id=game_id,
                    status="failed",
                    error=f"Game with id {game_id} not found in database",
                )
            game_title = game.title

            stmt_vid = (
                select(GameYouTubeVideo)
                .options(
                    selectinload(GameYouTubeVideo.transcript),
                    selectinload(GameYouTubeVideo.summary),
                )
                .where(GameYouTubeVideo.game_id == game_id)
            )
            res_vid = await self.db.execute(stmt_vid)
            existing_video = res_vid.scalar_one_or_none()
        except Exception as exc:
            logger.error("DB error loading game %d for YouTube enrichment: %s", game_id, exc)
            return YouTubeEnrichmentResult(game_id=game_id, status="failed", error=str(exc))

        now = datetime.now(UTC)

        # 4. Search Refresh TTL / Cost Control (YOUTUBE_SEARCH_REFRESH_HOURS)
        if existing_video and not force:
            refreshed_at = existing_video.refreshed_at or existing_video.created_at
            if refreshed_at.tzinfo is None:
                refreshed_at = refreshed_at.replace(tzinfo=UTC)
            age_hours = (now - refreshed_at).total_seconds() / 3600.0
            if age_hours < settings.YOUTUBE_SEARCH_REFRESH_HOURS:
                # Video is fresh. Check if summary is present or was transcript_unavailable
                if existing_video.status == "transcript_unavailable" or existing_video.summary:
                    logger.info(
                        "Game '%s' (id=%d) has fresh YouTube video (%s, age=%.1fh < %dh). Skipping search.",
                        game.title,
                        game.id,
                        existing_video.youtube_video_id,
                        age_hours,
                        settings.YOUTUBE_SEARCH_REFRESH_HOURS,
                    )
                    return YouTubeEnrichmentResult(
                        game_id=game_id,
                        status="skipped_fresh",
                        video_id=existing_video.youtube_video_id,
                        selection_rank=existing_video.selection_rank,
                        selection_reason=existing_video.selection_reason,
                        transcript_status="existing"
                        if existing_video.transcript
                        else "unavailable",
                        summary_status="skipped_unchanged"
                        if existing_video.summary
                        else "not_attempted",
                    )

        # 5. Search Candidates
        try:
            candidates = await self.search_provider.search_lets_plays(game)
        except YouTubeQuotaError as exc:
            logger.error("YouTube quota exceeded while searching for '%s': %s", game.title, exc)
            return YouTubeEnrichmentResult(
                game_id=game_id, status="failed", error=f"Quota exceeded: {exc}"
            )
        except YouTubeConfigError as exc:
            logger.warning("YouTube configuration error for '%s': %s", game.title, exc)
            return YouTubeEnrichmentResult(
                game_id=game_id, status="skipped_disabled", error=str(exc)
            )
        except YouTubeError as exc:
            logger.error("YouTube API error while searching for '%s': %s", game.title, exc)
            return YouTubeEnrichmentResult(
                game_id=game_id, status="failed", error=f"Search failed: {exc}"
            )
        except Exception as exc:
            logger.error(
                "Unexpected error searching YouTube for '%s': %s", game.title, exc, exc_info=True
            )
            return YouTubeEnrichmentResult(
                game_id=game_id, status="failed", error=f"Unexpected error: {exc}"
            )

        if not candidates:
            logger.info("No candidates returned from YouTube search for '%s'", game.title)
            return YouTubeEnrichmentResult(
                game_id=game_id,
                status="no_relevant_video",
                error="No YouTube candidates found for search query",
            )

        # 6. Filter Relevant Candidates
        relevant_candidates: list[tuple[YouTubeVideoCandidate, str]] = []
        for cand in candidates:
            rel_res = evaluate_candidate_relevance(cand, game_title)
            if rel_res.is_relevant:
                relevant_candidates.append((cand, rel_res.reason))

        if not relevant_candidates:
            logger.info(
                "None of the %d candidates for '%s' passed relevance filters",
                len(candidates),
                game_title,
            )
            return YouTubeEnrichmentResult(
                game_id=game_id,
                status="no_relevant_video",
                error="No candidates passed deterministic Let's Play relevance filter",
            )

        # 7. Sort by view_count DESC
        sorted_relevant = sort_candidates_by_views([c for c, _ in relevant_candidates])

        # 8. Selection Algorithm: Attempt transcripts in popularity order
        selected_cand: YouTubeVideoCandidate | None = None
        selected_transcript: TranscriptResult | None = None
        selection_rank: int = 1
        selection_reason: str = ""

        for idx, cand in enumerate(sorted_relevant, 1):
            try:
                transcript_res = await self.transcript_provider.fetch_transcript(cand.video_id)
                if transcript_res and transcript_res.text.strip():
                    selected_cand = cand
                    selected_transcript = transcript_res
                    selection_rank = idx
                    if idx == 1:
                        selection_reason = "Most-viewed relevant Let's Play candidate with an accessible transcript"
                    else:
                        selection_reason = f"Rank #{idx} most-viewed candidate (top {idx - 1} candidates lacked accessible transcripts)"
                    break
            except TranscriptUnavailableError as exc:
                logger.info(
                    "Candidate #%d ('%s', %s views) transcript unavailable: %s",
                    idx,
                    cand.title,
                    cand.view_count,
                    exc,
                )
                continue
            except Exception as exc:
                logger.warning(
                    "Error fetching transcript for candidate #%d ('%s'): %s",
                    idx,
                    cand.title,
                    exc,
                )
                continue

        # If no candidate had an accessible transcript, pick the top-1 relevant candidate
        if not selected_cand:
            selected_cand = sorted_relevant[0]
            selection_rank = 1
            selection_reason = (
                "Most-viewed relevant candidate, but speech transcript is unavailable"
            )

        # 9. AI Summarization & Fingerprint Cost Control
        summary_status = "not_attempted"
        summary_obj: VideoSummaryResult | None = None
        normalized_transcript: str = ""
        transcript_hash: str = ""
        fingerprint: str = ""

        if selected_transcript:
            normalized_transcript = normalize_transcript_text(selected_transcript.text)
            transcript_hash = compute_transcript_hash(normalized_transcript)
            fingerprint = compute_youtube_summary_fingerprint(
                transcript_hash=transcript_hash,
                provider=self.summarizer.provider,
                model=self.summarizer.model,
                prompt_version=self.summarizer.prompt_version,
                summary_language=self.summarizer.language,
            )

            # Check existing summary fingerprint
            if (
                existing_video
                and existing_video.youtube_video_id == selected_cand.video_id
                and existing_video.summary
                and existing_video.summary.input_fingerprint == fingerprint
            ):
                summary_status = "skipped_unchanged"
                logger.info(
                    "YouTube summary fingerprint unchanged for '%s' (video %s). Skipping paid LLM call.",
                    game_title,
                    selected_cand.video_id,
                )
            else:
                try:
                    summary_obj = await self.summarizer.summarize_video_transcript(
                        game_title=game_title,
                        transcript_text=normalized_transcript,
                    )
                    summary_status = "generated"
                except Exception as exc:
                    logger.error(
                        "LLM summarization failed for '%s' (video %s): %s",
                        game_title,
                        selected_cand.video_id,
                        exc,
                    )
                    summary_status = "failed"

        # 10. Persist Records Atomically
        try:
            existing_transcript = existing_video.transcript if existing_video else None
            existing_summary = existing_video.summary if existing_video else None

            if existing_video and existing_video.youtube_video_id != selected_cand.video_id:
                # Video changed, delete old transcript & summary associated with prior video
                if existing_transcript:
                    await self.db.delete(existing_transcript)
                    existing_transcript = None
                if existing_summary:
                    await self.db.delete(existing_summary)
                    existing_summary = None

            # Upsert GameYouTubeVideo
            if existing_video:
                vid_record = existing_video
                vid_record.youtube_video_id = selected_cand.video_id
                vid_record.url = selected_cand.url
                vid_record.title = selected_cand.title
                vid_record.channel_id = selected_cand.channel_id
                vid_record.channel_title = selected_cand.channel_title
                vid_record.thumbnail_url = selected_cand.thumbnail_url
                vid_record.published_at = selected_cand.published_at
                vid_record.duration_seconds = selected_cand.duration_seconds
                vid_record.view_count = selected_cand.view_count
                vid_record.like_count = selected_cand.like_count
                vid_record.search_query = getattr(
                    self.search_provider, "build_search_query", lambda t: t
                )(game_title)
                vid_record.selection_rank = selection_rank
                vid_record.selection_reason = selection_reason
                vid_record.status = "enriched" if selected_transcript else "transcript_unavailable"
                vid_record.refreshed_at = now
                vid_record.updated_at = now
            else:
                vid_record = GameYouTubeVideo(
                    game_id=game_id,
                    youtube_video_id=selected_cand.video_id,
                    url=selected_cand.url,
                    title=selected_cand.title,
                    channel_id=selected_cand.channel_id,
                    channel_title=selected_cand.channel_title,
                    thumbnail_url=selected_cand.thumbnail_url,
                    published_at=selected_cand.published_at,
                    duration_seconds=selected_cand.duration_seconds,
                    view_count=selected_cand.view_count,
                    like_count=selected_cand.like_count,
                    search_query=getattr(self.search_provider, "build_search_query", lambda t: t)(
                        game_title
                    ),
                    selection_rank=selection_rank,
                    selection_reason=selection_reason,
                    status="enriched" if selected_transcript else "transcript_unavailable",
                    discovered_at=now,
                    refreshed_at=now,
                    created_at=now,
                    updated_at=now,
                )
                self.db.add(vid_record)
                game.youtube_video = vid_record

            await self.db.flush()

            # Upsert YouTubeTranscript
            if selected_transcript:
                if existing_transcript:
                    t_record = existing_transcript
                    t_record.provider = selected_transcript.provider
                    t_record.language = selected_transcript.language
                    t_record.is_generated = selected_transcript.is_generated
                    t_record.text = normalized_transcript
                    t_record.text_hash = transcript_hash
                    t_record.segment_count = selected_transcript.segment_count
                    t_record.fetched_at = now
                    t_record.updated_at = now
                else:
                    t_record = YouTubeTranscript(
                        game_youtube_video_id=vid_record.id,
                        provider=selected_transcript.provider,
                        language=selected_transcript.language,
                        is_generated=selected_transcript.is_generated,
                        text=normalized_transcript,
                        text_hash=transcript_hash,
                        segment_count=selected_transcript.segment_count,
                        fetched_at=now,
                        updated_at=now,
                    )
                    self.db.add(t_record)

            # Upsert YouTubeSummary
            if summary_obj:
                if existing_summary:
                    s_record = existing_summary
                    s_record.summary = summary_obj.summary
                    s_record.key_points = summary_obj.key_points
                    s_record.provider = summary_obj.provider
                    s_record.model = summary_obj.model
                    s_record.prompt_version = summary_obj.prompt_version
                    s_record.summary_language = self.summarizer.language
                    s_record.input_fingerprint = fingerprint
                    s_record.input_tokens = summary_obj.input_tokens
                    s_record.output_tokens = summary_obj.output_tokens
                    s_record.generated_at = now
                    s_record.updated_at = now
                else:
                    s_record = YouTubeSummary(
                        game_youtube_video_id=vid_record.id,
                        summary=summary_obj.summary,
                        key_points=summary_obj.key_points,
                        provider=summary_obj.provider,
                        model=summary_obj.model,
                        prompt_version=summary_obj.prompt_version,
                        summary_language=self.summarizer.language,
                        input_fingerprint=fingerprint,
                        input_tokens=summary_obj.input_tokens,
                        output_tokens=summary_obj.output_tokens,
                        generated_at=now,
                        updated_at=now,
                    )
                    self.db.add(s_record)

            await self.db.commit()

        except Exception as exc:
            await self.db.rollback()
            logger.error(
                "Database error persisting YouTube enrichment for game %d: %s",
                game_id,
                exc,
                exc_info=True,
            )
            return YouTubeEnrichmentResult(game_id=game_id, status="failed", error=str(exc))

        final_status = "enriched" if selected_transcript else "transcript_unavailable"
        return YouTubeEnrichmentResult(
            game_id=game_id,
            status=final_status,
            video_id=selected_cand.video_id,
            selection_rank=selection_rank,
            selection_reason=selection_reason,
            transcript_status="fetched" if selected_transcript else "unavailable",
            summary_status=summary_status,
        )
