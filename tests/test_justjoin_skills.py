"""Tests for JustJoin skill normalization."""

from job_search.scrapers.sources.justjoin import _normalize_skills


def test_normalize_skills_from_name_and_level_objects():
    raw = [
        {"name": "GenAI", "level": 4},
        {"name": "Python", "level": 3},
        {"label": "SQL"},
        "Databricks",
    ]
    assert _normalize_skills(raw) == ["GenAI", "Python", "SQL", "Databricks"]


def test_normalize_skills_deduplicates():
    raw = [{"name": "Python"}, {"label": "Python"}, "Python"]
    assert _normalize_skills(raw) == ["Python"]
