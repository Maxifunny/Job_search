"""Relational and vector memory subsystem."""

from job_search.memory.database import create_db_engine, get_session, init_database
from job_search.memory.embeddings import EmbeddingService, build_offer_document
from job_search.memory.models import Base, JobOffer, MatchResult, Recommendation
from job_search.memory.repositories import (
    JobOfferRepository,
    MatchResultRepository,
    UserPreferenceRepository,
)
from job_search.memory.vector_store import VectorMemory

__all__ = [
    "Base",
    "EmbeddingService",
    "JobOffer",
    "JobOfferRepository",
    "MatchResult",
    "MatchResultRepository",
    "Recommendation",
    "UserPreferenceRepository",
    "VectorMemory",
    "build_offer_document",
    "create_db_engine",
    "get_session",
    "init_database",
]
