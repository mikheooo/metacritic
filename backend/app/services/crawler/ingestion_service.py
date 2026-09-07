import logging
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import get_current_date, get_current_datetime
from app.core.config import settings
from app.models.crawl import CrawlRun, DailyCrawlState, DailyGameProcessing
from app.models.game import Game
from app.models.platform import GamePlatform, Platform
from app.services.crawler.client import MetacriticClient
from app.services.crawler.dtos import (
    GameCandidate,
    GameDetails,
    extract_canonical_slug,
    normalize_canonical_url,
)
from app.services.crawler.lock import CrawlLock
from app.services.crawler.source import MetacriticSource

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    crawl_run_id: int | None
    status: str
    phase: str
    processed_count: int
    failed_count: int
    eligible_count: int
    candidates: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    dry_run: bool = False


class IngestionService:
    """
    Coordinates Metacritic ingestion, daily cursor management,
    candidate deduplication, failure isolation, and atomic UPSERT.
    """

    def __init__(
        self,
        db: AsyncSession,
        source: MetacriticSource | None = None,
    ) -> None:
        self.db = db
        self.source = source or MetacriticClient()

    async def get_or_create_daily_state(self, processing_date: date) -> DailyCrawlState:
        """Fetch or initialize DailyCrawlState for a calendar date."""
        stmt = select(DailyCrawlState).where(DailyCrawlState.processing_date == processing_date)
        res = await self.db.execute(stmt)
        state = res.scalar_one_or_none()
        if not state:
            state = DailyCrawlState(
                processing_date=processing_date,
                phase="new_releases",
                browse_page=1,
                browse_offset=0,
            )
            self.db.add(state)
            await self.db.flush()
        return state

    async def get_processed_ids_today(self, processing_date: date) -> set[str]:
        """Fetch set of game external IDs already successfully processed today."""
        stmt = select(DailyGameProcessing.game_external_id).where(
            DailyGameProcessing.processing_date == processing_date
        )
        res = await self.db.execute(stmt)
        return set(res.scalars().all())

    async def collect_eligible_candidates(
        self,
        limit: int,
        processing_date: date,
        state: DailyCrawlState,
        processed_today: set[str],
    ) -> tuple[list[GameCandidate], str, int]:
        """
        Collect up to `limit` eligible candidates following daily selection semantics:
        1. If phase == 'new_releases', fetch New Releases.
        2. Advance to 'browse' if New Releases exhausted or collected < limit.
        3. Iterate through browse pages until target collected or pages exhausted.
        """
        eligible: list[GameCandidate] = []
        seen_batch_ids: set[str] = set()
        current_phase = state.phase
        current_page = state.browse_page

        # 1. New Releases Phase
        if current_phase == "new_releases":
            logger.info("Executing New Releases discovery phase for %s", processing_date)
            try:
                nr_candidates = await self.source.get_new_releases()
            except Exception as exc:
                logger.error("Error fetching New Releases: %s", exc)
                nr_candidates = []

            for cand in nr_candidates:
                cid = cand.external_id
                if cid not in processed_today and cid not in seen_batch_ids:
                    eligible.append(cand)
                    seen_batch_ids.add(cid)
                    if len(eligible) >= limit:
                        break

            # If New Releases completed or batch full, advance phase to browse for subsequent runs
            current_phase = "browse"
            current_page = 1

        # 2. Browse Phase (if more candidates needed)
        if len(eligible) < limit:
            logger.info(
                "Executing Browse discovery phase starting from page %d (collected %d/%d)",
                current_page,
                len(eligible),
                limit,
            )
            consecutive_empty = 0

            while len(eligible) < limit and consecutive_empty < 3:
                try:
                    page_data = await self.source.get_browse_page(page=current_page)
                except Exception as exc:
                    logger.error("Error fetching Browse page %d: %s", current_page, exc)
                    break

                if not page_data.candidates:
                    consecutive_empty += 1
                else:
                    consecutive_empty = 0

                new_on_page = 0
                for cand in page_data.candidates:
                    cid = cand.external_id
                    if cid not in processed_today and cid not in seen_batch_ids:
                        eligible.append(cand)
                        seen_batch_ids.add(cid)
                        new_on_page += 1
                        if len(eligible) >= limit:
                            break

                logger.info(
                    "Browse page %d: total=%d, new_eligible=%d, cumulative=%d/%d",
                    current_page,
                    len(page_data.candidates),
                    new_on_page,
                    len(eligible),
                    limit,
                )

                if len(eligible) >= limit:
                    break

                if not page_data.has_next:
                    logger.info("Browse pages exhausted at page %d", current_page)
                    break

                current_page += 1

        return eligible[:limit], current_phase, current_page

    async def upsert_game_details(
        self,
        details: GameDetails,
        crawl_run_id: int | None,
        processing_date: date,
    ) -> Game:
        """
        Atomically persist or update game, platforms, scores,
        and record DailyGameProcessing entry.
        """
        now = get_current_datetime()
        canonical_url = normalize_canonical_url(details.metacritic_url)
        canonical_slug = extract_canonical_slug(details.external_id)

        # 1. Upsert Game entity
        stmt = select(Game).where(
            (Game.metacritic_url == canonical_url) | (Game.metacritic_slug == canonical_slug)
        )
        res = await self.db.execute(stmt)
        game = res.scalar_one_or_none()

        if not game:
            game = Game(
                title=details.title,
                metacritic_slug=canonical_slug,
                metacritic_url=canonical_url,
                cover_url=details.cover_url,
                developer=details.developer,
                description=details.description,
                trailer_url=details.trailer_url,
                created_at=now,
                updated_at=now,
            )
            self.db.add(game)
            await self.db.flush()
            logger.info("Inserted new Game: %s (#%d)", game.title, game.id)
        else:
            # Update mutable fields
            game.title = details.title
            game.metacritic_slug = canonical_slug
            game.metacritic_url = canonical_url
            if details.cover_url:
                game.cover_url = details.cover_url
            if details.developer:
                game.developer = details.developer
            if details.description:
                game.description = details.description
            if details.trailer_url:
                game.trailer_url = details.trailer_url
            game.updated_at = now
            await self.db.flush()
            logger.info("Updated existing Game: %s (#%d)", game.title, game.id)

        # 2. Upsert Platforms & GamePlatform associations
        for p_score in details.platforms:
            p_slug = p_score.platform_slug.lower()
            stmt_p = select(Platform).where(Platform.slug == p_slug)
            res_p = await self.db.execute(stmt_p)
            platform = res_p.scalar_one_or_none()

            if not platform:
                platform = Platform(name=p_score.platform_name, slug=p_slug)
                self.db.add(platform)
                await self.db.flush()

            # Check existing GamePlatform
            stmt_gp = select(GamePlatform).where(
                GamePlatform.game_id == game.id,
                GamePlatform.platform_id == platform.id,
            )
            res_gp = await self.db.execute(stmt_gp)
            gp = res_gp.scalar_one_or_none()

            if not gp:
                gp = GamePlatform(
                    game_id=game.id,
                    platform_id=platform.id,
                    metascore=p_score.metascore,
                    userscore=p_score.userscore,
                )
                self.db.add(gp)
            else:
                # Update scores if present
                if p_score.metascore is not None:
                    gp.metascore = p_score.metascore
                if p_score.userscore is not None:
                    gp.userscore = p_score.userscore

        await self.db.flush()

        # 3. Record DailyGameProcessing ledger invariant
        processing_entry = DailyGameProcessing(
            processing_date=processing_date,
            game_external_id=canonical_slug,
            crawl_run_id=crawl_run_id,
            processed_at=now,
        )
        self.db.add(processing_entry)
        await self.db.flush()

        return game

    async def run_crawl(
        self,
        limit: int | None = None,
        trigger_type: str = "manual",
        dry_run: bool = False,
    ) -> IngestionResult:
        """
        Execute an ingestion crawl run with concurrency lock, failure isolation,
        daily ledger checks, and cursor progression.
        """
        batch_limit = limit or settings.CRAWLER_BATCH_LIMIT
        today = get_current_date()
        now = get_current_datetime()

        # Concurrency protection
        async with CrawlLock():
            # Create CrawlRun record
            crawl_run: CrawlRun | None = None
            if not dry_run:
                crawl_run = CrawlRun(
                    status="running",
                    trigger_type=trigger_type,
                    started_at=now,
                    processed_count=0,
                    failed_count=0,
                    created_at=now,
                )
                self.db.add(crawl_run)
                await self.db.commit()
                await self.db.refresh(crawl_run)

            # Retrieve state and existing processed IDs
            state = await self.get_or_create_daily_state(today)
            processed_today = await self.get_processed_ids_today(today)

            # Collect candidates
            candidates, new_phase, new_page = await self.collect_eligible_candidates(
                limit=batch_limit,
                processing_date=today,
                state=state,
                processed_today=processed_today,
            )

            if dry_run:
                logger.info(
                    "[DRY RUN] Identified %d eligible candidates (Phase: %s, Page: %s)",
                    len(candidates),
                    new_phase,
                    new_page,
                )
                return IngestionResult(
                    crawl_run_id=None,
                    status="dry_run",
                    phase=new_phase,
                    processed_count=0,
                    failed_count=0,
                    eligible_count=len(candidates),
                    candidates=[c.title for c in candidates],
                    dry_run=True,
                )

            # Ingestion loop with per-game failure isolation
            processed_count = 0
            failed_count = 0
            processed_names: list[str] = []
            errors: list[str] = []

            for candidate in candidates:
                try:
                    logger.info("Processing game: %s (%s)", candidate.title, candidate.url)
                    details = await self.source.get_game_details(candidate.url)

                    # Use nested savepoint for atomic per-game transaction
                    async with self.db.begin_nested():
                        await self.upsert_game_details(
                            details=details,
                            crawl_run_id=crawl_run.id if crawl_run else None,
                            processing_date=today,
                        )

                    processed_count += 1
                    processed_names.append(details.title)
                    await self.db.commit()

                except Exception as exc:
                    failed_count += 1
                    error_msg = f"Failed to ingest game '{candidate.title}': {exc}"
                    logger.error(error_msg, exc_info=True)
                    errors.append(error_msg)
                    await self.db.rollback()

            # Update daily cursor
            if state.phase == "new_releases" and failed_count > 0:
                new_phase = "new_releases"

            state.phase = new_phase
            state.browse_page = new_page
            state.updated_at = get_current_datetime()

            # Determine crawl run status
            final_status = "completed"
            if failed_count > 0 and processed_count > 0:
                final_status = "partial"
            elif failed_count > 0 and processed_count == 0:
                final_status = "failed"

            if crawl_run:
                crawl_run.status = final_status
                crawl_run.finished_at = get_current_datetime()
                crawl_run.processed_count = processed_count
                crawl_run.failed_count = failed_count

            await self.db.commit()

            return IngestionResult(
                crawl_run_id=crawl_run.id if crawl_run else None,
                status=final_status,
                phase=new_phase,
                processed_count=processed_count,
                failed_count=failed_count,
                eligible_count=len(candidates),
                candidates=processed_names,
                errors=errors,
                dry_run=False,
            )
