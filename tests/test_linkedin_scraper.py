"""Unit tests for LinkedIn guest API scraper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import httpx

from config.settings import Settings
from job_search.scrapers.sources.linkedin import (
    LinkedInScraper,
    parse_linkedin_search_html,
)
from job_search.schemas.job_offer import JobSector

FIXTURES = Path(__file__).parent / "fixtures"
SEARCH_HTML = (FIXTURES / "linkedin_search.html").read_text(encoding="utf-8")
API_BASE = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"


class MockLinkedInHttp:
    """Mock HTTP client that returns fixture HTML for search requests."""

    def __init__(self, html: str = SEARCH_HTML) -> None:
        self.html = html
        self.search_calls = 0

    def get_text(self, url: str, *, params=None) -> str:
        if url.startswith(API_BASE):
            self.search_calls += 1
            return self.html
        raise KeyError(f"No mock route for {url}")

    def health_check(self, url: str) -> bool:
        return True

    def close(self) -> None:
        return None


class BlockingLinkedInHttp:
    """Mock HTTP client that simulates LinkedIn rate limiting."""

    def get_text(self, url: str, *, params=None) -> str:
        request = httpx.Request("GET", url, params=params or {})
        response = httpx.Response(403, request=request)
        raise httpx.HTTPStatusError("blocked", request=request, response=response)

    def close(self) -> None:
        return None


def test_parse_fixture_html_extracts_job_fields():
    cards = parse_linkedin_search_html(SEARCH_HTML)

    assert len(cards) == 5
    first = cards[0]
    assert first["job_id"] == "4000000001"
    assert first["title"] == "Data Engineer"
    assert first["company"] == "Acme Corp"
    assert first["location"] == "Warsaw, Mazowieckie, Poland"
    assert first["url"] == "https://www.linkedin.com/jobs/view/4000000001"
    assert "pipelines" in first["snippet"]


def test_fetch_offers_maps_job_offer_create():
    http = MockLinkedInHttp()
    scraper = LinkedInScraper(http_client=http)

    result = scraper.fetch_offers(JobSector.DATA, query="data engineer", max_pages=1)

    assert result.errors == []
    assert len(result.offers) == 5
    offer = result.offers[0]
    assert offer.source == "linkedin"
    assert offer.external_id == "4000000001"
    assert offer.title == "Data Engineer"
    assert offer.company == "Acme Corp"
    assert offer.sector == JobSector.DATA
    assert str(offer.url) == "https://www.linkedin.com/jobs/view/4000000001"
    assert offer.description == "Build and maintain data pipelines using Python and SQL."


def test_max_offers_caps_results_and_limits_http_calls():
    http = MockLinkedInHttp()
    scraper = LinkedInScraper(http_client=http)

    result = scraper.fetch_offers(
        JobSector.DATA,
        query="data engineer",
        max_pages=3,
        max_offers=2,
    )

    assert result.errors == []
    assert len(result.offers) == 2
    assert http.search_calls == 1


def test_403_response_adds_error_without_crashing():
    http = BlockingLinkedInHttp()
    scraper = LinkedInScraper(http_client=http)

    result = scraper.fetch_offers(JobSector.DATA, query="data engineer", max_pages=1)

    assert result.offers == []
    assert len(result.errors) == 1
    assert "403" in result.errors[0]
    assert "blocked" in result.errors[0].lower()


def test_health_check_uses_guest_search_endpoint():
    settings = Settings()
    http = MagicMock()
    response = MagicMock()
    response.status_code = 200
    http._client.get.return_value = response

    scraper = LinkedInScraper(http_client=http, settings=settings)
    assert scraper.health_check() is True

    http._client.get.assert_called_once()
    call_args = http._client.get.call_args
    assert call_args.args[0] == settings.linkedin_guest_api_base
    assert call_args.kwargs["params"]["keywords"] == "test"
    assert call_args.kwargs["params"]["location"] == settings.linkedin_jobs_location


def test_no_queries_configured_returns_clear_error(monkeypatch):
    scraper = LinkedInScraper(http_client=MockLinkedInHttp())

    monkeypatch.setattr(
        LinkedInScraper,
        "_resolve_queries",
        lambda self, sector_id: [],
    )

    result = scraper.fetch_offers(JobSector.DATA)

    assert result.offers == []
    assert len(result.errors) == 1
    assert "No LinkedIn search queries" in result.errors[0]
