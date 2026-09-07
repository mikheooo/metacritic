#!/usr/bin/env python3
"""
Standalone script to backfill game covers from Metacritic without modifying
other tables, cursors, AI summaries, vector embeddings, or YouTube data.
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.cli import run_backfill_covers_command  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill missing Metacritic game covers")
    parser.add_argument(
        "--apply",
        action="store_true",
        dest="apply",
        help="Apply database updates (default is dry-run)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_false",
        dest="apply",
        help="Run without committing updates to database (default)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Polite delay between HTTP requests in seconds (default: 0.5)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum games to check (default: all missing)",
    )

    args = parser.parse_args()
    asyncio.run(
        run_backfill_covers_command(
            dry_run=not args.apply,
            delay=args.delay,
            limit=args.limit,
        )
    )


if __name__ == "__main__":
    main()
