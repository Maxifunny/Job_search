"""Tests for Streamlit UI data access helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ui.data_access import (
    database_path_from_url,
    fetch_latest_status,
    fetch_offers,
    fetch_recommendations,
)


def _prepare_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE job_offers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                sector TEXT NOT NULL,
                company TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_offer_id INTEGER NOT NULL,
                candidate_name TEXT NOT NULL,
                recommended_at TEXT NOT NULL
            );

            CREATE TABLE scrape_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                sector TEXT NOT NULL,
                started_at TEXT NOT NULL,
                offers_found INTEGER NOT NULL,
                offers_new INTEGER NOT NULL,
                offers_updated INTEGER NOT NULL,
                status TEXT NOT NULL
            );

            CREATE TABLE match_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_offer_id INTEGER NOT NULL,
                decision TEXT NOT NULL,
                llm_score REAL,
                semantic_score REAL,
                evaluated_at TEXT NOT NULL
            );
            """
        )

        conn.execute(
            """
            INSERT INTO job_offers (source, sector, company, title, url, last_seen_at, is_active)
            VALUES
            ('justjoin', 'data', 'Acme', 'Data Engineer', 'https://example.com/1', '2026-06-17T08:00:00', 1),
            ('linkedin', 'automation', 'Beta', 'Automation Engineer', 'https://example.com/2', '2026-06-17T09:00:00', 1)
            """
        )

        conn.execute(
            """
            INSERT INTO recommendations (job_offer_id, candidate_name, recommended_at)
            VALUES (1, 'default', '2026-06-17T10:00:00')
            """
        )

        conn.execute(
            """
            INSERT INTO scrape_runs (source, sector, started_at, offers_found, offers_new, offers_updated, status)
            VALUES
            ('justjoin', 'data', '2026-06-17T10:00:00', 10, 8, 2, 'ok'),
            ('linkedin', 'data', '2026-06-17T10:00:00', 5, 1, 1, 'error')
            """
        )

        conn.execute(
            """
            INSERT INTO match_results (job_offer_id, decision, llm_score, semantic_score, evaluated_at)
            VALUES
            (1, 'accepted', 0.91, 0.88, '2026-06-17T10:05:00'),
            (2, 'rejected', 0.25, 0.40, '2026-06-17T10:05:00')
            """
        )
        conn.commit()


def test_database_path_from_sqlite_url_resolves_relative_path():
    db_path = database_path_from_url("sqlite:///./data/job_search.db")
    assert db_path is not None
    assert db_path.name == "job_search.db"
    assert db_path.is_absolute()


def test_database_path_from_non_sqlite_url_returns_none():
    assert database_path_from_url("postgresql://localhost/test") is None


def test_fetch_latest_status_aggregates_data(tmp_path: Path):
    db_path = tmp_path / "ui_test.db"
    _prepare_db(db_path)

    status = fetch_latest_status(db_path)

    assert status["scraped"] == 15
    assert status["new"] == 9
    assert status["updated"] == 3
    assert status["evaluated"] == 2
    assert status["accepted"] == 1
    assert status["rejected"] == 1
    assert status["errors"] == 1


def test_fetch_recommendations_returns_joined_rows(tmp_path: Path):
    db_path = tmp_path / "ui_test.db"
    _prepare_db(db_path)

    rows = fetch_recommendations(db_path, sector="data", source="justjoin")

    assert len(rows) == 1
    assert rows[0]["company"] == "Acme"
    assert rows[0]["decision"] == "accepted"


def test_fetch_offers_applies_filters(tmp_path: Path):
    db_path = tmp_path / "ui_test.db"
    _prepare_db(db_path)

    rows = fetch_offers(db_path, source="linkedin")

    assert len(rows) == 1
    assert rows[0]["title"] == "Automation Engineer"
