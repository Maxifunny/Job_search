"""Tests for LLM model fallback helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from openai import APIStatusError

from job_search.llm.model_fallback import (
    build_model_chain,
    is_retriable_api_error,
    run_with_model_fallback,
)


def test_build_model_chain_deduplicates_primary_and_fallbacks():
    chain = build_model_chain(
        "gemini-2.5-flash",
        ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-flash"],
    )
    assert chain == ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]


def test_is_retriable_api_error_detects_503():
    exc = APIStatusError(
        "high demand",
        response=MagicMock(status_code=503),
        body={"error": {"code": 503, "status": "UNAVAILABLE"}},
    )
    assert is_retriable_api_error(exc) is True


def test_run_with_model_fallback_switches_model_after_retries(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(
        "job_search.llm.model_fallback.time.sleep",
        lambda seconds: sleeps.append(seconds),
    )

    calls: list[str] = []

    def operation(model: str) -> str:
        calls.append(model)
        if model == "primary":
            raise APIStatusError(
                "unavailable",
                response=MagicMock(status_code=503),
                body={},
            )
        return f"ok:{model}"

    result, model_used = run_with_model_fallback(
        ["primary", "fallback"],
        operation,
        retries_per_model=2,
        retry_delay_seconds=0.01,
    )

    assert result == "ok:fallback"
    assert model_used == "fallback"
    assert calls.count("primary") == 2
    assert calls.count("fallback") == 1


def test_run_with_model_fallback_raises_non_retriable_immediately():
    def operation(_model: str) -> str:
        raise ValueError("invalid json")

    with pytest.raises(ValueError, match="invalid json"):
        run_with_model_fallback(["only-model"], operation, retries_per_model=2)
