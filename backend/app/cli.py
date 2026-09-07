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

    enrich_parser = subparsers.add_parser("enrich", help="Enrich game reviews and generate AI summaries")
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

    args = parser.parse_args()

    if args.command == "crawl":
        asyncio.run(run_crawl_command(limit=args.limit, dry_run=args.dry_run, trigger=args.trigger))
    elif args.command == "enrich":
        asyncio.run(run_enrich_command(game_id=args.game_id, slug=args.slug, summarize_only=args.summarize_only))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

