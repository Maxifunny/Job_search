"""ChromaDB vector store for semantic memory."""

from __future__ import annotations

from typing import Any

import chromadb
from chromadb.api.models.Collection import Collection

from config.settings import Settings, get_settings


class VectorMemory:
    """
    Long-term semantic memory backed by ChromaDB.

    Collections:
    - job_offers: embedded job descriptions for similarity search
    - user_preferences: embedded CV/skills/preferences for candidate context
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.settings.chroma_persist_dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=str(self.settings.chroma_persist_dir)
        )
        self.offers: Collection = self.client.get_or_create_collection(
            name=self.settings.chroma_collection_offers,
            metadata={"hnsw:space": "cosine"},
        )
        self.preferences: Collection = self.client.get_or_create_collection(
            name=self.settings.chroma_collection_preferences,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert_job_offer(
        self,
        *,
        offer_id: str,
        document: str,
        metadata: dict[str, Any],
        embedding: list[float] | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {
            "ids": [offer_id],
            "documents": [document],
            "metadatas": [metadata],
        }
        if embedding is not None:
            kwargs["embeddings"] = [embedding]
        self.offers.upsert(**kwargs)

    def upsert_preference(
        self,
        *,
        candidate_name: str,
        document: str,
        metadata: dict[str, Any],
        embedding: list[float] | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {
            "ids": [candidate_name],
            "documents": [document],
            "metadatas": [metadata],
        }
        if embedding is not None:
            kwargs["embeddings"] = [embedding]
        self.preferences.upsert(**kwargs)

    def query_similar_offers(
        self,
        query_embedding: list[float],
        *,
        n_results: int = 20,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.offers.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
        )
