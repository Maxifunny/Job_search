"""Relational and vector memory subsystem."""

from job_search.memory.database import create_db_engine, get_session, init_database
from job_search.memory.models import Base, JobOffer, MatchResult, Recommendation
from job_search.memory.repositories import JobOfferRepository, MatchResultRepository
from job_search.memory.vector_store import VectorMemory

__all__ = [
    "Base",
    "JobOffer",
    "JobOfferRepository",
    "MatchResult",
    "MatchResultRepository",
    "Recommendation",
    "VectorMemory",
    "create_db_engine",
    "get_session",
    "init_database",
]
