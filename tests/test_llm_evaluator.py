"""Tests for LLMEvaluator."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from openai import APIStatusError

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


def test_evaluate_logs_quota_from_raw_response_headers(profile, offer, caplog):
    parsed_response = MagicMock(
        choices=[
            MagicMock(
                message=MagicMock(
                    content=(
                        '{"score": 0.75, "confidence": 0.8, '
                        '"is_relevant_role": true, '
                        '"matched_skills": ["Python"], '
                        '"missing_skills": [], '
                        '"explanation": "OK"}'
                    )
                )
            )
        ],
        usage=MagicMock(prompt_tokens=120, completion_tokens=80, total_tokens=200),
    )
    raw_response = MagicMock(
        headers={
            "x-ratelimit-limit-requests": "500",
            "x-ratelimit-remaining-requests": "321",
            "x-ratelimit-reset-requests": "12s",
            "x-ratelimit-limit-tokens": "200000",
            "x-ratelimit-remaining-tokens": "180000",
            "x-ratelimit-reset-tokens": "12s",
        }
    )
    raw_response.parse.return_value = parsed_response

    mock_client = MagicMock()
    mock_client.chat.completions.with_raw_response.create.return_value = raw_response
    evaluator = LLMEvaluator(
        settings=Settings(
            LLM_API_KEY="sk-test-1234",
            LLM_MODEL="test-model",
            LOG_API_QUOTA=True,
        ),
        client=mock_client,
    )

    with caplog.at_level("INFO"):
        result = evaluator.evaluate(offer, profile)

    assert result.score == pytest.approx(0.75)
    assert any("api_usage endpoint=chat.completions" in rec.message for rec in caplog.records)
    assert any("remaining(requests=321,tokens=180000)" in rec.message for rec in caplog.records)
    assert any("key=***1234" in rec.message for rec in caplog.records)
    mock_client.chat.completions.with_raw_response.create.assert_called_once()


def test_evaluate_falls_back_to_next_model_on_503(profile, offer, caplog, monkeypatch):
    monkeypatch.setattr("job_search.llm.model_fallback.time.sleep", lambda _s: None)

    primary_error = APIStatusError(
        "high demand",
        response=MagicMock(status_code=503),
        body={"error": {"code": 503, "status": "UNAVAILABLE"}},
    )

    def _create_side_effect(**kwargs):
        model = kwargs.get("model")
        if model == "primary-model":
            raise primary_error
        return MagicMock(
            choices=[
                MagicMock(
                    message=MagicMock(
                        content=(
                            '{"score": 0.7, "confidence": 0.75, '
                            '"is_relevant_role": true, '
                            '"matched_skills": ["Python"], '
                            '"missing_skills": [], '
                            '"explanation": "Fallback OK"}'
                        )
                    )
                )
            ],
            usage=MagicMock(prompt_tokens=10, completion_tokens=10, total_tokens=20),
        )

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = _create_side_effect
    del mock_client.chat.completions.with_raw_response

    evaluator = LLMEvaluator(
        settings=Settings(
            LLM_API_KEY="sk-test",
            LLM_MODEL="primary-model",
            LLM_FALLBACK_MODELS="backup-model",
            LLM_RETRY_ATTEMPTS=1,
            LOG_API_QUOTA=False,
        ),
        client=mock_client,
    )

    with caplog.at_level("WARNING"):
        result = evaluator.evaluate(offer, profile)

    assert result.confidence == pytest.approx(0.75)
    assert evaluator.last_model_used == "backup-model"
    assert any("switching to next model" in rec.message for rec in caplog.records)


def test_evaluate_logs_quota_fallback_when_headers_missing(profile, offer, caplog):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[
            MagicMock(
                message=MagicMock(
                    content=(
                        '{"score": 0.61, "confidence": 0.62, '
                        '"is_relevant_role": false, '
                        '"matched_skills": [], '
                        '"missing_skills": ["SQL"], '
                        '"explanation": "Brak dopasowania"}'
                    )
                )
            )
        ],
        usage=MagicMock(prompt_tokens=50, completion_tokens=20, total_tokens=70),
    )
    evaluator = LLMEvaluator(
        settings=Settings(
            LLM_API_KEY="sk-test-9999",
            LLM_MODEL="test-model",
            LOG_API_QUOTA=True,
        ),
        client=mock_client,
    )

    with caplog.at_level("INFO"):
        evaluator.evaluate(offer, profile)

    assert any(
        "remaining_quota=not_exposed_by_provider" in rec.message
        for rec in caplog.records
    )
