"""Unit tests for job portal scrapers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

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
