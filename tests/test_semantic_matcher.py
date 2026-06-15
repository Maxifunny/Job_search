"""Tests for SemanticMatcher."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import sessionmaker

from config.settings import Settings
from job_search.matching.engine import MatchingEngine
from job_search.matching.llm_evaluator import LLMEvaluator
from job_search.matching.semantic_matcher import (
    SemanticMatcher,
    build_profile_document,
    cosine_similarity,
)
from job_search.memory.models import MatchDecisionEnum
from job_search.memory.repositories import JobOfferRepository, MatchResultRepository
from job_search.schemas.candidate import CandidateProfile, SkillEntry
from job_search.schemas.job_offer import JobOfferCreate, JobSector
from tests.conftest import MockEmbeddingService


@pytest.fixture
def data_profile() -> CandidateProfile:
    return CandidateProfile(
        name="tester",
        target_roles=["Data Engineer", "Data Analyst"],
        skills=[
            SkillEntry(name="Python", years=3),
            SkillEntry(name="SQL", years=4),
            SkillEntry(name="Pandas", years=2),
        ],
        cv_text="Data engineer with Python, SQL, and pandas experience.",
    )


def test_build_profile_document_includes_roles_skills_cv_and_notes():
    profile = CandidateProfile(
        target_roles=["Data Engineer"],
        skills=[SkillEntry(name="Python")],
        cv_text="Experienced analyst.",
        notes="Open to remote roles.",
    )
    document = build_profile_document(profile)

    assert "Data Engineer" in document
    assert "Python" in document
    assert "Experienced analyst." in document
    assert "Open to remote roles." in document


def test_cosine_similarity_returns_value_in_zero_one_range():
    left = [1.0, 0.0, 0.0]
    right = [1.0, 0.0, 0.0]
    assert cosine_similarity(left, right) == pytest.approx(1.0)


def test_semantic_score_high_for_data_engineer_offer(data_profile: CandidateProfile):
    matcher = SemanticMatcher(MockEmbeddingService())
    offer = JobOfferCreate(
        external_id="1",
        source="justjoin",
        title="Data Engineer",
        company="Acme",
        sector=JobSector.DATA,
        description="Build pipelines with Python, SQL, and pandas.",
        skills=["Python", "SQL", "Pandas"],
        url="https://example.com/1",
    )

    score = matcher.score(offer, data_profile)
    assert score > 0.7


def test_semantic_score_low_for_data_entry_offer(data_profile: CandidateProfile):
    matcher = SemanticMatcher(MockEmbeddingService())
    offer = JobOfferCreate(
        external_id="2",
        source="justjoin",
        title="Data Entry Clerk",
        company="Acme",
        sector=JobSector.DATA,
        description="Manual data input and document scanning.",
        url="https://example.com/2",
    )

    score = matcher.score(offer, data_profile)
    assert score < 0.5


def test_matching_engine_accepts_data_engineer_with_mock_llm(
    data_profile: CandidateProfile,
    sqlite_engine,
):
    session_factory = sessionmaker(bind=sqlite_engine)
    session = session_factory()

    offer_repo = JobOfferRepository(session)
    match_repo = MatchResultRepository(session)
    offer, _ = offer_repo.upsert(
        JobOfferCreate(
            external_id="de-1",
            source="justjoin",
            title="Data Engineer (Python, SQL)",
            company="TechCorp",
            sector=JobSector.DATA,
            description="Python, SQL, and pandas pipelines.",
            skills=["Python", "SQL", "Pandas"],
            url="https://example.com/de-1",
        )
    )
    session.flush()

    llm_evaluator = LLMEvaluator(
        settings=Settings(LLM_API_KEY="test-key"),
        client=MagicMock(),
    )
    llm_evaluator.client.chat.completions.create.return_value = MagicMock(
        choices=[
            MagicMock(
                message=MagicMock(
                    content=(
                        '{"score": 0.9, "confidence": 0.95, '
                        '"is_relevant_role": true, '
                        '"matched_skills": ["Python", "SQL"], '
                        '"missing_skills": [], '
                        '"explanation": "Strong match."}'
                    )
                )
            )
        ]
    )

    engine = MatchingEngine(
        semantic_matcher=SemanticMatcher(MockEmbeddingService()),
        llm_evaluator=llm_evaluator,
        offer_repo=offer_repo,
        match_repo=match_repo,
    )
    outcome = engine.evaluate_offer(
        JobOfferCreate(
            external_id=offer.external_id,
            source=offer.source,
            title=offer.title,
            company=offer.company,
            sector=JobSector.DATA,
            description=offer.description,
            skills=["Python", "SQL", "Pandas"],
            url=offer.url,
        ),
        data_profile,
        job_offer_id=offer.id,
    )

    assert outcome.decision == MatchDecisionEnum.ACCEPTED
    assert offer_repo.was_already_recommended(offer.id, data_profile.name) is True

    unmatched = offer_repo.get_unmatched_offers(data_profile.name, "data")
    assert all(item.id != offer.id for item in unmatched)

    session.close()


def test_same_offer_candidate_pair_not_evaluated_twice(
    data_profile: CandidateProfile,
    sqlite_engine,
):
    from sqlalchemy.orm import sessionmaker

    session_factory = sessionmaker(bind=sqlite_engine)
    session = session_factory()

    offer_repo = JobOfferRepository(session)
    match_repo = MatchResultRepository(session)
    offer, _ = offer_repo.upsert(
        JobOfferCreate(
            external_id="de-2",
            source="justjoin",
            title="Data Engineer",
            company="TechCorp",
            sector=JobSector.DATA,
            description="Python and SQL.",
            skills=["Python", "SQL"],
            url="https://example.com/de-2",
        )
    )
    session.flush()

    llm_evaluator = LLMEvaluator(
        settings=Settings(LLM_API_KEY="test-key"),
        client=MagicMock(),
    )
    llm_evaluator.client.chat.completions.create.return_value = MagicMock(
        choices=[
            MagicMock(
                message=MagicMock(
                    content=(
                        '{"score": 0.2, "confidence": 0.2, '
                        '"is_relevant_role": false, '
                        '"matched_skills": [], '
                        '"missing_skills": ["Spark"], '
                        '"explanation": "Weak match."}'
                    )
                )
            )
        ]
    )

    engine = MatchingEngine(
        semantic_matcher=SemanticMatcher(MockEmbeddingService()),
        llm_evaluator=llm_evaluator,
        offer_repo=offer_repo,
        match_repo=match_repo,
    )
    schema = JobOfferCreate(
        external_id=offer.external_id,
        source=offer.source,
        title=offer.title,
        company=offer.company,
        sector=JobSector.DATA,
        description=offer.description,
        skills=["Python", "SQL"],
        url=offer.url,
    )

    engine.evaluate_offer(schema, data_profile, job_offer_id=offer.id)
    session.flush()

    unmatched_ids = {
        item.id
        for item in offer_repo.get_unmatched_offers(data_profile.name, "data")
    }
    assert offer.id not in unmatched_ids

    session.close()
