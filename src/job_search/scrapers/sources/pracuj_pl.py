"""Pracuj.pl scraper (stub — implement in Scraper Agent task)."""

from job_search.scrapers.base import BaseScraper, ScraperResult
from job_search.schemas.job_offer import JobSector


class PracujPlScraper(BaseScraper):
    source_name = "pracuj_pl"

    def fetch_offers(self, sector: JobSector, **kwargs) -> ScraperResult:
        raise NotImplementedError("Implement in Scraper Agent branch")

    def health_check(self) -> bool:
        return False
