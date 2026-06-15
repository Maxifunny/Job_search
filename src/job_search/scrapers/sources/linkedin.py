"""LinkedIn scraper via public guest jobs search API (HTML fragments)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
import httpx
import structlog
from bs4 import BeautifulSoup, Tag

from config.sector_loader import queries_for_sector, resolve_sector
from config.settings import Settings, get_settings
from job_search.scrapers.base import BaseScraper, ScraperResult
from job_search.scrapers.http_client import ScraperHttpClient
from job_search.schemas.job_offer import JobOfferCreate, JobSector, coerce_sector_id

logger = structlog.get_logger(__name__)

PAGE_SIZE = 25
JOB_ID_PATTERN = re.compile(r"(?:/jobs/view/|jobPosting:)(\d+)")


class LinkedInBlockedError(Exception):
    """Raised when LinkedIn returns 403 or 429."""


def parse_linkedin_search_html(html: str) -> list[dict[str, Any]]:
    """Parse guest search API HTML into raw job card dicts."""
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("div.base-card.job-search-card, li div.base-card")
    if not cards:
        cards = soup.find_all("div", class_="base-card")

    results: list[dict[str, Any]] = []
    for card in cards:
        parsed = _parse_job_card(card)
        if parsed:
            results.append(parsed)
    return results


def _parse_job_card(card: Tag) -> dict[str, Any] | None:
    title_el = card.select_one("h3.base-search-card__title, [class*='_title']")
    company_el = card.select_one("h4.base-search-card__subtitle, [class*='_subtitle']")
    location_el = card.select_one("span.job-search-card__location, [class*='_location']")
    link_el = card.select_one("a.base-card__full-link, [class*='_full-link']")
    snippet_el = card.select_one(
        "p.job-search-card__snippet, [class*='snippet'], [class*='__description']"
    )
    date_el = card.select_one("time.job-search-card__listdate, [class*='listdate']")

    title = title_el.get_text(strip=True) if title_el else None
    company = company_el.get_text(strip=True) if company_el else None
    if not title or not company:
        return None

    link = link_el.get("href") if link_el else None
    job_id = _extract_job_id(card, link)
    if not job_id:
        return None

    location = location_el.get_text(strip=True) if location_el else None
    snippet = snippet_el.get_text(strip=True) if snippet_el else None
    posted_at = None
    if date_el and date_el.get("datetime"):
        posted_at = _parse_datetime(date_el["datetime"])

    url = f"https://www.linkedin.com/jobs/view/{job_id}"
    if link and isinstance(link, str) and link.startswith("http"):
        url = link.split("?")[0]

    return {
        "job_id": job_id,
        "title": title,
        "company": company,
        "location": location,
        "url": url,
        "snippet": snippet,
        "posted_at": posted_at,
    }


def _extract_job_id(card: Tag, link: str | None) -> str | None:
    urn = card.get("data-entity-urn")
    if isinstance(urn, str):
        match = JOB_ID_PATTERN.search(urn)
        if match:
            return match.group(1)

    if link:
        match = JOB_ID_PATTERN.search(link)
        if match:
            return match.group(1)
    return None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class LinkedInScraper(BaseScraper):
    source_name = "linkedin"

    def __init__(
        self,
        http_client: ScraperHttpClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.http = http_client or ScraperHttpClient(self.settings)
        self._owns_client = http_client is None

    def fetch_offers(self, sector: JobSector | str, *, query: str | None = None, **kwargs) -> ScraperResult:
        sector_id = coerce_sector_id(sector)
        queries = [query] if query else self._resolve_queries(sector_id)
        if not queries:
            message = f"No LinkedIn search queries configured for sector '{sector_id}'"
            logger.warning(message)
            return ScraperResult(
                source=self.source_name,
                sector=sector,
                offers=[],
                errors=[message],
            )

        offers: list[JobOfferCreate] = []
        errors: list[str] = []
        seen_ids: set[str] = set()
        max_pages = kwargs.get("max_pages", self.settings.scraper_max_pages)
        max_offers = kwargs.get("max_offers")

        for q in queries:
            if max_offers is not None and len(offers) >= max_offers:
                break
            remaining = None if max_offers is None else max_offers - len(offers)
            try:
                fetched = self._fetch_query(
                    q,
                    sector,
                    max_pages=max_pages,
                    seen_ids=seen_ids,
                    remaining=remaining,
                )
                offers.extend(fetched)
            except LinkedInBlockedError as exc:
                message = str(exc)
                logger.warning(message)
                errors.append(message)
                break
            except Exception as exc:  # noqa: BLE001 - collect per-query errors
                message = f"LinkedIn query '{q}' failed: {exc}"
                logger.warning(message)
                errors.append(message)

        return ScraperResult(source=self.source_name, sector=sector, offers=offers, errors=errors)

    def health_check(self) -> bool:
        url = self.settings.linkedin_guest_api_base
        params = {
            "keywords": "test",
            "location": self.settings.linkedin_jobs_location,
            "start": 0,
        }
        try:
            response = self.http._client.get(url, params=params, timeout=10.0)  # noqa: SLF001
            return response.status_code < 500
        except httpx.HTTPError:
            return False

    def close(self) -> None:
        if self._owns_client:
            self.http.close()

    def _resolve_queries(self, sector_id: str) -> list[str]:
        queries = queries_for_sector(sector_id, self.source_name)
        if queries:
            return queries

        config = resolve_sector(sector_id)
        for portal, portal_queries in config.portal_queries.items():
            if portal != self.source_name and portal_queries:
                return [portal_queries[0]]

        display = config.display_name.strip()
        if display:
            return [display.split("(")[0].strip()]

        return []

    def _fetch_query(
        self,
        query: str,
        sector: JobSector | str,
        *,
        max_pages: int,
        seen_ids: set[str],
        remaining: int | None = None,
    ) -> list[JobOfferCreate]:
        offers: list[JobOfferCreate] = []
        offer_cap = self.settings.scraper_max_offers_per_query
        if remaining is not None:
            offer_cap = min(offer_cap, remaining)
        if offer_cap <= 0:
            return offers

        start = 0
        for _page in range(max_pages):
            if len(offers) >= offer_cap:
                break

            html = self._get_search_html(query, start=start)
            cards = parse_linkedin_search_html(html)
            if not cards:
                break

            for card in cards:
                if len(offers) >= offer_cap:
                    break
                job_id = card["job_id"]
                if job_id in seen_ids:
                    continue
                seen_ids.add(job_id)
                try:
                    offers.append(self._map_offer(card, sector, query))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("linkedin_map_failed", job_id=job_id, error=str(exc))

            if len(offers) >= offer_cap:
                break
            if len(cards) < PAGE_SIZE:
                break
            start += PAGE_SIZE

        return offers

    def _get_search_html(self, query: str, *, start: int) -> str:
        params = {
            "keywords": query,
            "location": self.settings.linkedin_jobs_location,
            "start": start,
        }
        try:
            return self.http.get_text(self.settings.linkedin_guest_api_base, params=params)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {403, 429}:
                raise LinkedInBlockedError(
                    f"LinkedIn blocked request (HTTP {exc.response.status_code}); "
                    "try again later or use a residential IP"
                ) from exc
            raise

    def _map_offer(
        self,
        card: dict[str, Any],
        sector: JobSector | str,
        query: str,
    ) -> JobOfferCreate:
        description = card.get("snippet") or card["title"]
        remote = _guess_remote(card.get("location"))

        return JobOfferCreate(
            external_id=card["job_id"],
            source=self.source_name,
            title=card["title"],
            company=card["company"],
            location=card.get("location"),
            sector=coerce_sector_id(sector),
            description=description,
            requirements=None,
            skills=[],
            salary_min=None,
            salary_max=None,
            currency=None,
            employment_type=None,
            remote=remote,
            url=card["url"],
            posted_at=card.get("posted_at"),
            raw_payload={"card": card, "query": query},
        )


def _guess_remote(location: str | None) -> bool | None:
    if not location:
        return None
    lowered = location.lower()
    if "remote" in lowered or "zdaln" in lowered:
        return True
    return None
