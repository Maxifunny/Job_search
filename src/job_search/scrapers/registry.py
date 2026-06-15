"""Scraper registry and execution helpers."""

from __future__ import annotations

from job_search.scrapers.base import BaseScraper, ScraperResult
from job_search.scrapers.sources.justjoin import JustJoinScraper
from job_search.scrapers.sources.nofluffjobs import NoFluffJobsScraper
from job_search.scrapers.sources.pracuj_pl import PracujPlScraper
from job_search.schemas.job_offer import JobSector

SCRAPER_REGISTRY: dict[str, type[BaseScraper]] = {
    JustJoinScraper.source_name: JustJoinScraper,
    PracujPlScraper.source_name: PracujPlScraper,
    NoFluffJobsScraper.source_name: NoFluffJobsScraper,
}


def get_scraper(source: str) -> BaseScraper:
    """Instantiate a scraper by source name."""
    try:
        scraper_cls = SCRAPER_REGISTRY[source]
    except KeyError as exc:
        known = ", ".join(sorted(SCRAPER_REGISTRY))
        raise ValueError(f"Unknown scraper source '{source}'. Known sources: {known}") from exc
    return scraper_cls()


def list_sources() -> list[str]:
    return sorted(SCRAPER_REGISTRY.keys())


def run_scraper(source: str, sector: JobSector, **kwargs) -> ScraperResult:
    scraper = get_scraper(source)
    try:
        return scraper.fetch_offers(sector, **kwargs)
    finally:
        close = getattr(scraper, "close", None)
        if callable(close):
            close()


def run_all_scrapers(sector: JobSector, *, source: str | None = None, **kwargs) -> list[ScraperResult]:
    sources = [source] if source else list_sources()
    results: list[ScraperResult] = []
    for name in sources:
        results.append(run_scraper(name, sector, **kwargs))
    return results
