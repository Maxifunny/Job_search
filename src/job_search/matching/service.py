"""High-level matching service for pending offers."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from config.settings import get_settings
from job_search.matching.engine import MatchingEngine, MatchOutcome
from job_search.matching.llm_evaluator import LLMEvaluator
from job_search.matching.semantic_matcher import SemanticMatcher
from job_search.memory.database import create_db_engine
from job_search.memory.embeddings import EmbeddingService
from job_search.memory.models import JobOffer, MatchDecisionEnum
from job_search.memory.repositories import JobOfferRepository, MatchResultRepository
from job_search.schemas.candidate import CandidateProfile
from job_search.schemas.job_offer import JobOfferCreate, JobSector, coerce_sector_id

logger = logging.getLogger(__name__)


@dataclass
class MatchRunSummary:
    evaluated: int = 0
    accepted: int = 0
    rejected: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)
    accepted_outcomes: list[MatchOutcome] = field(default_factory=list)


@dataclass
class RecommendationRow:
    offer_id: int
    title: str
    company: str
    source: str
    sector: str
    url: str
    recommended_at: object


def load_profile(profile_path: Path) -> CandidateProfile:
    """Load candidate profile from a JSON file."""
    data = json.loads(profile_path.read_text(encoding="utf-8"))
    return CandidateProfile.model_validate(data)


def offer_orm_to_schema(offer: JobOffer) -> JobOfferCreate:
    """Convert a JobOffer ORM entity into a JobOfferCreate schema."""
    skills = json.loads(offer.skills_json) if offer.skills_json else []
    return JobOfferCreate(
        external_id=offer.external_id,
        source=offer.source,
        title=offer.title,
        company=offer.company,
        location=offer.location,
        sector=offer.sector,
        description=offer.description,
        requirements=offer.requirements,
        skills=skills,
        salary_min=offer.salary_min,
        salary_max=offer.salary_max,
        currency=offer.currency,
        employment_type=offer.employment_type,
        remote=offer.remote,
        url=offer.url,
        posted_at=offer.posted_at,
    )


def match_pending_offers(
    profile: CandidateProfile,
    *,
    sector: JobSector | str | None = None,
    limit: int | None = None,
    session: Session | None = None,
) -> MatchRunSummary:
    """Evaluate unmatched offers for the given candidate profile."""
    owns_session = session is None
    if owns_session:
        engine = create_db_engine(get_settings().database_url)
        session_factory = sessionmaker(bind=engine)
        session = session_factory()

    summary = MatchRunSummary()
    try:
        embedding_service = EmbeddingService(session=session)
        semantic_matcher = SemanticMatcher(embedding_service)
        llm_evaluator = LLMEvaluator()
        offer_repo = JobOfferRepository(session)
        match_repo = MatchResultRepository(session)
        matching_engine = MatchingEngine(
            semantic_matcher=semantic_matcher,
            llm_evaluator=llm_evaluator,
            offer_repo=offer_repo,
            match_repo=match_repo,
        )

        sectors = (
            [coerce_sector_id(sector)]
            if sector is not None
            else list(profile.target_sectors)
        )

        offers: list[JobOffer] = []
        for target_sector in sectors:
            offers.extend(
                offer_repo.get_unmatched_offers(profile.name, target_sector)
            )

        if limit is not None:
            offers = offers[:limit]

        for offer in offers:
            try:
                outcome = matching_engine.evaluate_offer(
                    offer_orm_to_schema(offer),
                    profile,
                    job_offer_id=offer.id,
                )
            except Exception as exc:
                message = (
                    f"Offer id={offer.id} ({offer.title} @ {offer.company}): {exc}"
                )
                logger.error("Matching failed for single offer: %s", message)
                summary.failed += 1
                summary.errors.append(message)
                continue

            summary.evaluated += 1
            if outcome.decision == MatchDecisionEnum.ACCEPTED:
                summary.accepted += 1
                summary.accepted_outcomes.append(outcome)
            elif outcome.decision == MatchDecisionEnum.SKIPPED:
                summary.skipped += 1
            else:
                summary.rejected += 1

        if owns_session:
            session.commit()
    except Exception:
        if owns_session and session is not None:
            session.rollback()
        raise
    finally:
        if owns_session and session is not None:
            session.close()

    return summary


def list_recent_recommendations(
    candidate_name: str,
    *,
    sector: str | None = None,
    limit: int = 20,
    session: Session | None = None,
) -> list[RecommendationRow]:
    """Return recent recommendations for a candidate, newest first."""
    from job_search.memory.models import Recommendation

    owns_session = session is None
    if owns_session:
        engine = create_db_engine(get_settings().database_url)
        session_factory = sessionmaker(bind=engine)
        session = session_factory()

    try:
        stmt = (
            select(Recommendation, JobOffer)
            .join(JobOffer, JobOffer.id == Recommendation.job_offer_id)
            .where(Recommendation.candidate_name == candidate_name)
            .order_by(Recommendation.recommended_at.desc())
            .limit(limit)
        )
        if sector is not None:
            stmt = stmt.where(JobOffer.sector == sector)

        rows: list[RecommendationRow] = []
        for recommendation, offer in session.execute(stmt).all():
            rows.append(
                RecommendationRow(
                    offer_id=offer.id,
                    title=offer.title,
                    company=offer.company,
                    source=offer.source,
                    sector=offer.sector,
                    url=offer.url,
                    recommended_at=recommendation.recommended_at,
                )
            )
        return rows
    finally:
        if owns_session and session is not None:
            session.close()
