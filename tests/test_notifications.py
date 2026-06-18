"""Tests for notification tokens, repository, and email digest."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session, sessionmaker

from config.settings import Settings
from job_search.memory.models import JobOffer, Recommendation
from job_search.notifications.email import EmailNotifier
from job_search.notifications.repository import NotificationRepository
from job_search.notifications.service import NotificationService
from job_search.notifications.templates import build_digest
from job_search.notifications.tokens import create_confirm_token, parse_confirm_token


def _add_offer(session: Session, *, offer_id: int | None = None) -> JobOffer:
    offer = JobOffer(
        id=offer_id,
        external_id=f"ext-{offer_id or 1}",
        source="justjoin",
        title="Junior Data Engineer",
        company="Acme",
        sector="data",
        description="Python SQL Spark",
        url=f"https://example.com/{offer_id or 1}",
        content_hash=f"hash-{offer_id or 1}",
        last_seen_at=datetime.now(UTC),
    )
    session.add(offer)
    session.flush()
    return offer


def test_confirm_token_roundtrip():
    token = create_confirm_token(
        candidate_name="default",
        job_offer_id=42,
        secret="test-secret",
    )
    payload = parse_confirm_token(token, secret="test-secret")
    assert payload.candidate_name == "default"
    assert payload.job_offer_id == 42


def test_repository_excludes_applied_and_already_emailed(sqlite_engine):
    session_factory = sessionmaker(bind=sqlite_engine)
    with session_factory() as session:
        offer1 = _add_offer(session, offer_id=1)
        offer2 = _add_offer(session, offer_id=2)
        offer3 = _add_offer(session, offer_id=3)
        session.add(
            Recommendation(
                job_offer_id=offer1.id,
                candidate_name="default",
                recommended_at=datetime.now(UTC),
            )
        )
        session.add(
            Recommendation(
                job_offer_id=offer2.id,
                candidate_name="default",
                user_action="applied",
                recommended_at=datetime.now(UTC),
            )
        )
        session.add(
            Recommendation(
                job_offer_id=offer3.id,
                candidate_name="default",
                recommended_at=datetime.now(UTC),
            )
        )
        session.commit()

        repo = NotificationRepository(session)
        repo.log_email_sent(
            job_offer_id=offer3.id,
            candidate_name="default",
            recipient="me@example.com",
            subject="test",
        )
        session.commit()

        pending = repo.list_pending_email_offers("default", limit=10)
        assert len(pending) == 1
        assert pending[0].offer_id == offer1.id


def test_mark_applied_hides_offer_from_pending(sqlite_engine):
    session_factory = sessionmaker(bind=sqlite_engine)
    with session_factory() as session:
        offer = _add_offer(session, offer_id=5)
        session.add(
            Recommendation(
                job_offer_id=offer.id,
                candidate_name="default",
                recommended_at=datetime.now(UTC),
            )
        )
        session.commit()

        repo = NotificationRepository(session)
        repo.mark_applied(candidate_name="default", job_offer_id=offer.id)
        session.commit()

        pending = repo.list_pending_email_offers("default", limit=10)
        assert pending == []


def test_build_digest_contains_confirm_command():
    digest = build_digest(
        candidate_name="default",
        offers=[
            {
                "offer_id": 7,
                "title": "Data Engineer",
                "company": "Acme",
                "url": "https://example.com/7",
                "source": "justjoin",
                "recommended_at": "2026-01-01",
                "llm_score": 0.8,
            }
        ],
        secret="secret-key",
    )
    assert "Data Engineer" in digest.text_body
    assert "notify confirm --token" in digest.text_body
    assert "mark-applied" in digest.text_body


def test_send_email_digest_sends_and_logs(sqlite_engine):
    session_factory = sessionmaker(bind=sqlite_engine)
    with session_factory() as session:
        offer = _add_offer(session, offer_id=10)
        session.add(
            Recommendation(
                job_offer_id=offer.id,
                candidate_name="default",
                recommended_at=datetime.now(UTC),
            )
        )
        session.commit()

        settings = Settings(
            _env_file=None,
            NOTIFIER_SECRET="secret",
            SMTP_HOST="smtp.example.com",
            SMTP_FROM="jobsearch@example.com",
            SMTP_TO="user@example.com",
            NOTIFIER_MAX_OFFERS=10,
        )
        email_notifier = EmailNotifier(settings)
        service = NotificationService(settings=settings, email_notifier=email_notifier)

        with patch.object(email_notifier, "send", return_value=["user@example.com"]) as mock_send:
            result = service.send_email_digest("default", session=session)
            session.commit()

        assert result.sent == 1
        mock_send.assert_called_once()
        repo = NotificationRepository(session)
        pending = repo.list_pending_email_offers("default", limit=10)
        assert pending == []


def test_send_email_digest_dry_run_does_not_send(sqlite_engine):
    session_factory = sessionmaker(bind=sqlite_engine)
    with session_factory() as session:
        offer = _add_offer(session, offer_id=11)
        session.add(
            Recommendation(
                job_offer_id=offer.id,
                candidate_name="default",
                recommended_at=datetime.now(UTC),
            )
        )
        session.commit()

        settings = Settings(
            _env_file=None,
            NOTIFIER_SECRET="secret",
            SMTP_HOST="smtp.example.com",
            SMTP_FROM="jobsearch@example.com",
            SMTP_TO="user@example.com",
        )
        email_notifier = EmailNotifier(settings)
        service = NotificationService(settings=settings, email_notifier=email_notifier)

        with patch.object(email_notifier, "send") as mock_send:
            result = service.send_email_digest("default", session=session, dry_run=True)

        assert result.skipped == 1
        assert result.sent == 0
        mock_send.assert_not_called()
