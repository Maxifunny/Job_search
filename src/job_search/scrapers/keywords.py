"""Sector-specific search terms and portal query mappings."""

from dataclasses import dataclass

from job_search.schemas.job_offer import JobSector


@dataclass(frozen=True)
class PortalQuery:
    """Single query configuration for a job portal scraper."""

    portal: str
    value: str


SECTOR_QUERIES: dict[JobSector, dict[str, list[PortalQuery]]] = {
    JobSector.DATA: {
        "justjoin": [
            PortalQuery("justjoin", "data"),
            PortalQuery("justjoin", "analytics"),
        ],
        "pracuj_pl": [
            PortalQuery("pracuj_pl", "data analyst"),
            PortalQuery("pracuj_pl", "data engineer"),
            PortalQuery("pracuj_pl", "data scientist"),
        ],
        "nofluffjobs": [
            PortalQuery("nofluffjobs", "data"),
            PortalQuery("nofluffjobs", "analytics"),
        ],
    },
    JobSector.AUTOMATION: {
        "justjoin": [
            PortalQuery("justjoin", "automation"),
            PortalQuery("justjoin", "plc"),
            PortalQuery("justjoin", "scada"),
        ],
        "pracuj_pl": [
            PortalQuery("pracuj_pl", "automatyk"),
            PortalQuery("pracuj_pl", "programista plc"),
            PortalQuery("pracuj_pl", "inżynier automatyki"),
        ],
        "nofluffjobs": [
            PortalQuery("nofluffjobs", "embedded"),
            PortalQuery("nofluffjobs", "automation"),
        ],
    },
}


def queries_for_sector(sector: JobSector, source: str | None = None) -> list[PortalQuery]:
    """Return configured portal queries for a sector and optional source filter."""
    sector_map = SECTOR_QUERIES[sector]
    if source is not None:
        return list(sector_map.get(source, []))
    queries: list[PortalQuery] = []
    for source_queries in sector_map.values():
        queries.extend(source_queries)
    return queries
