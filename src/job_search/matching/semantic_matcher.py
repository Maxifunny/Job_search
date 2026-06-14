"""Embedding-based similarity scoring (stub)."""

from job_search.memory.vector_store import VectorMemory
from job_search.schemas.candidate import CandidateProfile
from job_search.schemas.job_offer import JobOfferCreate


class SemanticMatcher:
    """Compute semantic overlap between candidate profile and job offer."""

    def __init__(self, vector_memory: VectorMemory) -> None:
        self.vector_memory = vector_memory

    def score(self, offer: JobOfferCreate, profile: CandidateProfile) -> float:
        """
        Return cosine similarity score in [0, 1].

        Implementation delegated to Matching Agent (embeddings + Chroma query).
        """
        raise NotImplementedError("Implement in Matching Agent branch")
