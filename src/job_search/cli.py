"""CLI entry point for the job search system."""

import argparse
import sys
from pathlib import Path

from config.sector_loader import SectorConfigError, list_sector_ids, resolve_sector
from job_search.matching.service import (
    list_recent_recommendations,
    load_profile,
    match_pending_offers,
)
from job_search.memory.database import get_session, init_database, migrate_database
from job_search.memory.repositories import JobOfferRepository
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
    sub.add_parser("migrate", help="Apply Alembic database migrations (upgrade head)")

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
    run.add_argument(
        "--db-only",
        action="store_true",
        help="Skip scraping and run matching only on offers already in database",
    )
    run.add_argument(
        "--history-limit",
        type=int,
        default=10,
        help="How many previously recommended offers to print after run (default: 10)",
    )
    run.set_defaults(sync_vectors=True)

    hide = sub.add_parser(
        "hide-offer",
        help="Hide an offer for a candidate so it is skipped in future matching",
    )
    hide.add_argument(
        "--profile",
        default="config/profiles/default.json",
        help="Path to candidate profile JSON (default: config/profiles/default.json)",
    )
    hide.add_argument("--offer-id", type=int, help="Internal job_offer id from SQLite")
    hide.add_argument("--url", help="Offer URL to hide")
    hide.add_argument("--reason", help="Optional reason why the offer was hidden")

    schedule = sub.add_parser(
        "schedule",
        help=(
            "Print PowerShell commands to register a Windows Scheduled Task "
            "(documentation helper)"
        ),
    )
    schedule.add_argument(
        "--sector",
        default="data",
        help="Sector slug passed to run_job_search.ps1 (default: data)",
    )
    schedule.add_argument(
        "--profile",
        default="config/profiles/default.json",
        help="Profile path (default: config/profiles/default.json)",
    )
    schedule.add_argument(
        "--source",
        default="justjoin",
        help="Portal source (default: justjoin)",
    )
    schedule.add_argument(
        "--max-offers",
        type=int,
        default=30,
        help="Max offers per portal (default: 30)",
    )
    schedule.add_argument(
        "--match-limit",
        type=int,
        default=20,
        help="LLM evaluation limit (default: 20)",
    )
    schedule.add_argument(
        "--sync-vectors",
        action="store_true",
        help="Include -SyncVectors in the registration command",
    )
    schedule.add_argument(
        "--task-name",
        default="JobSearch-Daily",
        help="Windows task name (default: JobSearch-Daily)",
    )
    schedule.add_argument(
        "--hour",
        type=int,
        default=8,
        help="Daily trigger hour (default: 8)",
    )
    schedule.add_argument(
        "--minute",
        type=int,
        default=0,
        help="Daily trigger minute (default: 0)",
    )

    return parser


def _safe_print(text: str) -> None:
    """Print without crashing on legacy Windows consoles (cp1250/cp1252)."""
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        fallback = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(fallback)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "init-db":
        init_database()
        print("Database initialized.")
    elif args.command == "migrate":
        migrate_database()
        print("Database migrations applied (alembic upgrade head).")
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
                f"-> {outcome.offer.url}"
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
                db_only=args.db_only,
            )
        except KeyboardInterrupt:
            print("\n[pipeline] Przerwano pipeline.")
            return

        print(f"\n=== REKOMENDACJE ({len(result.recommendations)}) ===")
        if result.recommendations:
            for recommendation in result.recommendations:
                _safe_print(f"[OK] {recommendation}")
        else:
            print("Brak nowych rekomendacji dla tego profilu.")

        historical = list_recent_recommendations(
            profile.name,
            sector=sector.value,
            limit=max(0, args.history_limit),
        )
        if historical:
            print(f"\n=== OSTATNIE REKOMENDACJE Z BAZY ({len(historical)}) ===")
            for row in historical:
                _safe_print(f"[id={row.offer_id}] {row.title} @ {row.company} - {row.url}")

        if result.scrape_errors:
            print(f"\n[pipeline] Błędy scrapera ({len(result.scrape_errors)}):")
            for error in result.scrape_errors:
                print(f"  - {error}")
        if result.errors:
            print(f"\n[pipeline] Błędy ({len(result.errors)}):")
            for error in result.errors:
                print(f"  - {error}")
    elif args.command == "hide-offer":
        if not args.offer_id and not args.url:
            parser.error("hide-offer requires --offer-id or --url")
        profile = load_profile(Path(args.profile))
        with get_session() as session:
            repo = JobOfferRepository(session)
            offer = repo.get_by_id(args.offer_id) if args.offer_id else repo.get_by_url(args.url)
            if offer is None:
                print("[hide-offer] Nie znaleziono oferty.")
                return
            repo.hide_offer(offer.id, profile.name, reason=args.reason)
            print(
                f"[hide-offer] Ukryto ofertę id={offer.id} "
                f"({offer.title} @ {offer.company}) dla profilu '{profile.name}'."
            )
    elif args.command == "schedule":
        profile = args.profile.replace("/", "\\")
        sync_flag = " -SyncVectors" if args.sync_vectors else ""
        print("# Windows Task Scheduler — skopiuj do PowerShell (jako Administrator)\n")
        print("cd <ścieżka-do-repozytorium-Job_search>")
        print(
            f".\\scripts\\windows\\register_scheduled_task.ps1 "
            f"-TaskName {args.task_name} "
            f"-Sector {args.sector} "
            f"-Profile {profile} "
            f"-Source {args.source} "
            f"-MaxOffers {args.max_offers} "
            f"-MatchLimit {args.match_limit} "
            f"-Hour {args.hour} -Minute {args.minute}"
            f"{sync_flag}"
        )
        print("\n# Ręczny test (bez harmonogramu):")
        print(
            f".\\scripts\\windows\\run_job_search.ps1 "
            f"-Sector {args.sector} -Profile {profile} "
            f"-Source {args.source} -MaxOffers {args.max_offers} "
            f"-MatchLimit {args.match_limit}"
            f"{sync_flag}"
        )
        print("\n# Odinstalowanie:")
        print(
            ".\\scripts\\windows\\register_scheduled_task.ps1 "
            f"-Unregister -TaskName {args.task_name}"
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
