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

    args = parser.parse_args()

    if args.command == "crawl":
        asyncio.run(run_crawl_command(limit=args.limit, dry_run=args.dry_run, trigger=args.trigger))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
