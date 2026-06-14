"""CLI entry point for the job search system."""

import argparse

from job_search.memory.database import init_database


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Autonomous Job Search System")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init-db", help="Initialize SQLite/PostgreSQL schema")
    sub.add_parser("scrape", help="Run scrapers for configured sectors")
    sub.add_parser("match", help="Evaluate pending offers against candidate profile")
    sub.add_parser("run", help="Full pipeline: scrape → match → recommend")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "init-db":
        init_database()
        print("Database initialized.")
    elif args.command in {"scrape", "match", "run"}:
        print(f"Command '{args.command}' is not yet implemented.")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
