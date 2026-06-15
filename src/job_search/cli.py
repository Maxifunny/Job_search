"""CLI entry point for the job search system."""

import argparse
from pathlib import Path

from job_search.matching.service import load_profile, match_pending_offers
from job_search.memory.database import init_database
from job_search.scrapers import list_sources, scrape_and_persist
from job_search.schemas.job_offer import JobSector


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Autonomous Job Search System")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init-db", help="Initialize SQLite/PostgreSQL schema")

    scrape = sub.add_parser("scrape", help="Run scrapers for configured sectors")
    scrape.add_argument(
        "--sector",
        choices=[sector.value for sector in JobSector],
        required=True,
        help="Target sector: data or automation",
    )
    scrape.add_argument(
        "--source",
        choices=list_sources(),
        help="Optional single portal source (default: all configured portals)",
    )
    scrape.add_argument(
        "--sync-vectors",
        action="store_true",
        help="Generate embeddings and upsert into ChromaDB (requires LLM_API_KEY)",
    )

    match = sub.add_parser("match", help="Evaluate pending offers against candidate profile")
    match.add_argument(
        "--profile",
        required=True,
        help="Path to candidate profile JSON (e.g. config/profiles/default.json)",
    )
    match.add_argument(
        "--sector",
        choices=[sector.value for sector in JobSector],
        help="Optional sector filter: data or automation",
    )
    match.add_argument(
        "--limit",
        type=int,
        help="Maximum number of offers to evaluate",
    )

    sub.add_parser("run", help="Full pipeline: scrape → match → recommend")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "init-db":
        init_database()
        print("Database initialized.")
    elif args.command == "scrape":
        sector = JobSector(args.sector)
        summaries = scrape_and_persist(
            sector,
            source=args.source,
            sync_vectors=args.sync_vectors,
        )
        for summary in summaries:
            print(
                f"[{summary.source}] sector={summary.sector.value} "
                f"found={summary.offers_found} new={summary.offers_new} "
                f"updated={summary.offers_updated} errors={len(summary.errors)}"
            )
            for error in summary.errors:
                print(f"  - {error}")
    elif args.command == "match":
        profile = load_profile(Path(args.profile))
        summary = match_pending_offers(
            profile,
            sector=args.sector,
            limit=args.limit,
        )
        print(
            f"evaluated={summary.evaluated} accepted={summary.accepted} "
            f"rejected={summary.rejected} skipped={summary.skipped}"
        )
        for outcome in summary.accepted_outcomes:
            print(
                f"ACCEPTED: {outcome.offer.title} @ {outcome.offer.company} "
                f"→ {outcome.offer.url}"
            )
    elif args.command == "run":
        print(f"Command '{args.command}' is not yet implemented.")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
