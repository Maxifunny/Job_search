"""Tests for configurable sector definitions."""

import pytest

from config.sector_loader import (
    SectorConfigError,
    list_sector_ids,
    load_sector_config,
    queries_for_sector,
    resolve_sector,
)


def test_list_sector_ids_includes_built_ins():
    ids = list_sector_ids()
    assert "data" in ids
    assert "automation" in ids
    assert "example" in ids


def test_load_data_sector_config():
    config = load_sector_config("data")
    assert config.id == "data"
    assert config.display_name
    assert "justjoin" in config.portal_queries
    assert "data" in config.portal_queries["justjoin"]
    assert "data entry" in config.false_positive_title_keywords
    assert "python" in config.required_skill_keywords


def test_resolve_sector_returns_same_as_load():
    assert resolve_sector("automation").id == "automation"


def test_queries_for_sector_source():
    queries = queries_for_sector("data", "justjoin")
    assert queries == ["data", "analytics", "python"]


def test_invalid_sector_id_raises():
    with pytest.raises(SectorConfigError, match="Unknown sector"):
        load_sector_config("not-a-real-sector")
