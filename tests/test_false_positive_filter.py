"""Tests for FalsePositiveFilter."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from config.settings import Settings
from job_search.matching.engine import MatchingEngine
from job_search.matching.filters import FalsePositiveFilter
from job_search.matching.llm_evaluator import LLMEvaluator
from job_search.matching.semantic_matcher import SemanticMatcher
from job_search.memory.models import MatchDecisionEnum
from job_search.memory.repositories import JobOfferRepository, MatchResultRepository
from job_search.schemas.candidate import CandidateProfile, SkillEntry
from job_search.schemas.job_offer import JobOfferCreate, JobSector
from tests.conftest import MockEmbeddingService


@pytest.fixture
def profile() -> CandidateProfile:
    return CandidateProfile(
        name="default",
        target_roles=["Data Engineer", "Data Analyst"],
        skills=[
            SkillEntry(name="Python"),
            SkillEntry(name="SQL"),
            SkillEntry(name="Pandas"),
        ],
        excluded_keywords=["staż bez wynagrodzenia"],
        cv_text="Data and analytics background.",
    )


def _offer(**overrides) -> JobOfferCreate:
    payload = dict(
        external_id="1",
        source="justjoin",
        title="Placeholder",
        company="Acme",
        sector=JobSector.DATA,
        description="Generic description.",
        url="https://example.com/1",
    )
    payload.update(overrides)
    return JobOfferCreate(**payload)


@pytest.mark.parametrize(
    ("title", "description", "skills", "expected"),
    [
        ("Data Entry Specialist", "Typing and scanning documents.", [], True),
        (
            "Data Entry Specialist",
            "Python, SQL analytics and reporting.",
            ["Python", "SQL"],
            False,
        ),
        ("Specjalista ds. wprowadzania danych", "Office administration.", [], True),
        (
            "Data Engineer",
            "Build Python and SQL pipelines.",
            ["Python", "SQL"],
            False,
        ),
    ],
)
def test_data_sector_false_positive_rules(
    profile, title, description, skills, expected
):
    offer = _offer(title=title, description=description, skills=skills)
    rejected, reason = FalsePositiveFilter.should_reject(offer, profile)

    assert rejected is expected
    if expected:
        assert reason is not None


@pytest.mark.parametrize(
    ("title", "description", "expected"),
    [
        ("Operator produkcji", "Obsługa linii produkcyjnej.", True),
        ("Monter instalacji", "Prace montażowe na hali.", True),
        ("Monter PLC", "Programowanie PLC i SCADA.", False),
        ("Automatyk", "Konfiguracja TIA Portal i SCADA.", False),
    ],
)
def test_automation_sector_false_positive_rules(title, description, expected):
    profile = CandidateProfile(
        target_roles=["Programista PLC"],
        skills=[SkillEntry(name="TIA Portal")],
    )
    offer = _offer(
        title=title,
        description=description,
        sector=JobSector.AUTOMATION,
    )
    rejected, reason = FalsePositiveFilter.should_reject(offer, profile)

    assert rejected is expected
    if expected:
        assert reason is not None


def test_excluded_keywords_from_profile_are_respected(profile):
    offer = _offer(title="Staż bez wynagrodzenia - Data Analyst")
    rejected, reason = FalsePositiveFilter.should_reject(offer, profile)

    assert rejected is True
    assert reason is not None
    assert "staż bez wynagrodzenia" in reason.lower()


def test_matching_engine_rejects_data_entry_before_llm(profile, sqlite_engine):
    from sqlalchemy.orm import sessionmaker

    session_factory = sessionmaker(bind=sqlite_engine)
    session = session_factory()

    offer_repo = JobOfferRepository(session)
    match_repo = MatchResultRepository(session)
    offer, _ = offer_repo.upsert(
        _offer(
            external_id="entry-1",
            title="Data Entry",
            description="Manual typing and document scanning.",
        )
    )
    session.flush()

    llm_evaluator = LLMEvaluator()
    engine = MatchingEngine(
        semantic_matcher=SemanticMatcher(MockEmbeddingService()),
        llm_evaluator=llm_evaluator,
        offer_repo=offer_repo,
        match_repo=match_repo,
    )

    outcome = engine.evaluate_offer(
        _offer(
            external_id=offer.external_id,
            source=offer.source,
            title=offer.title,
            company=offer.company,
            description=offer.description,
            url=offer.url,
        ),
        profile,
        job_offer_id=offer.id,
    )

    assert outcome.decision == MatchDecisionEnum.REJECTED
    assert outcome.reason is not None
    assert "false positive" in outcome.reason.lower()

    session.close()
