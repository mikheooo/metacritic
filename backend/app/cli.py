import argparse
import asyncio
import sys

from app.db.session import AsyncSessionLocal
from app.services.crawler.ingestion_service import IngestionService


async def run_crawl_command(limit: int, dry_run: bool, trigger: str) -> None:
    print("=== METACRITIC CRAWL INVOCATION ===")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE PERSISTENCE'}")
    print(f"Limit: {limit}")
    print(f"Trigger: {trigger}")
    print("-----------------------------------")

    async with AsyncSessionLocal() as session:
        service = IngestionService(db=session)
        result = await service.run_crawl(
            limit=limit,
            trigger_type=trigger,
            dry_run=dry_run,
        )

    print("-----------------------------------")
    print(f"Status:          {result.status}")
    print(f"Phase:           {result.phase}")
    print(f"Eligible Count:  {result.eligible_count}")
    print(f"Processed Count: {result.processed_count}")
    print(f"Failed Count:    {result.failed_count}")
    if result.crawl_run_id:
        print(f"CrawlRun ID:     {result.crawl_run_id}")

    if result.candidates:
        print("\nCandidates:")
        for idx, title in enumerate(result.candidates, 1):
            print(f"  {idx}. {title}")

    if result.errors:
        print("\nErrors encountered:")
        for err in result.errors:
            print(f"  - {err}")
    print("===================================")


async def run_enrich_command(
    game_id: int | None,
    slug: str | None,
    summarize_only: bool = False,
) -> None:
    from sqlalchemy import select

    from app.models.game import Game
    from app.services.ai import ReviewEnrichmentService

    print("=== REVIEW ENRICHMENT INVOCATION ===")
    async with AsyncSessionLocal() as session:
        target_game_id = game_id

        if not target_game_id and slug:
            stmt = select(Game.id).where(Game.metacritic_slug == slug)
            res = await session.execute(stmt)
            target_game_id = res.scalar_one_or_none()
            if not target_game_id:
                print(f"Error: Game with slug '{slug}' not found in database.")
                sys.exit(1)

        if not target_game_id:
            # Pick first game in database
            stmt = select(Game.id).order_by(Game.id.asc()).limit(1)
            res = await session.execute(stmt)
            target_game_id = res.scalar_one_or_none()
            if not target_game_id:
                print("Error: No games found in database. Run crawl first.")
                sys.exit(1)

        print(f"Target Game ID: {target_game_id}")
        service = ReviewEnrichmentService(db=session)

        if summarize_only:
            stmt_g = select(Game).where(Game.id == target_game_id)
            g_res = await session.execute(stmt_g)
            game_obj = g_res.scalar_one()
            c_res = await service.summarize_game_reviews(game_obj, "critic")
            u_res = await service.summarize_game_reviews(game_obj, "user")
            await session.commit()
            print(f"Critic summary status: {c_res.status} (fingerprint: {c_res.input_fingerprint})")
            print(f"User summary status:   {u_res.status} (fingerprint: {u_res.input_fingerprint})")
        else:
            result = await service.enrich_and_summarize(target_game_id)
            print("-----------------------------------")
            print(f"Critic reviews ingested: {result.critic_reviews_ingested}")
            print(f"User reviews ingested:   {result.user_reviews_ingested}")
            print(f"Critic summary status:   {result.critic_summary_status}")
            print(f"User summary status:     {result.user_summary_status}")
            if result.errors:
                print("Errors:")
                for err in result.errors:
                    print(f"  - {err}")
    print("===================================")


