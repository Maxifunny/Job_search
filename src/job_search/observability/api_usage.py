"""Helpers for logging OpenAI-compatible API quota and usage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class TokenUsage:
    """Token usage metadata returned in API response bodies."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class ApiQuotaSnapshot:
    """Quota data from OpenAI-compatible rate limit headers."""

    limit_requests: int | None = None
    remaining_requests: int | None = None
    reset_requests: str | None = None
    limit_tokens: int | None = None
    remaining_tokens: int | None = None
    reset_tokens: str | None = None

    @property
    def has_any_signal(self) -> bool:
        return any(
            value is not None
            for value in (
                self.limit_requests,
                self.remaining_requests,
                self.reset_requests,
                self.limit_tokens,
                self.remaining_tokens,
                self.reset_tokens,
            )
        )


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_quota_headers(headers: Mapping[str, str] | None) -> ApiQuotaSnapshot:
    """Parse common OpenAI-compatible quota/rate-limit headers."""
    if not headers:
        return ApiQuotaSnapshot()

    normalized = {key.lower(): value for key, value in headers.items()}
    return ApiQuotaSnapshot(
        limit_requests=_to_int(normalized.get("x-ratelimit-limit-requests")),
        remaining_requests=_to_int(normalized.get("x-ratelimit-remaining-requests")),
        reset_requests=normalized.get("x-ratelimit-reset-requests"),
        limit_tokens=_to_int(normalized.get("x-ratelimit-limit-tokens")),
        remaining_tokens=_to_int(normalized.get("x-ratelimit-remaining-tokens")),
        reset_tokens=normalized.get("x-ratelimit-reset-tokens"),
    )


def extract_token_usage(payload: Any) -> TokenUsage:
    """Extract usage fields from OpenAI-compatible response objects."""
    usage = getattr(payload, "usage", None)
    if usage is None and isinstance(payload, dict):
        usage = payload.get("usage")
    if usage is None:
        return TokenUsage()

    if isinstance(usage, dict):
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        total_tokens = usage.get("total_tokens")
    else:
        prompt_tokens = getattr(usage, "prompt_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None)
        total_tokens = getattr(usage, "total_tokens", None)

    return TokenUsage(
        prompt_tokens=_to_int(str(prompt_tokens)) if prompt_tokens is not None else None,
        completion_tokens=(
            _to_int(str(completion_tokens)) if completion_tokens is not None else None
        ),
        total_tokens=_to_int(str(total_tokens)) if total_tokens is not None else None,
    )


def mask_api_key(api_key: str | None) -> str | None:
    """Return a safe key fingerprint (last 4 chars) or None."""
    if not api_key:
        return None
    if len(api_key) <= 4:
        return "****"
    return f"***{api_key[-4:]}"


def format_api_usage_log(
    *,
    endpoint: str,
    model: str,
    usage: TokenUsage,
    quota: ApiQuotaSnapshot,
    api_key: str | None = None,
) -> str:
    """Format concise, ASCII-safe quota/usage log line."""
    key_fingerprint = mask_api_key(api_key)
    key_part = f" key={key_fingerprint}" if key_fingerprint else ""
    usage_part = (
        "tokens("
        f"prompt={usage.prompt_tokens if usage.prompt_tokens is not None else 'na'},"
        f"completion={usage.completion_tokens if usage.completion_tokens is not None else 'na'},"
        f"total={usage.total_tokens if usage.total_tokens is not None else 'na'}"
        ")"
    )
    if quota.has_any_signal:
        quota_part = (
            "remaining("
            f"requests={quota.remaining_requests if quota.remaining_requests is not None else 'na'},"
            f"tokens={quota.remaining_tokens if quota.remaining_tokens is not None else 'na'}"
            ") "
            "limits("
            f"requests={quota.limit_requests if quota.limit_requests is not None else 'na'},"
            f"tokens={quota.limit_tokens if quota.limit_tokens is not None else 'na'}"
            ") "
            "reset("
            f"requests={quota.reset_requests or 'na'},"
            f"tokens={quota.reset_tokens or 'na'}"
            ")"
        )
    else:
        quota_part = "remaining_quota=not_exposed_by_provider"

    return f"api_usage endpoint={endpoint} model={model}{key_part} {usage_part} {quota_part}"
