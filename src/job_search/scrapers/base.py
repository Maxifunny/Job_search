"""Abstract base class for all job portal scrapers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from job_search.schemas.job_offer import JobOfferCreate, JobSector, coerce_sector_id


@dataclass
class ScraperResult:
    """Normalized output of a single scraper run."""

    source: str
    sector: JobSector | str
    offers: list[JobOfferCreate] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class BaseScraper(ABC):
    """Interface every portal scraper must implement."""

    source_name: str

    @abstractmethod
    def fetch_offers(self, sector: JobSector | str, **kwargs) -> ScraperResult:
        """Retrieve raw offers for a given sector."""

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the data source is reachable."""
