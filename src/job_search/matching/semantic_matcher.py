"""Embedding-based similarity scoring."""

from __future__ import annotations

import math

from job_search.memory.embeddings import EmbeddingService, build_offer_document
from job_search.schemas.candidate import CandidateProfile
from job_search.schemas.job_offer import JobOfferCreate


def build_profile_document(profile: CandidateProfile) -> str:
    """Build a searchable document from candidate profile fields."""
    parts: list[str] = []

    if profile.target_roles:
        parts.append(f"Target roles: {', '.join(profile.target_roles)}")

    if profile.skills:
        skill_names = ", ".join(skill.name for skill in profile.skills)
        parts.append(f"Skills: {skill_names}")

    if profile.skills_to_learn:
        parts.append(f"Learning goals: {', '.join(profile.skills_to_learn)}")

    if profile.cv_text:
        parts.append(profile.cv_text.strip())

    if profile.notes:
        parts.append(profile.notes.strip())

    return "\n\n".join(part for part in parts if part)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Return cosine similarity clamped to [0, 1]."""
    if not left or not right or len(left) != len(right):
        return 0.0

    dot_product = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0

    similarity = dot_product / (left_norm * right_norm)
    return max(0.0, min(1.0, similarity))


class SemanticMatcher:
    """Compute semantic overlap between candidate profile and job offer."""

    def __init__(self, embedding_service: EmbeddingService) -> None:
        self.embedding_service = embedding_service

    def score(self, offer: JobOfferCreate, profile: CandidateProfile) -> float:
        """Return cosine similarity score in [0, 1]."""
        profile_document = build_profile_document(profile)
        offer_document = build_offer_document(offer)

        profile_embedding = self.embedding_service.embed_text(profile_document)
        offer_embedding = self.embedding_service.embed_text(offer_document)

        return cosine_similarity(profile_embedding, offer_embedding)
