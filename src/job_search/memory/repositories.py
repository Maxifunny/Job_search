"""Repository layer for relational memory operations."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from job_search.memory.embeddings import EmbeddingService, build_offer_document
from job_search.memory.models import (
    JobOffer,
    MatchDecisionEnum,
    MatchResult,
    Recommendation,
    ScrapeRun,
    UserPreference,
)
from job_search.schemas.job_offer import JobOfferCreate

if TYPE_CHECKING:
    from job_search.memory.vector_store import VectorMemory


def compute_content_hash(offer: JobOfferCreate) -> str:
    """Stable hash for deduplication across re-scrapes."""
    payload = "|".join(
        [
            offer.source,
            offer.external_id,
            offer.title.strip().lower(),
            offer.company.strip().lower(),
            offer.description.strip().lower(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class JobOfferRepository:
    """CRUD and deduplication helpers for job offers."""

    def __init__(
        self,
        session: Session,
        *,
        vector_memory: VectorMemory | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self.session = session
        self.vector_memory = vector_memory
        self.embedding_service = embedding_service

    def get_by_source_and_external_id(
        self, source: str, external_id: str
    ) -> JobOffer | None:
        stmt = select(JobOffer).where(
            JobOffer.source == source, JobOffer.external_id == external_id
        )
        return self.session.scalar(stmt)

    def upsert(self, offer: JobOfferCreate) -> tuple[JobOffer, bool]:
        """
        Insert or update an offer.

        Returns (job_offer, is_new).
        """
        existing = self.get_by_source_and_external_id(offer.source, offer.external_id)
        now = datetime.now(UTC)
        content_hash = compute_content_hash(offer)

        if existing:
            existing.title = offer.title
            existing.company = offer.company
            existing.location = offer.location
            existing.description = offer.description
            existing.requirements = offer.requirements
            existing.skills_json = json.dumps(offer.skills, ensure_ascii=False)
            existing.salary_min = offer.salary_min
            existing.salary_max = offer.salary_max
            existing.currency = offer.currency
            existing.employment_type = offer.employment_type
            existing.remote = offer.remote
            existing.url = str(offer.url)
            existing.content_hash = content_hash
            existing.posted_at = offer.posted_at
            existing.last_seen_at = now
            existing.is_active = True
            self._sync_vector(existing, offer)
            return existing, False

        entity = JobOffer(
            external_id=offer.external_id,
            source=offer.source,
            title=offer.title,
            company=offer.company,
            location=offer.location,
            sector=offer.sector,
            description=offer.description,
            requirements=offer.requirements,
            skills_json=json.dumps(offer.skills, ensure_ascii=False),
            salary_min=offer.salary_min,
            salary_max=offer.salary_max,
            currency=offer.currency,
            employment_type=offer.employment_type,
            remote=offer.remote,
            url=str(offer.url),
            content_hash=content_hash,
            posted_at=offer.posted_at,
            first_seen_at=now,
            last_seen_at=now,
            is_active=True,
        )
        self.session.add(entity)
        self.session.flush()
        self._sync_vector(entity, offer)
        return entity, True

    def _sync_vector(self, entity: JobOffer, offer: JobOfferCreate) -> None:
        if self.vector_memory is None:
            return
        document = build_offer_document(offer)
        embedding = None
        if self.embedding_service is not None:
            embedding = self.embedding_service.embed_text(document)
        self.vector_memory.upsert_job_offer(
            offer_id=str(entity.id),
            document=document,
            metadata={
                "source": entity.source,
                "sector": entity.sector,
                "company": entity.company,
                "title": entity.title,
            },
            embedding=embedding,
        )

    def was_already_recommended(
        self, job_offer_id: int, candidate_name: str = "default"
    ) -> bool:
        stmt = select(Recommendation.id).where(
            Recommendation.job_offer_id == job_offer_id,
            Recommendation.candidate_name == candidate_name,
        )
        return self.session.scalar(stmt) is not None

    def get_unmatched_offers(
        self,
        candidate_name: str,
        sector: str,
    ) -> list[JobOffer]:
        """Return active offers without a match result for the given candidate."""
        matched_ids = (
            select(MatchResult.job_offer_id)
            .where(MatchResult.candidate_name == candidate_name)
            .scalar_subquery()
        )
        stmt = (
            select(JobOffer)
            .where(
                JobOffer.sector == sector,
                JobOffer.is_active.is_(True),
                JobOffer.id.not_in(matched_ids),
            )
            .order_by(JobOffer.last_seen_at.desc())
        )
        return list(self.session.scalars(stmt).all())

    def mark_recommended(
        self,
        job_offer_id: int,
        candidate_name: str,
        channel: str | None = None,
    ) -> Recommendation:
        """Record that an offer was recommended to prevent duplicate suggestions."""
        existing = self.session.scalar(
            select(Recommendation).where(
                Recommendation.job_offer_id == job_offer_id,
                Recommendation.candidate_name == candidate_name,
            )
        )
        if existing:
            return existing

        recommendation = Recommendation(
            job_offer_id=job_offer_id,
            candidate_name=candidate_name,
            channel=channel,
        )
        self.session.add(recommendation)
        self.session.flush()
        return recommendation

    def deactivate_stale_offers(
        self,
        source: str,
        older_than_days: int = 30,
    ) -> int:
        """Mark offers not seen recently as inactive. Returns count updated."""
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
        stmt = select(JobOffer).where(
            JobOffer.source == source,
            JobOffer.is_active.is_(True),
            JobOffer.last_seen_at < cutoff,
        )
        offers = list(self.session.scalars(stmt).all())
        for offer in offers:
            offer.is_active = False
        if offers:
            self.session.flush()
        return len(offers)


class MatchResultRepository:
    """Store and query LLM/semantic evaluation outcomes."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def save_result(
        self,
        *,
        job_offer_id: int,
        candidate_name: str,
        semantic_score: float | None,
        llm_score: float | None,
        llm_confidence: float | None,
        decision: MatchDecisionEnum,
        rejection_reason: str | None = None,
        matched_skills: list[str] | None = None,
        missing_skills: list[str] | None = None,
        llm_explanation: str | None = None,
    ) -> MatchResult:
        result = MatchResult(
            job_offer_id=job_offer_id,
            candidate_name=candidate_name,
            semantic_score=semantic_score,
            llm_score=llm_score,
            llm_confidence=llm_confidence,
            decision=decision,
            rejection_reason=rejection_reason,
            matched_skills_json=json.dumps(matched_skills or [], ensure_ascii=False),
            missing_skills_json=json.dumps(missing_skills or [], ensure_ascii=False),
            llm_explanation=llm_explanation,
        )
        self.session.add(result)
        self.session.flush()
        return result


