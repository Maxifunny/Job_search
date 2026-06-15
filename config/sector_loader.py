"""Load job sector definitions from JSON config files."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field


class SectorConfigError(ValueError):
    """Raised when a sector config file is missing or invalid."""


class SectorConfig(BaseModel):
    """Sector definition: portal queries and false-positive filter rules."""

    id: str = Field(..., description="Slug identifier, e.g. data, automation")
    display_name: str
    portal_queries: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Portal name → search query strings (linkedin optional)",
    )
    false_positive_title_keywords: list[str] = Field(default_factory=list)
    required_skill_keywords: list[str] = Field(default_factory=list)


def _sectors_dir() -> Path:
    return Path(__file__).resolve().parent / "sectors"


def list_sector_ids() -> list[str]:
    """Return sorted sector slugs discovered in config/sectors/."""
    directory = _sectors_dir()
    if not directory.is_dir():
        return []
    return sorted(path.stem for path in directory.glob("*.json"))


@lru_cache(maxsize=32)
def load_sector_config(sector_id: str) -> SectorConfig:
    """Load and validate a sector JSON file by slug."""
    path = _sectors_dir() / f"{sector_id}.json"
    if not path.is_file():
        raise SectorConfigError(f"Unknown sector: {sector_id!r} (expected {path})")

    data = json.loads(path.read_text(encoding="utf-8"))
    if "id" not in data:
        data["id"] = sector_id
    elif data["id"] != sector_id:
        raise SectorConfigError(
            f"Sector id mismatch in {path.name}: file id={data['id']!r}, expected {sector_id!r}"
        )

    return SectorConfig.model_validate(data)


def resolve_sector(sector_id: str) -> SectorConfig:
    """Return sector config, raising SectorConfigError if not found."""
    return load_sector_config(sector_id)


def queries_for_sector(sector_id: str, source: str) -> list[str]:
    """Return portal search queries for a sector and scraper source name."""
    config = resolve_sector(sector_id)
    return list(config.portal_queries.get(source, []))