async def run_embed_command(
    game_id: int | None,
    all_games: bool = False,
    force: bool = False,
) -> None:
    from app.services.ai import GameEmbeddingService

    print("=== GAME EMBEDDING INVOCATION ===")
    async with AsyncSessionLocal() as session:
        service = GameEmbeddingService(db=session)
        if all_games:
            print(f"Embedding all games (force={force})...")
            res = await service.embed_all(force=force)
            print("-----------------------------------")
            print(f"Total games:       {res['total']}")
            print(f"Generated:         {res['generated']}")
            print(f"Skipped Unchanged: {res['skipped_unchanged']}")
            print(f"Failed:            {res['failed']}")
        elif game_id:
            print(f"Embedding game ID {game_id} (force={force})...")
            res_single = await service.refresh_game_embedding(game_id=game_id, force=force)
            print("-----------------------------------")
            print(f"Game ID:           {res_single.game_id}")
            print(f"Status:            {res_single.status}")
            print(f"Provider:          {res_single.provider}")
            print(f"Model:             {res_single.model}")
            print(f"Dimensions:        {res_single.dimensions}")
            if res_single.input_fingerprint:
                print(f"Fingerprint:       {res_single.input_fingerprint[:16]}...")
            print(f"Input Tokens:      {res_single.input_tokens}")
            if res_single.error:
                print(f"Error:             {res_single.error}")
        else:
            print("Error: Specify either --game-id <id> or --all")
            sys.exit(1)
    print("===================================")


async def run_similarity_command(
    game_id: int | None,
    rebuild_all: bool = False,
    limit: int = 5,
) -> None:
    from sqlalchemy import select

    from app.models.game import Game
    from app.services.ai import SimilarGamesService

    print("=== SIMILAR GAMES INVOCATION ===")
    async with AsyncSessionLocal() as session:
        service = SimilarGamesService(db=session, limit=limit)
        if rebuild_all:
            print(f"Rebuilding similarity cache for all embedded games (limit={limit})...")
            res = await service.rebuild_all(limit=limit)
            print("-----------------------------------")
            print(f"Total Games:       {res['total_games']}")
            print(f"Associations:      {res['total_associations']}")
            print(f"Duration:          {res['duration_ms']:.2f} ms")
        elif game_id:
            print(f"Computing top {limit} similar games for Game ID {game_id}...")
            matches = await service.refresh_for_game(game_id=game_id, limit=limit)
            print("-----------------------------------")
            if not matches:
                print("No similar games found (or source game has no embedding).")
            else:
                for idx, match in enumerate(matches, 1):
                    stmt_g = select(Game.title).where(Game.id == match.similar_game_id)
                    title = (
                        await session.execute(stmt_g)
                    ).scalar() or f"Game #{match.similar_game_id}"
                    print(
                        f"  {idx}. {title} (ID: {match.similar_game_id}) — Score: {match.similarity_score:.4f}"
                    )
        else:
            print("Error: Specify either --game-id <id> or --rebuild-all")
            sys.exit(1)
    print("===================================")


async def run_youtube_command(
    game_id: int | None,
    missing: bool,
    all_games: bool,
    force: bool,
) -> None:
    from sqlalchemy import select

    from app.models.game import Game
    from app.models.youtube import GameYouTubeVideo
    from app.services.youtube import YouTubeEnrichmentService

    print("=== YOUTUBE LET'S PLAY ENRICHMENT ===")
    async with AsyncSessionLocal() as session:
        service = YouTubeEnrichmentService(db=session)

        target_ids: list[int] = []
        if game_id is not None:
            target_ids = [game_id]
        elif missing:
            stmt = (
                select(Game.id)
                .outerjoin(GameYouTubeVideo, Game.id == GameYouTubeVideo.game_id)
                .where(GameYouTubeVideo.id.is_(None))
                .order_by(Game.id.asc())
            )
            res = await session.execute(stmt)
            target_ids = list(res.scalars().all())
            print(f"Found {len(target_ids)} games missing YouTube data.")
        elif all_games:
            stmt = select(Game.id).order_by(Game.id.asc())
            res = await session.execute(stmt)
            target_ids = list(res.scalars().all())
            print(f"Found {len(target_ids)} total games.")
        else:
            # Pick first game
            stmt = select(Game.id).order_by(Game.id.asc()).limit(1)
            res = await session.execute(stmt)
            first_id = res.scalar_one_or_none()
            if first_id is not None:
                target_ids = [first_id]
            else:
                print("Error: No games found in database. Run crawl first.")
                return

        for gid in target_ids:
            res_item = await service.enrich_game(game_id=gid, force=force)
            print(
                f"Game #{gid}: status={res_item.status}, video_id={res_item.video_id}, rank={res_item.selection_rank}"
            )
            if res_item.selection_reason:
                print(f"  Reason: {res_item.selection_reason}")
            if res_item.transcript_status:
                print(f"  Transcript: {res_item.transcript_status}")
            if res_item.summary_status:
                print(f"  Summary: {res_item.summary_status}")
            if res_item.error:
                print(f"  Error: {res_item.error}")
    print("=====================================")


