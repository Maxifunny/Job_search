"""Text embedding helpers and OpenAI-backed embedding service."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Mapping

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from config.settings import Settings, get_settings
from job_search.memory.models import EmbeddingCache
from job_search.llm.model_fallback import build_model_chain, run_with_model_fallback
from job_search.observability.api_usage import (
    extract_token_usage,
    format_api_usage_log,
    parse_quota_headers,
)
from job_search.schemas.job_offer import JobOfferCreate

logger = logging.getLogger(__name__)


def build_offer_document(offer: JobOfferCreate) -> str:
    """Build a searchable document from offer title, description, and skills."""
    skills = ", ".join(offer.skills) if offer.skills else ""
    parts = [offer.title.strip(), offer.description.strip()]
    if skills:
        parts.append(f"Skills: {skills}")
    return "\n\n".join(part for part in parts if part)


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EmbeddingService:
    """Generate embeddings via OpenAI API with optional SQLite cache."""

    def __init__(
        self,
        session: Session | None = None,
        settings: Settings | None = None,
        client: OpenAI | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.session = session
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
            self.settings.embedding_model,
            self.settings.embedding_fallback_models,
        )

    def _load_cached(self, text: str, *, model: str) -> list[float] | None:
        if self.session is None:
            return None
        text_hash = _text_hash(text)
        stmt = select(EmbeddingCache).where(
            EmbeddingCache.text_hash == text_hash,
            EmbeddingCache.model == model,
        )
        cached = self.session.scalar(stmt)
        if cached is None:
            return None
        return json.loads(cached.embedding_json)

    def _save_cache(self, text: str, embedding: list[float], *, model: str) -> None:
        if self.session is None:
            return
        self.session.add(
            EmbeddingCache(
                text_hash=_text_hash(text),
                model=model,
                embedding_json=json.dumps(embedding),
            )
        )
        self.session.flush()

    def _create_embedding_with_headers(
        self,
        text: str,
        *,
        model: str,
    ) -> tuple[object, Mapping[str, str] | None]:
        kwargs = {"model": model, "input": text}
        embeddings_api = self.client.embeddings
        if hasattr(embeddings_api, "with_raw_response"):
            raw_response = embeddings_api.with_raw_response.create(**kwargs)
            parsed = raw_response.parse()
            try:
                embedding = parsed.data[0].embedding
            except (AttributeError, IndexError, TypeError):
                embedding = None
            if isinstance(embedding, list):
                return parsed, getattr(raw_response, "headers", None)
        return embeddings_api.create(**kwargs), None

    def embed_text(self, text: str) -> list[float]:
        """Return embedding vector for text, using cache when available."""
        for model in self._model_chain():
            cached = self._load_cached(text, model=model)
            if cached is not None:
                self.last_model_used = model
                return cached

        def _call(selected_model: str) -> tuple[object, Mapping[str, str] | None]:
            return self._create_embedding_with_headers(text, model=selected_model)

        (response, headers), model_used = run_with_model_fallback(
            self._model_chain(),
            _call,
            retries_per_model=self.settings.llm_retry_attempts,
            endpoint_label="embeddings.create",
        )
        self.last_model_used = model_used

        if self.settings.log_api_quota:
            logger.info(
                format_api_usage_log(
                    endpoint="embeddings.create",
                    model=model_used,
                    usage=extract_token_usage(response),
                    quota=parse_quota_headers(headers),
                    api_key=self.settings.llm_api_key,
                )
            )
        embedding = response.data[0].embedding
        self._save_cache(text, embedding, model=model_used)
        return embedding
