"""Unit tests for API usage/quota observability helpers."""

from job_search.observability.api_usage import (
    extract_token_usage,
    format_api_usage_log,
    parse_quota_headers,
)


def test_parse_quota_headers_with_values():
    snapshot = parse_quota_headers(
        {
            "x-ratelimit-limit-requests": "500",
            "x-ratelimit-remaining-requests": "321",
            "x-ratelimit-reset-requests": "22s",
            "x-ratelimit-limit-tokens": "200000",
            "x-ratelimit-remaining-tokens": "175000",
            "x-ratelimit-reset-tokens": "22s",
        }
    )

    assert snapshot.limit_requests == 500
    assert snapshot.remaining_requests == 321
    assert snapshot.reset_requests == "22s"
    assert snapshot.limit_tokens == 200000
    assert snapshot.remaining_tokens == 175000
    assert snapshot.reset_tokens == "22s"
    assert snapshot.has_any_signal is True


def test_parse_quota_headers_without_values():
    snapshot = parse_quota_headers(None)
    assert snapshot.has_any_signal is False
    assert snapshot.remaining_requests is None
    assert snapshot.remaining_tokens is None


def test_format_log_fallback_when_provider_hides_quota():
    usage = extract_token_usage({"usage": {"prompt_tokens": 10, "total_tokens": 10}})
    snapshot = parse_quota_headers({})

    line = format_api_usage_log(
        endpoint="chat.completions",
        model="gpt-4o-mini",
        usage=usage,
        quota=snapshot,
        api_key="sk-test-4321",
    )

    assert "key=***4321" in line
    assert "tokens(prompt=10,completion=na,total=10)" in line
    assert "remaining_quota=not_exposed_by_provider" in line
