"""LLM-based job fit evaluation (stub)."""

from dataclasses import dataclass

from job_search.schemas.candidate import CandidateProfile
from job_search.schemas.job_offer import JobOfferCreate


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

    def evaluate(
        self, offer: JobOfferCreate, profile: CandidateProfile
    ) -> LLMEvaluation:
        raise NotImplementedError("Implement in Matching Agent branch")