async def run_backfill_covers_command(
    dry_run: bool = True,
    delay: float = 0.5,
    limit: int | None = None,
) -> None:
    import httpx
    from sqlalchemy import select

    from app.models.game import Game
    from app.services.crawler.client import DEFAULT_HEADERS
    from app.services.crawler.parser import MetacriticParser

    print("=== BACKFILL GAME COVERS ===")
    print(
        f"Mode:         {'DRY RUN (no database changes)' if dry_run else 'LIVE PERSISTENCE (updating games.cover_url)'}"
    )
    print(f"Polite Delay: {delay}s")
    print(f"Limit:        {limit or 'None (all missing)'}")
    print("----------------------------------------------------------------------")

    async with AsyncSessionLocal() as session:
        stmt = (
            select(Game)
            .where((Game.cover_url.is_(None)) | (Game.cover_url == ""))
            .order_by(Game.id.asc())
        )
        if limit:
            stmt = stmt.limit(limit)
        res = await session.execute(stmt)
        games_to_check = list(res.scalars().all())

        total_scanned = len(games_to_check)
        print(f"Found {total_scanned} games with missing/empty cover_url in database.\n")

        found_count = 0
        updated_count = 0
        failed_requests = 0

        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            timeout=15.0,
            follow_redirects=True,
        ) as client:
            # First, collect candidate thumbnails from New Releases and Browse listing pages
            listing_covers: dict[str, tuple[str, str]] = {}
            print("Scanning Metacritic listing pages for candidate cover artwork...")
            try:
                r_nr = await client.get("https://www.metacritic.com/game/")
                if r_nr.status_code == 200:
                    for cand in MetacriticParser.parse_new_releases(r_nr.text):
                        if cand.cover_url:
                            listing_covers[cand.external_id] = ("New Releases", cand.cover_url)
                for page in range(1, 16):
                    r_bp = await client.get(
                        f"https://www.metacritic.com/browse/game/all/all/all-time/new/?page={page}"
                    )
                    if r_bp.status_code != 200:
                        break
                    bp = MetacriticParser.parse_browse_page(r_bp.text, page=page)
                    for cand in bp.candidates:
                        if cand.cover_url and cand.external_id not in listing_covers:
                            listing_covers[cand.external_id] = (
                                f"Browse Page {page}",
                                cand.cover_url,
                            )
                    if not bp.has_next:
                        break
                    await asyncio.sleep(0.1)
            except Exception as exc:
                print(f"  Warning: listing scan encountered error: {exc}")

            print(f"Listing pages scanned. Found {len(listing_covers)} candidate covers.\n")

            audit_rows: list[tuple[int, str, str, str, str | None]] = []

            for idx, game in enumerate(games_to_check, 1):
                url = game.metacritic_url
                new_cover: str | None = None
                source_used = "Detail Page"

                print(f"[{idx}/{total_scanned}] Game #{game.id}: '{game.title}'")
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        details = MetacriticParser.parse_game_details(resp.text, url)
                        new_cover = details.cover_url
                    else:
                        print(f"  -> HTTP {resp.status_code} fetching detail page")
                        failed_requests += 1
                except Exception as e:
                    print(f"  -> Error fetching detail page: {e}")
                    failed_requests += 1

                # Priority 2: listing-card cover if detail-page cover absent
                if not new_cover and game.metacritic_slug in listing_covers:
                    source_name, cand_cover = listing_covers[game.metacritic_slug]
                    new_cover = cand_cover
                    source_used = f"Listing ({source_name})"

                if new_cover:
                    found_count += 1
                    print(f"  -> Found cover via {source_used}: {new_cover}")
                    if not dry_run:
                        game.cover_url = new_cover
                        updated_count += 1
                else:
                    print("  -> No cover available on Metacritic (detail, listing, or Nuxt)")

                audit_rows.append(
                    (
                        game.id,
                        game.title,
                        source_used if new_cover else "Metacritic (Detail + Listing)",
                        "yes" if new_cover else "no",
                        new_cover,
                    )
                )

                if delay > 0 and idx < total_scanned:
                    await asyncio.sleep(delay)

        if not dry_run and updated_count > 0:
            await session.commit()
            print(f"\n[SUCCESS] Committed {updated_count} cover updates to database.")

        print("\n=== DRY-RUN / AUDIT TABLE ===")
        print("| id | title | listing source | image found yes/no | image URL |")
        print("|---|---|---|---|---|")
        for gid, gtitle, gsrc, gfound, gurl in audit_rows:
            print(f"| {gid} | {gtitle} | {gsrc} | {gfound} | {gurl or 'None'} |")

        remaining = total_scanned - (updated_count if not dry_run else found_count)
        print("----------------------------------------------------------------------")
        print("SUMMARY:")
        print(f"  Total games scanned:           {total_scanned}")
        print(f"  Covers found on Metacritic:    {found_count}")
        print(f"  Covers updated in DB:          {updated_count}")
        print(f"  Failed HTTP requests:          {failed_requests}")
        print(f"  Games remaining without cover: {remaining}")
        print("======================================================================")


