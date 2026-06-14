"""Orchestrates filtering, semantic scoring, and LLM evaluation."""

from dataclasses import dataclass

from config.settings import get_settings
from job_search.matching.filters import FalsePositiveFilter
from job_search.matching.llm_evaluator import LLMEvaluator
from job_search.matching.semantic_matcher import SemanticMatcher
from job_search.memory.models import MatchDecisionEnum
from job_search.memory.repositories import JobOfferRepository, MatchResultRepository
from job_search.schemas.candidate import CandidateProfile
from job_search.schemas.job_offer import JobOfferCreate


@dataclass
class MatchOutcome:
    offer: JobOfferCreate
    decision: MatchDecisionEnum
    semantic_score: float | None = None
    llm_score: float | None = None
    llm_confidence: float | None = None
    reason: str | None = None


class MatchingEngine:
    """End-to-end matching pipeline for a single offer."""

    def __init__(
        self,
        semantic_matcher: SemanticMatcher,
        llm_evaluator: LLMEvaluator,
        offer_repo: JobOfferRepository,
        match_repo: MatchResultRepository,
    ) -> None:
        self.semantic_matcher = semantic_matcher
        self.llm_evaluator = llm_evaluator
        self.offer_repo = offer_repo
        self.match_repo = match_repo
        self.settings = get_settings()

    def evaluate_offer(
        self,
        offer: JobOfferCreate,
        profile: CandidateProfile,
        *,
        job_offer_id: int | None = None,
    ) -> MatchOutcome:
        rejected, reason = FalsePositiveFilter.should_reject(offer, profile)
        if rejected:
            return MatchOutcome(
                offer=offer,
                decision=MatchDecisionEnum.REJECTED,
                reason=reason,
            )

        if job_offer_id and self.offer_repo.was_already_recommended(
            job_offer_id, profile.name
        ):
            return MatchOutcome(
                offer=offer,
                decision=MatchDecisionEnum.SKIPPED,
                reason="Offer already recommended",
            )

        semantic_score = self.semantic_matcher.score(offer, profile)
        if semantic_score < self.settings.min_semantic_score:
            return MatchOutcome(
                offer=offer,
                decision=MatchDecisionEnum.REJECTED,
                semantic_score=semantic_score,
                reason="Below semantic threshold",
            )

        llm_result = self.llm_evaluator.evaluate(offer, profile)
        if (
            not llm_result.is_relevant_role
            or llm_result.confidence < self.settings.min_llm_confidence
        ):
            return MatchOutcome(
                offer=offer,
                decision=MatchDecisionEnum.REJECTED,
                semantic_score=semantic_score,
                llm_score=llm_result.score,
                llm_confidence=llm_result.confidence,
                reason=llm_result.explanation,
            )

        return MatchOutcome(
            offer=offer,
            decision=MatchDecisionEnum.ACCEPTED,
            semantic_score=semantic_score,
            llm_score=llm_result.score,
            llm_confidence=llm_result.confidence,
            reason=llm_result.explanation,
        )
