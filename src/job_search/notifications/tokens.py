"""Signed tokens for email confirmation (mark as applied)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

TOKEN_VERSION = 1
TOKEN_MAX_AGE_SECONDS = 60 * 60 * 24 * 90  # 90 days


@dataclass(frozen=True)
class ConfirmTokenPayload:
    candidate_name: str
    job_offer_id: int
    issued_at: int


def _signing_secret(secret: str) -> bytes:
    if not secret:
        raise ValueError("NOTIFIER_SECRET is required for confirmation tokens")
    return secret.encode("utf-8")


def create_confirm_token(
    *,
    candidate_name: str,
    job_offer_id: int,
    secret: str,
) -> str:
    payload = {
        "v": TOKEN_VERSION,
        "candidate": candidate_name,
        "offer_id": job_offer_id,
        "iat": int(time.time()),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("ascii").rstrip("=")
    signature = hmac.new(
        _signing_secret(secret),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()
    sig_b64 = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"{payload_b64}.{sig_b64}"


def parse_confirm_token(token: str, *, secret: str) -> ConfirmTokenPayload:
    try:
        payload_b64, sig_b64 = token.split(".", 1)
    except ValueError as exc:
        raise ValueError("Niepoprawny token potwierdzenia.") from exc

    padded_payload = payload_b64 + "=" * (-len(payload_b64) % 4)
    padded_sig = sig_b64 + "=" * (-len(sig_b64) % 4)

    expected_sig = hmac.new(
        _signing_secret(secret),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()
    try:
        provided_sig = base64.urlsafe_b64decode(padded_sig.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise ValueError("Niepoprawny token potwierdzenia.") from exc

    if not hmac.compare_digest(expected_sig, provided_sig):
        raise ValueError("Token potwierdzenia jest nieprawidłowy lub wygasł.")

    try:
        payload = json.loads(base64.urlsafe_b64decode(padded_payload.encode("ascii")))
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Niepoprawny token potwierdzenia.") from exc

    if payload.get("v") != TOKEN_VERSION:
        raise ValueError("Nieobsługiwana wersja tokenu.")

    issued_at = int(payload.get("iat", 0))
    if issued_at <= 0 or time.time() - issued_at > TOKEN_MAX_AGE_SECONDS:
        raise ValueError("Token potwierdzenia wygasł.")

    candidate_name = str(payload.get("candidate", "")).strip()
    job_offer_id = int(payload.get("offer_id", 0))
    if not candidate_name or job_offer_id <= 0:
        raise ValueError("Niepoprawny token potwierdzenia.")

    return ConfirmTokenPayload(
        candidate_name=candidate_name,
        job_offer_id=job_offer_id,
        issued_at=issued_at,
    )
