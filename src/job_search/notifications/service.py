"""High-level notification orchestration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from config.settings import Settings, get_settings
from job_search.memory.database import create_db_engine
from job_search.memory.models import Recommendation
from job_search.notifications.email import EmailNotifier
from job_search.notifications.repository import NotificationRepository
from job_search.notifications.templates import build_digest
from job_search.notifications.tokens import parse_confirm_token

logger = logging.getLogger(__name__)


@dataclass
class NotificationResult:
    sent: int = 0
    skipped: int = 0
    recipients: list[str] = field(default_factory=list)
    subject: str | None = None
    errors: list[str] = field(default_factory=list)


class NotificationService:
    """Email digest for top pending recommendations."""

    def __init__(
        self,
        settings: Settings | None = None,
        email_notifier: EmailNotifier | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.email_notifier = email_notifier or EmailNotifier(self.settings)

    def _effective_secret(self) -> str:
        if self.settings.notifier_secret:
            return self.settings.notifier_secret
        if self.settings.smtp_password:
            return self.settings.smtp_password
        raise RuntimeError(
            "Ustaw NOTIFIER_SECRET (lub SMTP_PASSWORD) do podpisywania tokenów potwierdzenia."
        )

    def send_email_digest(
        self,
        candidate_name: str,
        *,
        limit: int | None = None,
        session: Session | None = None,
        dry_run: bool = False,
    ) -> NotificationResult:
        owns_session = session is None
        if owns_session:
            engine = create_db_engine(self.settings.database_url)
            session_factory = sessionmaker(bind=engine)
            session = session_factory()

        result = NotificationResult()
        max_offers = limit if limit is not None else self.settings.notifier_max_offers

        try:
            if not self.email_notifier.is_configured():
                raise RuntimeError(
                    "SMTP nie jest skonfigurowane (SMTP_HOST, SMTP_FROM, SMTP_TO)."
                )

            repo = NotificationRepository(session)
            pending = repo.list_pending_email_offers(candidate_name, limit=max_offers)
            if not pending:
                logger.info(
                    "Brak nowych ofert do wysłania mailem dla profilu %s", candidate_name
                )
                return result

            offer_rows = [
                {
                    "offer_id": item.offer_id,
                    "title": item.title,
                    "company": item.company,
                    "url": item.url,
                    "source": item.source,
                    "recommended_at": item.recommended_at.isoformat(),
                    "llm_score": item.llm_score,
                }
                for item in pending
            ]
            digest = build_digest(
                candidate_name=candidate_name,
                offers=offer_rows,
                secret=self._effective_secret(),
                public_base_url=self.settings.notifier_public_base_url,
            )
            result.subject = digest.subject

            if dry_run:
                result.skipped = len(pending)
                return result

            recipients = self.email_notifier.send(
                subject=digest.subject,
                text_body=digest.text_body,
                html_body=digest.html_body,
            )
            result.recipients = recipients
            recipient_label = ", ".join(recipients)

            for item in pending:
                repo.log_email_sent(
                    job_offer_id=item.offer_id,
                    candidate_name=candidate_name,
                    recipient=recipient_label,
                    subject=digest.subject,
                )
                recommendation = session.scalar(
                    select(Recommendation).where(Recommendation.id == item.recommendation_id)
                )
                if recommendation is not None:
                    recommendation.channel = "email"

            result.sent = len(pending)

            if owns_session:
                session.commit()
        except Exception:
            if owns_session and session is not None:
                session.rollback()
            raise
        finally:
            if owns_session and session is not None:
                session.close()

        return result

    def confirm_applied_from_token(self, token: str, *, session: Session | None = None) -> str:
        payload = parse_confirm_token(token, secret=self._effective_secret())
        return self.mark_applied(
            candidate_name=payload.candidate_name,
            job_offer_id=payload.job_offer_id,
            session=session,
        )

    def mark_applied(
        self,
        *,
        candidate_name: str,
        job_offer_id: int,
        session: Session | None = None,
    ) -> str:
        owns_session = session is None
        if owns_session:
            engine = create_db_engine(self.settings.database_url)
            session_factory = sessionmaker(bind=engine)
            session = session_factory()

        try:
            repo = NotificationRepository(session)
            recommendation = repo.mark_applied(
                candidate_name=candidate_name,
                job_offer_id=job_offer_id,
            )
            if recommendation is None:
                raise ValueError(
                    f"Nie znaleziono rekomendacji dla oferty id={job_offer_id} "
                    f"i profilu '{candidate_name}'."
                )
            if owns_session:
                session.commit()
        except Exception:
            if owns_session and session is not None:
                session.rollback()
            raise
        finally:
            if owns_session and session is not None:
                session.close()

        return (
            f"Oferta id={job_offer_id} oznaczona jako zaaplikowana. "
            "Nie będzie już wysyłana mailem."
        )
