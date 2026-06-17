"""Helpers for safe read-only access to SQLite data for the Streamlit UI."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from config.sector_loader import list_sector_ids, resolve_sector
from config.settings import get_settings

SUPPORTED_SOURCES = ("justjoin", "pracuj_pl", "nofluffjobs", "linkedin")


def get_repo_root() -> Path:
    """Return project root (parent of ui/)."""
    return Path(__file__).resolve().parents[1]


def list_sectors_for_ui() -> list[tuple[str, str]]:
    """Return sectors as (id, display_name) pairs."""
    sectors: list[tuple[str, str]] = []
    for sector_id in list_sector_ids():
        config = resolve_sector(sector_id)
        sectors.append((sector_id, config.display_name))
    return sectors


def _profile_label_from_path(relative_path: str) -> str:
    """Create a friendly profile label from profile file name."""
    name = Path(relative_path).stem.replace("_", " ").replace("-", " ").strip()
    if not name:
        return relative_path
    return name[:1].upper() + name[1:]


def list_profiles_for_ui() -> list[tuple[str, str]]:
    """Return profiles as (path, friendly_label) pairs."""
    profiles_dir = get_repo_root() / "config" / "profiles"
    if not profiles_dir.is_dir():
        return []
    items: list[tuple[str, str]] = []
    for path in sorted(profiles_dir.glob("*.json")):
        relative_path = str(path.relative_to(get_repo_root())).replace("\\", "/")
        items.append((relative_path, _profile_label_from_path(relative_path)))
    return items


def detect_env_status() -> tuple[bool, bool]:
    """Return (.env exists, LLM_API_KEY present) without exposing secrets."""
    repo_root = get_repo_root()
    env_exists = (repo_root / ".env").is_file()
    key_present = bool(get_settings().llm_api_key.strip())
    return env_exists, key_present


def database_path_from_url(database_url: str | None = None) -> Path | None:
    """Resolve sqlite file path from DATABASE_URL.

    Returns None for non-SQLite backends.
    """
    url = database_url or get_settings().database_url
    if not url.startswith("sqlite:"):
        return None

    if url.startswith("sqlite:///"):
        raw = url.removeprefix("sqlite:///")
    elif url.startswith("sqlite://"):
        raw = url.removeprefix("sqlite://")
    else:
        return None

    parsed = urlparse(raw)
    if parsed.scheme and parsed.scheme != "file":
        return None

    path_value = parsed.path or raw
    if parsed.query:
        query = parse_qs(parsed.query)
        if "path" in query and query["path"]:
            path_value = query["path"][0]

    path = Path(path_value)
    if not path.is_absolute():
        path = (get_repo_root() / path).resolve()
    return path


def _read_only_connection(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _run_query(db_path: Path, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    try:
        with _read_only_connection(db_path) as connection:
            cursor = connection.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except sqlite3.Error:
        return []


def fetch_latest_status(db_path: Path) -> dict[str, int]:
    """Return latest scrape + match counters."""
    default = {
        "scraped": 0,
        "new": 0,
        "updated": 0,
        "evaluated": 0,
        "accepted": 0,
        "rejected": 0,
        "skipped": 0,
        "errors": 0,
    }

    scrape_rows = _run_query(
        db_path,
        """
        WITH latest_run AS (
            SELECT MAX(started_at) AS started_at
            FROM scrape_runs
        )
        SELECT
            COALESCE(SUM(offers_found), 0) AS scraped,
            COALESCE(SUM(offers_new), 0) AS new_count,
            COALESCE(SUM(offers_updated), 0) AS updated_count,
            COALESCE(SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END), 0) AS errors_count
        FROM scrape_runs
        WHERE started_at = (SELECT started_at FROM latest_run)
        """,
    )

    match_rows = _run_query(
        db_path,
        """
        SELECT
            COALESCE(COUNT(*), 0) AS evaluated,
            COALESCE(SUM(CASE WHEN decision = 'accepted' THEN 1 ELSE 0 END), 0) AS accepted,
            COALESCE(SUM(CASE WHEN decision = 'rejected' THEN 1 ELSE 0 END), 0) AS rejected,
            COALESCE(SUM(CASE WHEN decision = 'skipped' THEN 1 ELSE 0 END), 0) AS skipped
        FROM match_results
        WHERE evaluated_at = (SELECT MAX(evaluated_at) FROM match_results)
        """,
    )

    if scrape_rows:
        row = scrape_rows[0]
        default["scraped"] = int(row.get("scraped", 0) or 0)
        default["new"] = int(row.get("new_count", 0) or 0)
        default["updated"] = int(row.get("updated_count", 0) or 0)
        default["errors"] = int(row.get("errors_count", 0) or 0)
    if match_rows:
        row = match_rows[0]
        default["evaluated"] = int(row.get("evaluated", 0) or 0)
        default["accepted"] = int(row.get("accepted", 0) or 0)
        default["rejected"] = int(row.get("rejected", 0) or 0)
        default["skipped"] = int(row.get("skipped", 0) or 0)
    return default


def fetch_recommendations(
    db_path: Path,
    *,
    sector: str | None = None,
    source: str | None = None,
    text_query: str = "",
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return recommendations joined with offers and latest match decision."""
    filters: list[str] = []
    params: list[Any] = []

    if sector:
        filters.append("o.sector = ?")
        params.append(sector)
    if source:
        filters.append("o.source = ?")
        params.append(source)
    if text_query.strip():
        filters.append("(LOWER(o.title) LIKE ? OR LOWER(o.company) LIKE ?)")
        q = f"%{text_query.lower().strip()}%"
        params.extend([q, q])

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    params.append(limit)

    return _run_query(
        db_path,
        f"""
        WITH latest_match AS (
            SELECT m1.*
            FROM match_results m1
            JOIN (
                SELECT job_offer_id, MAX(evaluated_at) AS max_evaluated
                FROM match_results
                GROUP BY job_offer_id
            ) m2
            ON m1.job_offer_id = m2.job_offer_id
            AND m1.evaluated_at = m2.max_evaluated
        )
        SELECT
            o.id AS offer_id,
            r.recommended_at,
            r.candidate_name,
            o.source,
            o.sector,
            o.company,
            o.title,
            o.url,
            lm.decision,
            lm.llm_score,
            lm.semantic_score
        FROM recommendations r
        JOIN job_offers o ON o.id = r.job_offer_id
        LEFT JOIN latest_match lm ON lm.job_offer_id = o.id
        {where_clause}
        ORDER BY r.recommended_at DESC
        LIMIT ?
        """,
        tuple(params),
    )


def fetch_offers(
    db_path: Path,
    *,
    sector: str | None = None,
    source: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return latest offers table for the UI."""
    filters: list[str] = []
    params: list[Any] = []

    if sector:
        filters.append("sector = ?")
        params.append(sector)
    if source:
        filters.append("source = ?")
        params.append(source)

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    params.append(limit)

    return _run_query(
        db_path,
        f"""
        SELECT
            id AS offer_id,
            last_seen_at,
            sector,
            source,
            company,
            title,
            url,
            is_active
        FROM job_offers
        {where_clause}
        ORDER BY last_seen_at DESC
        LIMIT ?
        """,
        tuple(params),
    )