async def run_backfill_russian_content_command(
    dry_run: bool = False,
    limit: int | None = None,
    batch_size: int = 5,
) -> None:
    from sqlalchemy import select

    from app.models.game import Game
    from app.models.review import Review
    from app.models.summary import GameReviewSummary
    from app.services.ai import (
        ContentTranslationService,
        ReviewEnrichmentService,
        compute_text_hash,
        is_already_russian,
    )

    print("=== BACKFILL RUSSIAN CONTENT ===")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE PERSISTENCE'}")
    if limit:
        print(f"Limit: {limit}")
    print(f"Batch size: {batch_size}")
    print("-----------------------------------")

    games_processed = 0
    descriptions_translated = 0
    reviews_translated = 0
    summaries_generated = 0
    skipped_unchanged = 0
    failed = 0

    async with AsyncSessionLocal() as session:
        translation_service = ContentTranslationService(db=session)
        enrichment_service = ReviewEnrichmentService(db=session)

        stmt = select(Game).order_by(Game.id.asc())
        if limit:
            stmt = stmt.limit(limit)
        res = await session.execute(stmt)
        games = list(res.scalars().all())

        total_games = len(games)
        print(f"Found {total_games} game(s) to evaluate.")

        for idx, game in enumerate(games, 1):
            games_processed += 1
            print(f"[{idx}/{total_games}] Processing '{game.title}' (id: {game.id})...")

            # 1. Description translation
            if game.description and game.description.strip():
                cleaned_desc = game.description.strip()
                desc_hash = compute_text_hash(cleaned_desc)
                if game.description_ru and game.description_source_hash == desc_hash:
                    skipped_unchanged += 1
                elif is_already_russian(cleaned_desc):
                    if not game.description_ru:
                        descriptions_translated += 1
                        if not dry_run:
                            game.description_ru = cleaned_desc
                            game.description_source_hash = desc_hash
                    else:
                        skipped_unchanged += 1
                else:
                    if dry_run:
                        descriptions_translated += 1
                    else:
                        try:
                            d_res = await translation_service.translate_game_description(game)
                            if d_res.status in ("translated", "already_russian"):
                                descriptions_translated += 1
                            elif d_res.status == "skipped_unchanged":
                                skipped_unchanged += 1
                            elif d_res.status == "error":
                                failed += 1
                        except Exception as exc:
                            failed += 1
                            print(
                                f"  [Error] Description translation failed for '{game.title}': {exc}"
                            )

            # 2. Reviews translation (top 10 per type)
            for r_type in ("critic", "user"):
                r_stmt = (
                    select(Review)
                    .where(
                        Review.game_id == game.id,
                        Review.review_type == r_type,
                        Review.body.is_not(None),
                        Review.body != "",
                    )
                    .order_by(Review.rating.desc().nullslast(), Review.id.asc())
                    .limit(10)
                )
                r_res = await session.execute(r_stmt)
                reviews = list(r_res.scalars().all())

                for rev in reviews:
                    if not rev.body or not rev.body.strip():
                        continue
                    cleaned_body = rev.body.strip()
                    rev_hash = compute_text_hash(cleaned_body)

                    if rev.body_ru and rev.body_source_hash == rev_hash:
                        skipped_unchanged += 1
                    elif is_already_russian(cleaned_body):
                        if not rev.body_ru:
                            reviews_translated += 1
                            if not dry_run:
                                rev.body_ru = cleaned_body
                                rev.body_source_hash = rev_hash
                        else:
                            skipped_unchanged += 1
                    else:
                        if dry_run:
                            reviews_translated += 1
                        else:
                            try:
                                translated = await translation_service.translator.translate_text(
                                    cleaned_body, context_type="review"
                                )
                                rev.body_ru = translated.strip()
                                rev.body_source_hash = rev_hash
                                reviews_translated += 1
                            except Exception as exc:
                                failed += 1
                                print(f"  [Error] Review {rev.id} translation failed: {exc}")

            # 3. Summaries check / generation
            for r_type in ("critic", "user"):
                s_stmt = select(GameReviewSummary).where(
                    GameReviewSummary.game_id == game.id,
                    GameReviewSummary.review_type == r_type,
                )
                s_res = await session.execute(s_stmt)
                summary_row = s_res.scalar_one_or_none()
                if summary_row and summary_row.summary and is_already_russian(summary_row.summary):
                    skipped_unchanged += 1
                else:
                    if dry_run:
                        summaries_generated += 1
                    else:
                        try:
                            s_exec = await enrichment_service.summarize_game_reviews(game, r_type)
                            if s_exec.status == "generated":
                                summaries_generated += 1
                            elif s_exec.status == "skipped_unchanged":
                                skipped_unchanged += 1
                            elif s_exec.status == "error":
                                failed += 1
                        except Exception as exc:
                            failed += 1
                            print(f"  [Error] {r_type.title()} summary generation failed: {exc}")

            if not dry_run and idx % batch_size == 0:
                await session.commit()
                print(f"  [Batch commit] Committed changes up to game {idx}")

        if not dry_run:
            await session.commit()

    print("-----------------------------------")
    print(f"games_processed:         {games_processed}")
    print(f"descriptions_translated: {descriptions_translated}")
    print(f"reviews_translated:      {reviews_translated}")
    print(f"summaries_generated:     {summaries_generated}")
    print(f"skipped_unchanged:       {skipped_unchanged}")
    print(f"failed:                  {failed}")
    print("===================================")


