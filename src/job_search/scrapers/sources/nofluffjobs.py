"""NoFluffJobs scraper via public posting API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from config.settings import Settings, get_settings
from job_search.scrapers.base import BaseScraper, ScraperResult
from job_search.scrapers.http_client import ScraperHttpClient
from job_search.scrapers.parsers import html_to_text
from job_search.schemas.job_offer import JobOfferCreate, JobSector

logger = structlog.get_logger(__name__)


class NoFluffJobsScraper(BaseScraper):
    source_name = "nofluffjobs"

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
            except Exception as exc:  # noqa: BLE001
                message = f"NoFluffJobs query '{q}' failed: {exc}"
                logger.warning(message)
                errors.append(message)

        return ScraperResult(source=self.source_name, sector=sector, offers=offers, errors=errors)

    def health_check(self) -> bool:
        return self.http.health_check(f"{self.settings.nofluffjobs_api_base}/posting?limit=1")

    def close(self) -> None:
        if self._owns_client:
            self.http.close()

    def _default_queries(self, sector: JobSector) -> list[str]:
        if sector == JobSector.DATA:
            return ["data", "analytics"]
        return ["embedded", "automation"]

    def _fetch_query(
        self,
        query: str,
        sector: JobSector,
        *,
        max_pages: int,
        seen_ids: set[str],
        remaining: int | None = None,
    ) -> list[JobOfferCreate]:
        offers: list[JobOfferCreate] = []
        offset = 0
        limit = self.settings.scraper_items_per_page
        offer_cap = self.settings.scraper_max_offers_per_query
        if remaining is not None:
            offer_cap = min(offer_cap, remaining)
        if offer_cap <= 0:
            return offers

        for _page in range(max_pages):
            if len(offers) >= offer_cap:
                break
            params = {"limit": limit, "offset": offset, "criteria": f"category={query}"}
            payload = self.http.get_json(f"{self.settings.nofluffjobs_api_base}/posting", params=params)
            postings = payload.get("postings", [])
            if not postings:
                break

            for posting in postings:
                if len(offers) >= offer_cap:
                    break
                posting_id = posting.get("id")
                if not posting_id or posting_id in seen_ids:
                    continue
                seen_ids.add(posting_id)
                try:
                    detail = self.http.get_json(
                        f"{self.settings.nofluffjobs_api_base}/posting/{posting_id}"
                    )
                    offers.append(self._map_offer(posting, detail, sector, query))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("nofluffjobs_map_failed", posting_id=posting_id, error=str(exc))

            if len(offers) >= offer_cap:
                break
            if len(postings) < limit:
                break
            offset += limit

        return offers

    def _map_offer(
        self,
        posting: dict[str, Any],
        detail: dict[str, Any],
        sector: JobSector,
        query: str,
    ) -> JobOfferCreate:
        title = detail.get("title") or posting.get("title") or posting.get("name")
        company = _company_name(posting, detail)
        location = _first_city(posting)
        description_parts = detail.get("specs", {}).get("dailyTasks", [])
        description = "\n".join(description_parts) if description_parts else title
        requirements_raw = detail.get("requirements")
        if isinstance(requirements_raw, dict):
            requirements = None
        else:
            requirements = html_to_text(requirements_raw) or None
        skills = _extract_skills(detail)
        salary_min, salary_max = _extract_salary(detail)
        remote = _is_remote(posting)

        return JobOfferCreate(
            external_id=posting["id"],
            source=self.source_name,
            title=title,
            company=company,
            location=location,
            sector=sector,
            description=description,
            requirements=requirements,
            skills=skills,
            salary_min=salary_min,
            salary_max=salary_max,
            currency="PLN",
            employment_type=None,
            remote=remote,
            url=f"https://nofluffjobs.com/job/{posting['id']}",
            posted_at=datetime.now(),
            raw_payload={"posting": posting, "detail": detail, "query": query},
        )


def _company_name(posting: dict[str, Any], detail: dict[str, Any]) -> str:
    if detail.get("company", {}).get("name"):
        return detail["company"]["name"]
    return posting.get("name") or posting.get("companyName") or "Unknown company"


def _first_city(posting: dict[str, Any]) -> str | None:
    places = posting.get("location", {}).get("places", [])
    if not places:
        return None
    return places[0].get("city")


def _extract_skills(detail: dict[str, Any]) -> list[str]:
    skills: list[str] = []
    for block in detail.get("requirements", {}).get("skills", []):
        if isinstance(block, dict):
            value = block.get("name") or block.get("skill")
            if value:
                skills.append(str(value))
        elif isinstance(block, str):
            skills.append(block)
    technology = detail.get("basics", {}).get("technology")
    if technology and technology not in skills:
        skills.insert(0, str(technology))
    return skills


def _extract_salary(detail: dict[str, Any]) -> tuple[float | None, float | None]:
    salary = detail.get("salary") or {}
    return salary.get("from"), salary.get("to")


def _is_remote(posting: dict[str, Any]) -> bool:
    fully_remote = posting.get("location", {}).get("fullyRemote")
    if fully_remote is not None:
        return bool(fully_remote)
    return False
