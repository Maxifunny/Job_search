"""Sector-specific search terms and portal query mappings."""

from __future__ import annotations

from dataclasses import dataclass

from config.sector_loader import queries_for_sector as _queries_for_sector
from job_search.schemas.job_offer import JobSector, coerce_sector_id


@dataclass(frozen=True)
class PortalQuery:
    """Single query configuration for a job portal scraper."""

    portal: str
    value: str


def queries_for_sector(
    sector: JobSector | str,
    source: str | None = None,
) -> list[PortalQuery]:
    """Return configured portal queries for a sector and optional source filter."""
    sector_id = coerce_sector_id(sector)
    if source is not None:
        return [
            PortalQuery(source, query)
            for query in _queries_for_sector(sector_id, source)
        ]

    from config.sector_loader import resolve_sector

    config = resolve_sector(sector_id)
    queries: list[PortalQuery] = []
    for portal, portal_queries in config.portal_queries.items():
        for query in portal_queries:
            queries.append(PortalQuery(portal, query))
    return queries
