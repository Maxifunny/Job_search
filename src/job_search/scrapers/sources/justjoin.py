"""JustJoin.it scraper via candidate-api."""

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


class JustJoinScraper(BaseScraper):
    source_name = "justjoin"

    CATEGORY_KEYS = {"data", "analytics", "python", "devops", "architecture", "pm", "other"}
    SEARCH_KEYS = {"automation", "plc", "scada", "automatyk"}

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
        seen_slugs: set[str] = set()
        max_pages = kwargs.get("max_pages", self.settings.scraper_max_pages)
        max_offers = kwargs.get("max_offers", self.settings.scraper_max_offers_per_query)

        for q in queries:
            try:
                fetched = self._fetch_query(
                    q,
                    sector,
                    max_pages=max_pages,
                    seen_slugs=seen_slugs,
                    max_offers=max_offers,
                )
                offers.extend(fetched)
            except Exception as exc:  # noqa: BLE001 - collect per-query errors
                message = f"JustJoin query '{q}' failed: {exc}"
                logger.warning(message)
                errors.append(message)

        return ScraperResult(source=self.source_name, sector=sector, offers=offers, errors=errors)

    def health_check(self) -> bool:
        return self.http.health_check(f"{self.settings.justjoin_api_base}/offers?itemsCount=1")

    def close(self) -> None:
        if self._owns_client:
            self.http.close()

    def _default_queries(self, sector: JobSector) -> list[str]:
        if sector == JobSector.DATA:
            return ["data", "analytics"]
        return ["automation", "plc", "scada"]

    def _fetch_query(
        self,
        query: str,
        sector: JobSector,
        *,
        max_pages: int,
        seen_slugs: set[str],
        max_offers: int | None = None,
    ) -> list[JobOfferCreate]:
        offers: list[JobOfferCreate] = []
        cursor = 0
        pages = 0
        offer_limit = max_offers or self.settings.scraper_max_offers_per_query

        while pages < max_pages:
            if len(offers) >= offer_limit:
                break

            params: dict[str, Any] = {
                "itemsCount": min(
                    self.settings.scraper_items_per_page,
                    offer_limit - len(offers),
                ),
                "from": cursor,
            }
            if query in self.CATEGORY_KEYS:
                params["categories"] = query
            else:
                params["search"] = query

            payload = self.http.get_json(f"{self.settings.justjoin_api_base}/offers", params=params)
            batch = payload.get("data", [])
            if not batch:
                break

            for item in batch:
                if len(offers) >= offer_limit:
                    break

                slug = item.get("slug")
                if not slug or slug in seen_slugs:
                    continue
                seen_slugs.add(slug)
                title = item.get("title", slug)
                print(
                    f"[justjoin] Pobieram {len(offers) + 1}/{offer_limit}: {title}",
                    flush=True,
                )
                try:
                    offers.append(self._map_offer(item, sector, query))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("justjoin_map_failed", slug=slug, error=str(exc))

            meta = payload.get("meta", {})
            next_cursor = meta.get("next", {}).get("cursor")
            if next_cursor is None:
                break
            cursor = next_cursor
            pages += 1

        return offers

    def _map_offer(self, item: dict[str, Any], sector: JobSector, query: str) -> JobOfferCreate:
        slug = item["slug"]
        detail = self.http.get_json(f"{self.settings.justjoin_api_base}/offers/{slug}")
        description = html_to_text(detail.get("body"))
        requirements = html_to_text(detail.get("requirements")) or None
        skills = _normalize_skills(
            detail.get("requiredSkills", []) + detail.get("niceToHaveSkills", [])
        )
        salary_min, salary_max, currency = _extract_salary(detail.get("employmentTypes", []))
        workplace = detail.get("workplaceType") or item.get("workplaceType")
        posted_at = _parse_datetime(item.get("publishedAt") or detail.get("publishedAt"))

        return JobOfferCreate(
            external_id=item.get("guid") or slug,
            source=self.source_name,
            title=item.get("title") or detail.get("title"),
            company=item.get("companyName") or detail.get("companyName"),
            location=item.get("city") or detail.get("city"),
            sector=sector,
            description=description or item.get("title", ""),
            requirements=requirements,
            skills=skills,
            salary_min=salary_min,
            salary_max=salary_max,
            currency=currency,
            employment_type=_extract_employment_type(detail.get("employmentTypes", [])),
            remote=workplace in {"remote", "fully_remote"},
            url=f"https://justjoin.it/offers/{slug}",
            posted_at=posted_at,
            raw_payload={"list_item": item, "detail": detail, "query": query},
        )


def _normalize_skills(raw_skills: list[Any]) -> list[str]:
    """Map JustJoin skill objects to plain string names."""
    skills: list[str] = []
    seen: set[str] = set()

    for skill in raw_skills:
        name: str | None = None
        if isinstance(skill, str):
            name = skill.strip()
        elif isinstance(skill, dict):
            for key in ("label", "name", "skill", "title"):
                value = skill.get(key)
                if value:
                    name = str(value).strip()
                    break

        if name and name not in seen:
            seen.add(name)
            skills.append(name)

    return skills


def _extract_salary(employment_types: list[dict[str, Any]]) -> tuple[float | None, float | None, str | None]:
    for item in employment_types:
        currency = item.get("currency")
        if currency not in {None, "PLN"}:
            continue
        return item.get("from"), item.get("to"), "PLN"
    if employment_types:
        first = employment_types[0]
        return first.get("from"), first.get("to"), first.get("currency")
    return None, None, None


def _extract_employment_type(employment_types: list[dict[str, Any]]) -> str | None:
    if not employment_types:
        return None
    return employment_types[0].get("type")


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
