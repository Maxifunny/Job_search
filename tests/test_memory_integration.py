"""Integration tests for relational and vector memory."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session, sessionmaker

from config.settings import Settings
from job_search.memory.embeddings import EmbeddingService, build_offer_document
from job_search.memory.models import JobOffer, MatchDecisionEnum
from job_search.memory.repositories import (
    JobOfferRepository,
    MatchResultRepository,
    UserPreferenceRepository,
)
from job_search.memory.vector_store import VectorMemory
from job_search.schemas.job_offer import JobOfferCreate, JobSector


def _sample_offer(**overrides) -> JobOfferCreate:
    payload = dict(
        external_id="jj-100",
        source="justjoin",
        title="Data Engineer",
        company="Acme Corp",
        sector=JobSector.DATA,
        description="Build data pipelines with Python, SQL, and Spark.",
        skills=["Python", "SQL", "Spark"],
        url="https://example.com/jobs/100",
    )
    payload.update(overrides)
    return JobOfferCreate(**payload)


@pytest.fixture
def db_session(sqlite_engine) -> Session:
    session_factory = sessionmaker(bind=sqlite_engine)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture
def chroma_settings(tmp_path: Path) -> Settings:
    return Settings(
        chroma_persist_dir=tmp_path / "chroma",
        chroma_collection_offers="test_offers",
        chroma_collection_preferences="test_preferences",
        embedding_model="test-embedding-model",
    )


class MockEmbeddingService(EmbeddingService):
    """Deterministic embeddings for tests without OpenAI calls."""

    def embed_text(self, text: str) -> list[float]:
        cached = self._load_cached(text)
        if cached is not None:
            return cached

        text_lower = text.lower()
        vector = [
            float("python" in text_lower),
            float("sql" in text_lower),
            float("spark" in text_lower),
            float("plc" in text_lower or "automation" in text_lower),
            float("data" in text_lower),
        ]
        self._save_cache(text, vector)
        return vector


def test_build_offer_document_includes_title_description_skills():
    offer = _sample_offer()
    document = build_offer_document(offer)
    assert "Data Engineer" in document
    assert "Python, SQL, Spark" in document
    assert "data pipelines" in document


def test_upsert_same_offer_twice_updates_last_seen(db_session: Session):
    repo = JobOfferRepository(db_session)
    offer = _sample_offer()

    _, is_new_first = repo.upsert(offer)
    first = repo.get_by_source_and_external_id(offer.source, offer.external_id)
    assert is_new_first is True
    assert first is not None
    first_seen = first.last_seen_at

    db_session.commit()
    _, is_new_second = repo.upsert(offer)
    second = repo.get_by_source_and_external_id(offer.source, offer.external_id)

    assert is_new_second is False
    assert second is not None
    assert second.last_seen_at >= first_seen


def test_was_already_recommended_after_mark_recommended(db_session: Session):
    repo = JobOfferRepository(db_session)
    offer, _ = repo.upsert(_sample_offer())
    db_session.flush()

    assert repo.was_already_recommended(offer.id, "alice") is False
    repo.mark_recommended(offer.id, "alice", channel="email")
    db_session.flush()
    assert repo.was_already_recommended(offer.id, "alice") is True


def test_duplicate_source_external_id_not_inserted_twice(db_session: Session):
    repo = JobOfferRepository(db_session)
    first, is_new_first = repo.upsert(_sample_offer())
    second, is_new_second = repo.upsert(_sample_offer())

    assert is_new_first is True
    assert is_new_second is False
    assert first.id == second.id
    assert db_session.query(JobOffer).count() == 1


def test_get_unmatched_offers_excludes_matched(db_session: Session):
    offer_repo = JobOfferRepository(db_session)
    match_repo = MatchResultRepository(db_session)

    offer_a, _ = offer_repo.upsert(_sample_offer(external_id="a"))
    offer_b, _ = offer_repo.upsert(
        _sample_offer(external_id="b", title="Data Analyst", skills=["SQL"])
    )
    db_session.flush()

    match_repo.save_result(
        job_offer_id=offer_a.id,
        candidate_name="bob",
        semantic_score=0.9,
        llm_score=0.85,
        llm_confidence=0.8,
        decision=MatchDecisionEnum.ACCEPTED,
    )
    db_session.flush()

    unmatched = offer_repo.get_unmatched_offers("bob", "data")
    unmatched_ids = {offer.id for offer in unmatched}

    assert offer_a.id not in unmatched_ids
    assert offer_b.id in unmatched_ids


def test_deactivate_stale_offers(db_session: Session):
    repo = JobOfferRepository(db_session)
    offer, _ = repo.upsert(_sample_offer())
    db_session.flush()

    offer.last_seen_at = datetime.now(UTC) - timedelta(days=45)
    db_session.flush()

    updated = repo.deactivate_stale_offers("justjoin", older_than_days=30)
    db_session.refresh(offer)

    assert updated == 1
    assert offer.is_active is False


def test_user_preference_save_and_load(db_session: Session):
    repo = UserPreferenceRepository(db_session)
    profile = {"skills": ["Python", "SQL"], "locations": ["Warsaw", "Remote"]}

    repo.save_profile("carol", profile)
    loaded = repo.load_profile("carol")

    assert loaded == profile

    updated = {"skills": ["Python", "Spark"], "locations": ["Krakow"]}
    repo.save_profile("carol", updated)
    assert repo.load_profile("carol") == updated


def test_upsert_syncs_vector_store(db_session: Session, chroma_settings: Settings):
    vector_memory = VectorMemory(chroma_settings)
    embedding_service = MockEmbeddingService(session=db_session, settings=chroma_settings)
    repo = JobOfferRepository(
        db_session,
        vector_memory=vector_memory,
        embedding_service=embedding_service,
    )

    offer, _ = repo.upsert(_sample_offer())
    db_session.flush()

    stored = vector_memory.offers.get(ids=[str(offer.id)])
    assert stored["ids"] == [str(offer.id)]
    assert "Data Engineer" in stored["documents"][0]


def test_query_similar_offers_by_profile_embedding(
    db_session: Session, chroma_settings: Settings
):
    vector_memory = VectorMemory(chroma_settings)
    embedding_service = MockEmbeddingService(session=db_session, settings=chroma_settings)
    repo = JobOfferRepository(
        db_session,
        vector_memory=vector_memory,
        embedding_service=embedding_service,
    )

    data_offer, _ = repo.upsert(_sample_offer(external_id="data-1"))
    repo.upsert(
        _sample_offer(
            external_id="auto-1",
            title="PLC Programmer",
            description="Program PLCs and automation systems.",
            skills=["PLC", "Siemens"],
            sector=JobSector.AUTOMATION,
        )
    )
    db_session.flush()

    profile_text = "Experienced data engineer with Python, SQL, and Spark skills."
    profile_embedding = embedding_service.embed_text(profile_text)
    results = vector_memory.query_similar_offers(profile_embedding, n_results=2)

    assert results["ids"][0]
    top_id = results["ids"][0][0]
    assert top_id == str(data_offer.id)


def test_embedding_cache_avoids_duplicate_api_calls(db_session: Session):
    mock_client = MagicMock()
    mock_client.embeddings.create.return_value = MagicMock(
        data=[MagicMock(embedding=[0.1, 0.2, 0.3])]
    )
    service = EmbeddingService(session=db_session, client=mock_client)

    first = service.embed_text("same text")
    second = service.embed_text("same text")

    assert first == second
    mock_client.embeddings.create.assert_called_once()


def test_embedding_logs_quota_from_raw_response_headers(db_session: Session, caplog):
    parsed_response = MagicMock(
        data=[MagicMock(embedding=[0.1, 0.2, 0.3])],
        usage=MagicMock(prompt_tokens=12, total_tokens=12),
    )
    raw_response = MagicMock(
        headers={
            "x-ratelimit-remaining-requests": "111",
            "x-ratelimit-remaining-tokens": "150000",
        }
    )
    raw_response.parse.return_value = parsed_response

    mock_client = MagicMock()
    mock_client.embeddings.with_raw_response.create.return_value = raw_response
    service = EmbeddingService(
        session=db_session,
        client=mock_client,
        settings=Settings(LLM_API_KEY="sk-test-0007", LOG_API_QUOTA=True),
    )

    with caplog.at_level("INFO"):
        service.embed_text("quota logs test")

    assert any("api_usage endpoint=embeddings.create" in rec.message for rec in caplog.records)
    assert any("remaining(requests=111,tokens=150000)" in rec.message for rec in caplog.records)
    assert any("key=***0007" in rec.message for rec in caplog.records)


def test_embedding_logs_provider_quota_fallback_without_headers(
    db_session: Session, caplog
):
    mock_client = MagicMock()
    mock_client.embeddings.create.return_value = MagicMock(
        data=[MagicMock(embedding=[0.5, 0.6, 0.7])],
        usage=MagicMock(prompt_tokens=5, total_tokens=5),
    )
    service = EmbeddingService(
        session=db_session,
        client=mock_client,
        settings=Settings(LLM_API_KEY="sk-test-1111", LOG_API_QUOTA=True),
    )

    with caplog.at_level("INFO"):
        service.embed_text("fallback quota logs test")

    assert any(
        "remaining_quota=not_exposed_by_provider" in rec.message
        for rec in caplog.records
    )
