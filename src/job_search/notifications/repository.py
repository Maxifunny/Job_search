"""Query helpers for notification candidates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from job_search.memory.models import HiddenOffer, JobOffer, NotificationLog, Recommendation


@dataclass(frozen=True)
class NotifiableOffer:
    recommendation_id: int
    offer_id: int
    title: str
    company: str
    url: str
    source: str
    sector: str
    recommended_at: datetime
    llm_score: float | None


class NotificationRepository:
    """Read/write notification state."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_pending_email_offers(
        self,
        candidate_name: str,
        *,
        limit: int = 10,
    ) -> list[NotifiableOffer]:
        notified_ids = (
            select(NotificationLog.job_offer_id)
            .where(
                NotificationLog.candidate_name == candidate_name,
                NotificationLog.channel == "email",
            )
            .scalar_subquery()
        )
        hidden_ids = (
            select(HiddenOffer.job_offer_id)
            .where(HiddenOffer.candidate_name == candidate_name)
            .scalar_subquery()
        )

        stmt: Select = (
            select(Recommendation, JobOffer)
            .join(JobOffer, JobOffer.id == Recommendation.job_offer_id)
            .where(
                Recommendation.candidate_name == candidate_name,
                or_(
                    Recommendation.user_action.is_(None),
                    Recommendation.user_action != "applied",
                ),
                Recommendation.job_offer_id.not_in(notified_ids),
                Recommendation.job_offer_id.not_in(hidden_ids),
            )
            .order_by(Recommendation.recommended_at.desc())
            .limit(limit)
        )

        rows: list[NotifiableOffer] = []
        for recommendation, offer in self.session.execute(stmt).all():
            llm_score = self._latest_llm_score(offer.id, candidate_name)
            rows.append(
                NotifiableOffer(
                    recommendation_id=recommendation.id,
                    offer_id=offer.id,
                    title=offer.title,
                    company=offer.company,
                    url=offer.url,
                    source=offer.source,
                    sector=offer.sector,
                    recommended_at=recommendation.recommended_at,
                    llm_score=llm_score,
                )
            )
        return rows

    def _latest_llm_score(self, job_offer_id: int, candidate_name: str) -> float | None:
        from job_search.memory.models import MatchResult

        stmt = (
            select(MatchResult.llm_score)
            .where(
                MatchResult.job_offer_id == job_offer_id,
                MatchResult.candidate_name == candidate_name,
            )
            .order_by(MatchResult.evaluated_at.desc())
            .limit(1)
        )
        return self.session.scalar(stmt)

    def log_email_sent(
        self,
        *,
        job_offer_id: int,
        candidate_name: str,
        recipient: str,
        subject: str,
    ) -> NotificationLog:
        existing = self.session.scalar(
            select(NotificationLog).where(
                NotificationLog.job_offer_id == job_offer_id,
                NotificationLog.candidate_name == candidate_name,
                NotificationLog.channel == "email",
            )
        )
        if existing:
            return existing

        entry = NotificationLog(
            job_offer_id=job_offer_id,
            candidate_name=candidate_name,
            channel="email",
            recipient=recipient,
            subject=subject,
        )
        self.session.add(entry)
        self.session.flush()
        return entry

    def mark_applied(
        self,
        *,
        candidate_name: str,
        job_offer_id: int,
    ) -> Recommendation | None:
        recommendation = self.session.scalar(
            select(Recommendation).where(
                Recommendation.job_offer_id == job_offer_id,
                Recommendation.candidate_name == candidate_name,
            )
        )
        if recommendation is None:
            return None

        recommendation.user_action = "applied"

        hidden = self.session.scalar(
            select(HiddenOffer).where(
                HiddenOffer.job_offer_id == job_offer_id,
                HiddenOffer.candidate_name == candidate_name,
            )
        )
        if hidden is None:
            self.session.add(
                HiddenOffer(
                    job_offer_id=job_offer_id,
                    candidate_name=candidate_name,
                    reason="applied",
                )
            )
        else:
            hidden.reason = hidden.reason or "applied"

        self.session.flush()
        return recommendation
