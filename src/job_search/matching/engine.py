"""Orchestrates filtering, semantic scoring, and LLM evaluation."""

from dataclasses import dataclass

from config.settings import get_settings
from job_search.matching.filters import FalsePositiveFilter
from job_search.matching.llm_evaluator import LLMEvaluation, LLMEvaluator
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
    matched_skills: list[str] | None = None
    missing_skills: list[str] | None = None


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
            outcome = MatchOutcome(
                offer=offer,
                decision=MatchDecisionEnum.REJECTED,
                reason=reason,
            )
            if job_offer_id is not None:
                self._persist_outcome(job_offer_id, profile.name, outcome)
            return outcome

        if job_offer_id and self.offer_repo.was_already_recommended(
            job_offer_id, profile.name
        ):
            outcome = MatchOutcome(
                offer=offer,
                decision=MatchDecisionEnum.SKIPPED,
                reason="Offer already recommended",
            )
            if job_offer_id is not None:
                self._persist_outcome(job_offer_id, profile.name, outcome)
            return outcome

        semantic_score = self.semantic_matcher.score(offer, profile)
        if semantic_score < self.settings.min_semantic_score:
            outcome = MatchOutcome(
                offer=offer,
                decision=MatchDecisionEnum.REJECTED,
                semantic_score=semantic_score,
                reason="Below semantic threshold",
            )
            if job_offer_id is not None:
                self._persist_outcome(job_offer_id, profile.name, outcome)
            return outcome

        llm_result = self.llm_evaluator.evaluate(offer, profile)
        if (
            not llm_result.is_relevant_role
            or llm_result.confidence < self.settings.min_llm_confidence
        ):
            outcome = MatchOutcome(
                offer=offer,
                decision=MatchDecisionEnum.REJECTED,
                semantic_score=semantic_score,
                llm_score=llm_result.score,
                llm_confidence=llm_result.confidence,
                reason=llm_result.explanation,
                matched_skills=llm_result.matched_skills,
                missing_skills=llm_result.missing_skills,
            )
            if job_offer_id is not None:
                self._persist_outcome(
                    job_offer_id,
                    profile.name,
                    outcome,
                    llm_result=llm_result,
                )
            return outcome

        outcome = MatchOutcome(
            offer=offer,
            decision=MatchDecisionEnum.ACCEPTED,
            semantic_score=semantic_score,
            llm_score=llm_result.score,
            llm_confidence=llm_result.confidence,
            reason=llm_result.explanation,
            matched_skills=llm_result.matched_skills,
            missing_skills=llm_result.missing_skills,
        )
        if job_offer_id is not None:
            self._persist_outcome(
                job_offer_id,
                profile.name,
                outcome,
                llm_result=llm_result,
            )
            self.offer_repo.mark_recommended(
                job_offer_id,
                profile.name,
                channel="matching",
            )
        return outcome

    def _persist_outcome(
        self,
        job_offer_id: int,
        candidate_name: str,
        outcome: MatchOutcome,
        *,
        llm_result: LLMEvaluation | None = None,
    ) -> None:
        self.match_repo.save_result(
            job_offer_id=job_offer_id,
            candidate_name=candidate_name,
            semantic_score=outcome.semantic_score,
            llm_score=outcome.llm_score,
            llm_confidence=outcome.llm_confidence,
            decision=outcome.decision,
            rejection_reason=outcome.reason,
            matched_skills=outcome.matched_skills or [],
            missing_skills=outcome.missing_skills or [],
            llm_explanation=(
                llm_result.explanation if llm_result is not None else outcome.reason
            ),
        )
