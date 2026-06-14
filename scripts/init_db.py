#!/usr/bin/env python3
"""Initialize relational database and ChromaDB directories."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from config.settings import get_settings
from job_search.memory.database import init_database
from job_search.memory.vector_store import VectorMemory


def main() -> None:
    settings = get_settings()
    Path("data").mkdir(exist_ok=True)
    init_database()
    VectorMemory(settings)
    print("Relational DB and ChromaDB initialized.")


if __name__ == "__main__":
    main()
