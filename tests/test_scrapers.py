"""Unit tests for job portal scrapers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from config.settings import Settings
from job_search.scrapers.parsers import extract_pracuj_offer_links, parse_pracuj_offer_page
from job_search.scrapers.registry import list_sources, run_scraper
from job_search.scrapers.sources.justjoin import JustJoinScraper
from job_search.scrapers.sources.nofluffjobs import NoFluffJobsScraper
from job_search.scrapers.sources.pracuj_pl import PracujPlScraper
from job_search.schemas.job_offer import JobSector

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str):
    path = FIXTURES / name
    if name.endswith(".json"):
        return json.loads(path.read_text(encoding="utf-8"))
    return path.read_text(encoding="utf-8")


class MockHttpClient:
    def __init__(self, routes: dict[str, object]) -> None:
        self.routes = routes

    def get_json(self, url: str, *, params=None):
        candidates = sorted(self.routes.items(), key=lambda item: len(item[0]), reverse=True)
        for route, payload in candidates:
            if url.startswith(route):
                return payload
        raise KeyError(f"No mock route for {url} params={params}")

    def get_text(self, url: str, *, params=None):
        payload = self.get_json(url, params=params) if url in self.routes else None
        if isinstance(payload, str):
            return payload
        raise KeyError(f"No mock text route for {url}")

    def health_check(self, url: str) -> bool:
        return True

    def close(self) -> None:
        return None


def test_list_sources_includes_three_portals():
    sources = list_sources()
    assert "justjoin" in sources
    assert "pracuj_pl" in sources
    assert "nofluffjobs" in sources


def test_justjoin_maps_offer_from_api():
    http = MockHttpClient(
        {
            "https://justjoin.it/api/candidate-api/offers": _load("justjoin_list.json"),
            "https://justjoin.it/api/candidate-api/offers/warner-bros-discovery-observability-engineer-warsaw-data-4b63f485": _load(
                "justjoin_detail.json"
            ),
        }
    )
    scraper = JustJoinScraper(http_client=http)
    result = scraper.fetch_offers(JobSector.DATA, query="data", max_pages=1)

    assert result.errors == []
    assert len(result.offers) == 1
    offer = result.offers[0]
    assert offer.source == "justjoin"
    assert offer.title == "Observability Engineer"
    assert "Python" in offer.skills
    assert "SQL" in offer.skills
    assert "Spark" in offer.skills
    assert offer.sector == JobSector.DATA


def test_pracuj_parser_extracts_links_and_details():
    search_html = _load("pracuj_search.html")
    links = extract_pracuj_offer_links(search_html)
    assert len(links) == 2
    assert ",oferta,1003220296" in links[0]

    parsed = parse_pracuj_offer_page(
        _load("pracuj_offer.html"),
        "https://www.pracuj.pl/praca/data-engineer-warszawa,oferta,1003220296",
    )
    assert parsed["title"] == "Data Engineer"
    assert parsed["company"] == "Acme Corp"
    assert parsed["salary_min"] == 8000
    assert parsed["remote"] is True


def test_pracuj_scraper_uses_search_and_detail_pages():
    search_html = _load("pracuj_search.html")
    offer_html = _load("pracuj_offer.html")

    http = MagicMock()
    http.get_text.side_effect = [search_html, offer_html, search_html, offer_html]
    http.health_check.return_value = True

    scraper = PracujPlScraper(http_client=http)
    result = scraper.fetch_offers(JobSector.DATA, query="data engineer", max_pages=1)

    assert len(result.offers) == 2
    assert result.offers[0].source == "pracuj_pl"
    assert result.offers[0].company == "Acme Corp"


def test_nofluffjobs_maps_offer_from_api():
    http = MockHttpClient(
        {
            "https://nofluffjobs.com/api/posting": _load("nofluffjobs_list.json"),
            "https://nofluffjobs.com/api/posting/data-engineer-acme-warsaw": _load(
                "nofluffjobs_detail.json"
            ),
        }
    )
    scraper = NoFluffJobsScraper(http_client=http)
    result = scraper.fetch_offers(JobSector.DATA, query="data", max_pages=1)

    assert result.errors == []
    assert len(result.offers) == 1
    offer = result.offers[0]
    assert offer.source == "nofluffjobs"
    assert offer.title == "Data Engineer"
    assert "Python" in offer.skills


def test_run_scraper_unknown_source_raises():
    with pytest.raises(ValueError, match="Unknown scraper source"):
        run_scraper("unknown-portal", JobSector.DATA)


# --- max_offers / early-termination fixtures and helpers -------------------

JUSTJOIN_DETAIL = {
    "body": "<p>Build and operate data pipelines.</p>",
    "requirements": "<p>SQL, Python</p>",
    "requiredSkills": [{"name": "Python"}, {"name": "SQL"}],
    "niceToHaveSkills": [{"name": "Spark"}],
    "employmentTypes": [
        {"from": 12000, "to": 18000, "currency": "PLN", "type": "permanent"}
    ],
    "workplaceType": "remote",
}

NOFLUFF_DETAIL = {
    "title": "Data Engineer",
    "company": {"name": "Acme Corp"},
    "specs": {"dailyTasks": ["Build pipelines"]},
    "requirements": {"skills": [{"name": "Python"}]},
    "basics": {"technology": "Python"},
    "salary": {"from": 12000, "to": 18000},
}


def _justjoin_list(count: int):
    return {
        "data": [
            {
                "guid": f"guid-{i}",
                "slug": f"data-offer-{i}",
                "title": f"Data Role {i}",
                "companyName": "Acme",
                "city": "Warsaw",
                "workplaceType": "remote",
                "publishedAt": "2026-06-14T18:00:02Z",
            }
            for i in range(count)
        ],
        "meta": {"from": 0, "totalItems": count, "next": {"cursor": None}},
    }


def _nofluff_list(count: int):
    return {
        "postings": [
            {
                "id": f"job-{i}",
                "name": "Acme Corp",
                "title": f"Data Engineer {i}",
                "location": {"fullyRemote": False, "places": [{"city": "Warszawa"}]},
            }
            for i in range(count)
        ]
    }


class CountingJustJoinHttp:
    """JustJoin mock that returns a list payload and counts detail requests."""

    def __init__(self, list_payload: dict) -> None:
        self.list_payload = list_payload
        self.detail_calls = 0

    def get_json(self, url: str, *, params=None):
        if url.endswith("/offers"):
            return self.list_payload
        self.detail_calls += 1
        return JUSTJOIN_DETAIL

    def health_check(self, url: str) -> bool:
        return True

    def close(self) -> None:
        return None


class CountingNoFluffHttp:
    """NoFluffJobs mock that returns a list payload and counts detail requests."""

    def __init__(self, list_payload: dict) -> None:
        self.list_payload = list_payload
        self.detail_calls = 0

    def get_json(self, url: str, *, params=None):
        if url.endswith("/posting"):
            return self.list_payload
        self.detail_calls += 1
        return NOFLUFF_DETAIL

    def health_check(self, url: str) -> bool:
        return True

    def close(self) -> None:
        return None


def test_justjoin_max_offers_caps_total_and_limits_detail_calls():
    http = CountingJustJoinHttp(_justjoin_list(10))
    scraper = JustJoinScraper(http_client=http)

    result = scraper.fetch_offers(JobSector.DATA, max_offers=3, max_pages=1)

    assert result.errors == []
    assert len(result.offers) == 3
    assert http.detail_calls == 3


def test_justjoin_default_run_bounded_by_per_query_cap():
    settings = Settings()
    settings.scraper_max_offers_per_query = 2
    http = CountingJustJoinHttp(_justjoin_list(10))
    scraper = JustJoinScraper(http_client=http, settings=settings)

    result = scraper.fetch_offers(JobSector.DATA, query="data", max_pages=1)

    assert len(result.offers) == 2
    assert http.detail_calls == 2


def test_nofluffjobs_max_offers_caps_total_and_limits_detail_calls():
    http = CountingNoFluffHttp(_nofluff_list(10))
    scraper = NoFluffJobsScraper(http_client=http)

    result = scraper.fetch_offers(JobSector.DATA, max_offers=3, max_pages=1)

    assert result.errors == []
    assert len(result.offers) == 3
    assert http.detail_calls == 3


def test_nofluffjobs_default_run_bounded_by_per_query_cap():
    settings = Settings()
    settings.scraper_max_offers_per_query = 2
    http = CountingNoFluffHttp(_nofluff_list(10))
    scraper = NoFluffJobsScraper(http_client=http, settings=settings)

    result = scraper.fetch_offers(JobSector.DATA, query="data", max_pages=1)

    assert len(result.offers) == 2
    assert http.detail_calls == 2


def test_pracuj_max_offers_caps_total_and_limits_detail_calls():
    search_html = _load("pracuj_search.html")
    offer_html = _load("pracuj_offer.html")

    http = MagicMock()
    http.get_text.side_effect = [search_html, offer_html, offer_html]
    http.health_check.return_value = True

    scraper = PracujPlScraper(http_client=http)
    result = scraper.fetch_offers(
        JobSector.DATA, query="data engineer", max_pages=1, max_offers=1
    )

    assert len(result.offers) == 1
    # One list request + one detail request; the second link is never fetched.
    assert http.get_text.call_count == 2