class ScrapeRunRepository:
    """Track scraper execution history."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def start_run(self, source: str, sector: str) -> ScrapeRun:
        run = ScrapeRun(source=source, sector=sector, status="running")
        self.session.add(run)
        self.session.flush()
        return run

    def finish_run(
        self,
        run: ScrapeRun,
        *,
        offers_found: int,
        offers_new: int,
        offers_updated: int,
        status: str = "success",
        error_message: str | None = None,
    ) -> None:
        run.finished_at = datetime.now(UTC)
        run.offers_found = offers_found
        run.offers_new = offers_new
        run.offers_updated = offers_updated
        run.status = status
        run.error_message = error_message


class UserPreferenceRepository:
    """Persist and load structured candidate profiles."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def save_profile(self, candidate_name: str, profile: dict) -> UserPreference:
        existing = self.session.scalar(
            select(UserPreference).where(UserPreference.candidate_name == candidate_name)
        )
        profile_json = json.dumps(profile, ensure_ascii=False)
        if existing:
            existing.profile_json = profile_json
            existing.updated_at = datetime.now(UTC)
            self.session.flush()
            return existing

        entity = UserPreference(
            candidate_name=candidate_name,
            profile_json=profile_json,
        )
        self.session.add(entity)
        self.session.flush()
        return entity

    def load_profile(self, candidate_name: str) -> dict | None:
        entity = self.session.scalar(
            select(UserPreference).where(UserPreference.candidate_name == candidate_name)
        )
        if entity is None:
            return None
        return json.loads(entity.profile_json)
