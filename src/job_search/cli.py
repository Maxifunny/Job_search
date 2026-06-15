"""CLI entry point for the job search system."""

import argparse
from pathlib import Path

from config.sector_loader import SectorConfigError, list_sector_ids, resolve_sector
from job_search.matching.service import load_profile, match_pending_offers
from job_search.memory.database import init_database
from job_search.orchestrator import JobSearchPipeline
from job_search.schemas.job_offer import JobSector, coerce_sector_id
from job_search.scrapers import list_sources, scrape_and_persist


def _sector_choices() -> list[str]:
    return list_sector_ids()


def _parse_sector(value: str) -> JobSector:
    try:
        return JobSector(value)
    except SectorConfigError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Autonomous Job Search System")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init-db", help="Initialize SQLite/PostgreSQL schema")

    sub.add_parser(
        "list-sectors",
        help="List available sector ids and display names from config/sectors/",
    )

    scrape = sub.add_parser("scrape", help="Run scrapers for configured sectors")
    scrape.add_argument(
        "--sector",
        type=_parse_sector,
        choices=_sector_choices(),
        required=True,
        help="Target sector slug (see list-sectors)",
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
        type=_parse_sector,
        choices=_sector_choices(),
        help="Optional sector filter (see list-sectors)",
    )
    match.add_argument(
        "--limit",
        type=int,
        help="Maximum number of offers to evaluate",
    )

    run = sub.add_parser("run", help="Full pipeline: scrape → store → match → recommend")
    run.add_argument(
        "--sector",
        type=_parse_sector,
        choices=_sector_choices(),
        required=True,
        help="Target sector slug (see list-sectors)",
    )
    run.add_argument(
        "--profile",
        default="config/profiles/default.json",
        help="Path to candidate profile JSON (default: config/profiles/default.json)",
    )
    run.add_argument(
        "--source",
        choices=list_sources(),
        help="Optional single portal source (default: all configured portals)",
    )
    run.add_argument(
        "--max-offers",
        type=int,
        help="Limit offers scraped per portal",
    )
    run.add_argument(
        "--max-pages",
        type=int,
        help="Limit number of pages scraped per portal",
    )
    run.add_argument(
        "--match-limit",
        type=int,
        help="Limit number of offers evaluated by the LLM (saves API quota)",
    )
    run.add_argument(
        "--no-sync-vectors",
        dest="sync_vectors",
        action="store_false",
        help="Skip ChromaDB embeddings during scrape (debug only)",
    )
    run.set_defaults(sync_vectors=True)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "init-db":
        init_database()
        print("Database initialized.")
    elif args.command == "list-sectors":
        for sector_id in list_sector_ids():
            config = resolve_sector(sector_id)
            print(f"{sector_id}\t{config.display_name}")
    elif args.command == "scrape":
        sector = args.sector
        summaries = scrape_and_persist(
            sector,
            source=args.source,
            sync_vectors=args.sync_vectors,
        )
        for summary in summaries:
            print(
                f"[{summary.source}] sector={summary.sector} "
                f"found={summary.offers_found} new={summary.offers_new} "
                f"updated={summary.offers_updated} errors={len(summary.errors)}"
            )
            for error in summary.errors:
                print(f"  - {error}")
    elif args.command == "match":
        profile = load_profile(Path(args.profile))
        sector_arg = coerce_sector_id(args.sector) if args.sector is not None else None
        summary = match_pending_offers(
            profile,
            sector=sector_arg,
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
        sector = args.sector
        profile = load_profile(Path(args.profile))
        pipeline = JobSearchPipeline()
        try:
            result = pipeline.run(
                sector,
                profile,
                source=args.source,
                sync_vectors=args.sync_vectors,
                max_offers=args.max_offers,
                max_pages=args.max_pages,
                match_limit=args.match_limit,
            )
        except KeyboardInterrupt:
            print("\n[pipeline] Przerwano pipeline.")
            return

        print(f"\n=== REKOMENDACJE ({len(result.recommendations)}) ===")
        if result.recommendations:
            for recommendation in result.recommendations:
                print(f"✅ {recommendation}")
        else:
            print("Brak nowych rekomendacji dla tego profilu.")

        if result.scrape_errors:
            print(f"\n[pipeline] Błędy scrapera ({len(result.scrape_errors)}):")
            for error in result.scrape_errors:
                print(f"  - {error}")
        if result.errors:
            print(f"\n[pipeline] Błędy ({len(result.errors)}):")
            for error in result.errors:
                print(f"  - {error}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