def main() -> None:
    parser = argparse.ArgumentParser(description="Metacritic AI Platform CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    crawl_parser = subparsers.add_parser("crawl", help="Run Metacritic ingestion crawl")
    crawl_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of eligible games to process (default: 20)",
    )
    crawl_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate candidate discovery without persisting to DB or modifying cursor",
    )
    crawl_parser.add_argument(
        "--trigger",
        type=str,
        default="manual",
        help="Trigger type (manual or scheduled, default: manual)",
    )

    enrich_parser = subparsers.add_parser(
        "enrich", help="Enrich game reviews and generate AI summaries"
    )
    enrich_parser.add_argument(
        "--game-id",
        type=int,
        default=None,
        help="Specific game ID to enrich",
    )
    enrich_parser.add_argument(
        "--slug",
        type=str,
        default=None,
        help="Specific game slug to enrich",
    )
    enrich_parser.add_argument(
        "--summarize-only",
        action="store_true",
        help="Only run review summarization without scraping reviews",
    )

    embed_parser = subparsers.add_parser("embed", help="Generate semantic vector embeddings")
    embed_parser.add_argument(
        "--game-id",
        type=int,
        default=None,
        help="Specific game ID to embed",
    )
    embed_parser.add_argument(
        "--all",
        action="store_true",
        dest="all_games",
        help="Embed all games in database",
    )
    embed_parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-embedding even if input fingerprint is unchanged",
    )

    sim_parser = subparsers.add_parser(
        "similarity", help="Compute and materialize similar game recommendations"
    )
    sim_parser.add_argument(
        "--game-id",
        type=int,
        default=None,
        help="Specific game ID to refresh similarities for",
    )
    sim_parser.add_argument(
        "--rebuild-all",
        action="store_true",
        help="Rebuild similarity cache for all embedded games",
    )
    sim_parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum similar games to retrieve per game (default: 5)",
    )

    youtube_parser = subparsers.add_parser(
        "youtube", help="Discover and summarize YouTube Let's Plays"
    )
    youtube_parser.add_argument(
        "--game-id",
        type=int,
        default=None,
        help="Specific game ID to enrich with YouTube Let's Play",
    )
    youtube_parser.add_argument(
        "--missing",
        action="store_true",
        help="Enrich all games missing YouTube Let's Play data",
    )
    youtube_parser.add_argument(
        "--all",
        action="store_true",
        dest="all_games",
        help="Enrich all games in catalog",
    )
    youtube_parser.add_argument(
        "--force",
        action="store_true",
        help="Force search and regeneration even if fresh or unchanged",
    )

    backfill_parser = subparsers.add_parser(
        "backfill-covers", help="Backfill missing/broken game covers without modifying other fields"
    )
    backfill_parser.add_argument(
        "--apply",
        action="store_true",
        dest="apply",
        help="Apply database updates (defaults to dry-run if omitted)",
    )
    backfill_parser.add_argument(
        "--dry-run",
        action="store_false",
        dest="apply",
        help="Run without committing updates to database (default)",
    )
    backfill_parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Polite delay between HTTP requests in seconds (default: 0.5)",
    )
    backfill_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum games to check (default: all missing)",
    )

    ru_parser = subparsers.add_parser(
        "backfill-russian-content",
        help="Backfill Russian translations for descriptions, reviews, and summaries",
    )
    ru_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate backfill without persisting changes to database",
    )
    ru_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum games to process (default: all)",
    )
    ru_parser.add_argument(
        "--batch-size",
        type=int,
        default=5,
        help="Number of games to process per commit batch (default: 5)",
    )

    args = parser.parse_args()

    if args.command == "crawl":
        asyncio.run(run_crawl_command(limit=args.limit, dry_run=args.dry_run, trigger=args.trigger))
    elif args.command == "enrich":
        asyncio.run(
            run_enrich_command(
                game_id=args.game_id, slug=args.slug, summarize_only=args.summarize_only
            )
        )
    elif args.command == "embed":
        asyncio.run(
            run_embed_command(game_id=args.game_id, all_games=args.all_games, force=args.force)
        )
    elif args.command == "similarity":
        asyncio.run(
            run_similarity_command(
                game_id=args.game_id, rebuild_all=args.rebuild_all, limit=args.limit
            )
        )
    elif args.command == "youtube":
        asyncio.run(
            run_youtube_command(
                game_id=args.game_id,
                missing=args.missing,
                all_games=args.all_games,
                force=args.force,
            )
        )
    elif args.command == "backfill-covers":
        asyncio.run(
            run_backfill_covers_command(
                dry_run=not args.apply,
                delay=args.delay,
                limit=args.limit,
            )
        )
    elif args.command == "backfill-russian-content":
        asyncio.run(
            run_backfill_russian_content_command(
                dry_run=args.dry_run,
                limit=args.limit,
                batch_size=args.batch_size,
            )
        )
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
