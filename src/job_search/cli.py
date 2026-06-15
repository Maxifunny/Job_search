"""CLI entry point for the job search system."""

import argparse

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
    scrape.add_argument(
        "--max-offers",
        type=int,
        default=None,
        help="Max offers per portal query (default: SCRAPER_MAX_OFFERS_PER_QUERY from .env)",
    )
    scrape.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Max listing pages per query (default: SCRAPER_MAX_PAGES from .env)",
    )

    sub.add_parser("match", help="Evaluate pending offers against candidate profile")
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
        scrape_kwargs: dict = {}
        if args.max_offers is not None:
            scrape_kwargs["max_offers"] = args.max_offers
        if args.max_pages is not None:
            scrape_kwargs["max_pages"] = args.max_pages

        try:
            summaries = scrape_and_persist(
                sector,
                source=args.source,
                sync_vectors=args.sync_vectors,
                **scrape_kwargs,
            )
        except KeyboardInterrupt:
            print("\nPrzerwano scrapowanie (Ctrl+C). Częściowe wyniki mogły zostać zapisane.")
            return

        for summary in summaries:
            print(
                f"[{summary.source}] sector={summary.sector.value} "
                f"found={summary.offers_found} new={summary.offers_new} "
                f"updated={summary.offers_updated} errors={len(summary.errors)}"
            )
            for error in summary.errors:
                print(f"  - {error}")
    elif args.command in {"match", "run"}:
        print(f"Command '{args.command}' is not yet implemented.")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
