"""LLM-based job fit evaluation."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Mapping

from openai import OpenAI

from config.settings import Settings, get_settings
from job_search.llm.model_fallback import build_model_chain, run_with_model_fallback
from job_search.matching.prompts import build_evaluation_prompt
from job_search.observability.api_usage import (
    extract_token_usage,
    format_api_usage_log,
    parse_quota_headers,
)
from job_search.schemas.candidate import CandidateProfile
from job_search.schemas.job_offer import JobOfferCreate

logger = logging.getLogger(__name__)


@dataclass
class LLMEvaluation:
    score: float
    confidence: float
    matched_skills: list[str]
    missing_skills: list[str]
    explanation: str
    is_relevant_role: bool


class LLMEvaluator:
    """Use an LLM to assess whether skills truly match job requirements."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: OpenAI | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = client
        self.last_model_used: str | None = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                api_key=self.settings.llm_api_key or None,
                base_url=self.settings.llm_base_url,
            )
        return self._client

    def _model_chain(self) -> list[str]:
        return build_model_chain(
            self.settings.llm_model,
            self.settings.llm_fallback_models,
        )

    def _dev_mode_result(self) -> LLMEvaluation:
        return LLMEvaluation(
            score=0.0,
            confidence=0.0,
            matched_skills=[],
            missing_skills=[],
            explanation="LLM evaluation skipped: missing LLM_API_KEY",
            is_relevant_role=False,
        )

    def _create_completion_with_headers(
        self,
        prompt: str,
        *,
        model: str,
    ) -> tuple[object, Mapping[str, str] | None]:
        kwargs = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Jesteś asystentem HR. Odpowiadaj wyłącznie poprawnym JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        completions_api = self.client.chat.completions
        if hasattr(completions_api, "with_raw_response"):
            raw_response = completions_api.with_raw_response.create(**kwargs)
            parsed = raw_response.parse()
            try:
                content = parsed.choices[0].message.content
            except (AttributeError, IndexError, TypeError):
                content = None
            if isinstance(content, str):
                return parsed, getattr(raw_response, "headers", None)
        return completions_api.create(**kwargs), None

    def evaluate(
        self, offer: JobOfferCreate, profile: CandidateProfile
    ) -> LLMEvaluation:
        if not self.settings.llm_api_key:
            logger.warning(
                "LLM_API_KEY is not configured; skipping LLM evaluation (dev mode)"
            )
            return self._dev_mode_result()

        prompt = build_evaluation_prompt(offer, profile)

        def _call(model: str) -> tuple[object, Mapping[str, str] | None]:
            return self._create_completion_with_headers(prompt, model=model)

        (response, headers), model_used = run_with_model_fallback(
            self._model_chain(),
            _call,
            retries_per_model=self.settings.llm_retry_attempts,
            endpoint_label="chat.completions",
        )
        self.last_model_used = model_used

        if self.settings.log_api_quota:
            logger.info(
                format_api_usage_log(
                    endpoint="chat.completions",
                    model=model_used,
                    usage=extract_token_usage(response),
                    quota=parse_quota_headers(headers),
                    api_key=self.settings.llm_api_key,
                )
            )

        content = response.choices[0].message.content or "{}"
        payload = json.loads(content)

        return LLMEvaluation(
            score=float(payload.get("score", 0.0)),
            confidence=float(payload.get("confidence", 0.0)),
            matched_skills=list(payload.get("matched_skills", [])),
            missing_skills=list(payload.get("missing_skills", [])),
            explanation=str(payload.get("explanation", "")),
            is_relevant_role=bool(payload.get("is_relevant_role", False)),
        )
