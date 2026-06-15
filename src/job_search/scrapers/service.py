"""Persist scraped offers via the memory layer."""

from __future__ import annotations

from dataclasses import dataclass, field

from config.settings import get_settings
from job_search.memory.database import get_session
from job_search.memory.embeddings import EmbeddingService
from job_search.memory.repositories import JobOfferRepository, ScrapeRunRepository
from job_search.memory.vector_store import VectorMemory
from job_search.scrapers.base import ScraperResult
from job_search.scrapers.registry import run_all_scrapers, run_scraper
from job_search.schemas.job_offer import JobSector, coerce_sector_id


@dataclass
class ScrapeSummary:
    source: str
    sector: str
    offers_found: int = 0
    offers_new: int = 0
    offers_updated: int = 0
    errors: list[str] = field(default_factory=list)


def scrape_and_persist(
    sector: JobSector | str,
    *,
    source: str | None = None,
    sync_vectors: bool = False,
    **kwargs,
) -> list[ScrapeSummary]:
    """Run scraper(s), upsert offers, and record scrape runs."""
    sector_id = coerce_sector_id(sector)
    results = (
        [run_scraper(source, sector, **kwargs)]
        if source
        else run_all_scrapers(sector, **kwargs)
    )
    summaries: list[ScrapeSummary] = []

    with get_session() as session:
        settings = get_settings()
        vector_memory = VectorMemory(settings) if sync_vectors else None
        embedding_service = EmbeddingService(session=session, settings=settings) if sync_vectors else None
        offer_repo = JobOfferRepository(
            session,
            vector_memory=vector_memory,
            embedding_service=embedding_service,
        )
        scrape_repo = ScrapeRunRepository(session)

        for result in results:
            summary = ScrapeSummary(
                source=result.source,
                sector=coerce_sector_id(result.sector),
                errors=list(result.errors),
            )
            run = scrape_repo.start_run(result.source, sector_id)
            status = "success" if not result.errors or result.offers else "partial"

            for offer in result.offers:
                _, is_new = offer_repo.upsert(offer)
                summary.offers_found += 1
                if is_new:
                    summary.offers_new += 1
                else:
                    summary.offers_updated += 1

            if result.errors and not result.offers:
                status = "failed"

            scrape_repo.finish_run(
                run,
                offers_found=summary.offers_found,
                offers_new=summary.offers_new,
                offers_updated=summary.offers_updated,
                status=status,
                error_message="; ".join(result.errors) if result.errors else None,
            )
            summaries.append(summary)

    return summaries
