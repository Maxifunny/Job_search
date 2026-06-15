"""Tests for LLMEvaluator."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from config.settings import Settings
from job_search.matching.llm_evaluator import LLMEvaluator
from job_search.schemas.candidate import CandidateProfile, SkillEntry
from job_search.schemas.job_offer import JobOfferCreate, JobSector


@pytest.fixture
def profile() -> CandidateProfile:
    return CandidateProfile(
        name="default",
        target_roles=["Data Engineer"],
        skills=[SkillEntry(name="Python"), SkillEntry(name="SQL")],
        cv_text="Data engineer profile.",
    )


@pytest.fixture
def offer() -> JobOfferCreate:
    return JobOfferCreate(
        external_id="1",
        source="justjoin",
        title="Data Engineer (Python, SQL)",
        company="Acme",
        sector=JobSector.DATA,
        description="Python and SQL pipelines.",
        skills=["Python", "SQL"],
        url="https://example.com/1",
    )


def test_evaluate_parses_structured_json_response(profile, offer):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[
            MagicMock(
                message=MagicMock(
                    content=(
                        '{"score": 0.88, "confidence": 0.91, '
                        '"is_relevant_role": true, '
                        '"matched_skills": ["Python", "SQL"], '
                        '"missing_skills": ["Spark"], '
                        '"explanation": "Dobre dopasowanie."}'
                    )
                )
            )
        ]
    )

    evaluator = LLMEvaluator(
        settings=Settings(LLM_API_KEY="test-key", LLM_MODEL="test-model"),
        client=mock_client,
    )
    result = evaluator.evaluate(offer, profile)

    assert result.score == pytest.approx(0.88)
    assert result.confidence == pytest.approx(0.91)
    assert result.is_relevant_role is True
    assert result.matched_skills == ["Python", "SQL"]
    assert result.missing_skills == ["Spark"]
    assert "Dobre dopasowanie" in result.explanation

    mock_client.chat.completions.create.assert_called_once()
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["response_format"] == {"type": "json_object"}


def test_evaluate_without_api_key_returns_dev_mode_result(
    profile, offer, caplog, monkeypatch
):
    # Isolate from the developer's .env / OS env (LLM_API_KEY would otherwise win).
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = Settings(_env_file=None, llm_api_key="")
    evaluator = LLMEvaluator(settings=settings)

    with caplog.at_level("WARNING"):
        result = evaluator.evaluate(offer, profile)

    assert result.confidence == 0.0
    assert result.is_relevant_role is False
    assert "LLM_API_KEY" in result.explanation
    assert any("LLM_API_KEY" in record.message for record in caplog.records)
