#!/usr/bin/env python3
"""Verify PostgreSQL connectivity using Docker Compose (optional prod setup)."""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text

from job_search.memory.database import create_db_engine, init_database


def main() -> int:
    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg2://jobsearch:jobsearch@localhost:5432/job_search",
    )
    compose_file = Path(__file__).resolve().parent / "docker-compose.postgres.yml"

    print(f"Starting PostgreSQL via {compose_file.name} ...")
    subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "up", "-d", "--wait"],
        check=True,
    )

    print(f"Connecting with DATABASE_URL={database_url}")
    engine = create_db_engine(database_url)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).scalar_one()
        assert result == 1

    init_database(engine)
    print("PostgreSQL connection OK; schema initialized.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"Docker Compose failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except Exception as exc:
        print(f"PostgreSQL test failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
