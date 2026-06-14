"""Shared HTTP client for scrapers with retry and rate limiting."""

from __future__ import annotations

import time
from typing import Any

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from config.settings import Settings, get_settings

logger = structlog.get_logger(__name__)


class ScraperHttpClient:
    """HTTP client wrapper with retry, delay, and browser-like defaults."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._last_request_at = 0.0
        self._client = httpx.Client(
            headers={
                "User-Agent": self.settings.scraper_user_agent,
                "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
                "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
            },
            timeout=30.0,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ScraperHttpClient:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _respect_rate_limit(self) -> None:
        delay = self.settings.scraper_request_delay_seconds
        if delay <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < delay:
            time.sleep(delay - elapsed)

    @retry(
        retry=retry_if_exception_type(httpx.HTTPError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def get_json(self, url: str, *, params: dict[str, Any] | None = None) -> Any:
        self._respect_rate_limit()
        response = self._client.get(url, params=params)
        self._last_request_at = time.monotonic()
        response.raise_for_status()
        return response.json()

    @retry(
        retry=retry_if_exception_type(httpx.HTTPError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def get_text(self, url: str, *, params: dict[str, Any] | None = None) -> str:
        self._respect_rate_limit()
        response = self._client.get(url, params=params)
        self._last_request_at = time.monotonic()
        response.raise_for_status()
        return response.text

    def health_check(self, url: str) -> bool:
        try:
            response = self._client.get(url, timeout=10.0)
            return response.status_code < 500
        except httpx.HTTPError:
            return False
