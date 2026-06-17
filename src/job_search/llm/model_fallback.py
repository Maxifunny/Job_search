"""Retry and model fallback for OpenAI-compatible LLM/embedding APIs."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

from openai import APIConnectionError, APIStatusError, RateLimitError

logger = logging.getLogger(__name__)

T = TypeVar("T")

_RETRIABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_QUOTA_SIGNALS = (
    "quota",
    "rate limit",
    "rate_limit",
    "too many requests",
    "resource_exhausted",
    "exhausted",
    "unavailable",
    "high demand",
    "limit exceeded",
    "billing",
)


def build_model_chain(primary: str, fallbacks: list[str]) -> list[str]:
    """Return unique model ids: primary first, then fallbacks."""
    chain: list[str] = []
    seen: set[str] = set()
    for model in [primary, *fallbacks]:
        model = model.strip()
        if model and model not in seen:
            seen.add(model)
            chain.append(model)
    return chain


def is_retriable_api_error(exc: Exception) -> bool:
    """Whether the error may succeed on retry or with another model."""
    if isinstance(exc, (RateLimitError, APIConnectionError)):
        return True
    if isinstance(exc, APIStatusError):
        if exc.status_code in _RETRIABLE_STATUS_CODES:
            return True
    message = str(exc).lower()
    return any(signal in message for signal in _QUOTA_SIGNALS)


def run_with_model_fallback(
    models: list[str],
    operation: Callable[[str], T],
    *,
    retries_per_model: int = 2,
    retry_delay_seconds: float = 1.5,
    endpoint_label: str = "api",
) -> tuple[T, str]:
    """Run *operation(model)* with per-model retries and fallback chain."""
    if not models:
        raise ValueError("At least one model is required")

    last_error: Exception | None = None
    for model_index, model in enumerate(models):
        delay = retry_delay_seconds
        for attempt in range(max(1, retries_per_model)):
            try:
                result = operation(model)
                if model_index > 0:
                    logger.warning(
                        "%s succeeded with fallback model %s (primary unavailable)",
                        endpoint_label,
                        model,
                    )
                return result, model
            except Exception as exc:
                last_error = exc
                if not is_retriable_api_error(exc):
                    raise
                is_last_attempt = attempt >= retries_per_model - 1
                is_last_model = model_index >= len(models) - 1
                if is_last_attempt and is_last_model:
                    break
                if is_last_attempt:
                    logger.warning(
                        "%s model %s unavailable (%s); switching to next model",
                        endpoint_label,
                        model,
                        exc,
                    )
                    break
                logger.warning(
                    "%s model %s attempt %d/%d failed (%s); retry in %.1fs",
                    endpoint_label,
                    model,
                    attempt + 1,
                    retries_per_model,
                    exc,
                    delay,
                )
                time.sleep(delay)
                delay *= 2

    assert last_error is not None
    raise last_error
