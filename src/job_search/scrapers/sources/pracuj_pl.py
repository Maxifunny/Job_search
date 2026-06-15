"""Pracuj.pl scraper using HTML search results and offer detail pages."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

import structlog

from config.settings import Settings, get_settings
from job_search.scrapers.base import BaseScraper, ScraperResult
from job_search.scrapers.http_client import ScraperHttpClient
from job_search.scrapers.parsers import extract_pracuj_offer_links, parse_pracuj_offer_page
from job_search.schemas.job_offer import JobOfferCreate, JobSector

logger = structlog.get_logger(__name__)


class PracujPlScraper(BaseScraper):
    source_name = "pracuj_pl"

    def __init__(
        self,
        http_client: ScraperHttpClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.http = http_client or ScraperHttpClient(self.settings)
        self._owns_client = http_client is None

    def fetch_offers(self, sector: JobSector, *, query: str | None = None, **kwargs) -> ScraperResult:
        queries = [query] if query else self._default_queries(sector)
        offers: list[JobOfferCreate] = []
        errors: list[str] = []
        seen_ids: set[str] = set()
        max_pages = kwargs.get("max_pages", self.settings.scraper_max_pages)

        for q in queries:
            try:
                fetched = self._fetch_query(q, sector, max_pages=max_pages, seen_ids=seen_ids)
                offers.extend(fetched)
            except Exception as exc:  # noqa: BLE001
                message = f"Pracuj.pl query '{q}' failed: {exc}"
                logger.warning(message)
                errors.append(message)

        return ScraperResult(source=self.source_name, sector=sector, offers=offers, errors=errors)

    def health_check(self) -> bool:
        return self.http.health_check(f"{self.settings.pracuj_pl_base_url}/praca/it;kw")

    def close(self) -> None:
        if self._owns_client:
            self.http.close()

    def _default_queries(self, sector: JobSector) -> list[str]:
        if sector == JobSector.DATA:
            return ["data analyst", "data engineer", "data scientist"]
        return ["automatyk", "programista plc", "inżynier automatyki"]

    def _fetch_query(
        self,
        query: str,
        sector: JobSector,
        *,
        max_pages: int,
        seen_ids: set[str],
    ) -> list[JobOfferCreate]:
        offers: list[JobOfferCreate] = []
        encoded = quote(query)

        for page in range(1, max_pages + 1):
            search_url = f"{self.settings.pracuj_pl_base_url}/praca/{encoded};kw?pn={page}"
            html = self.http.get_text(search_url)

            if "Just a moment" in html or "cf-challenge" in html.lower():
                raise RuntimeError(
                    "Pracuj.pl blocked the request (Cloudflare). "
                    "Run the scraper from a home network or increase SCRAPER_REQUEST_DELAY_SECONDS."
                )

            links = extract_pracuj_offer_links(html, self.settings.pracuj_pl_base_url)
            if not links:
                break

            for link in links[: self.settings.scraper_max_offers_per_query]:
                offer_id = link.split(",oferta,")[-1].split("?")[0]
                if offer_id in seen_ids:
                    continue
                seen_ids.add(offer_id)
                try:
                    detail_html = self.http.get_text(link)
                    parsed = parse_pracuj_offer_page(detail_html, link)
                    offers.append(
                        JobOfferCreate(
                            source=self.source_name,
                            sector=sector,
                            currency="PLN",
                            employment_type=None,
                            posted_at=datetime.now(),
                            raw_payload={"query": query, "search_url": search_url},
                            **parsed,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("pracuj_offer_failed", url=link, error=str(exc))

        return offers
