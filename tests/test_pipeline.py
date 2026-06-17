"""Tests for the JobSearchPipeline orchestrator.

These tests mock the scrape and match services so no live API calls or live
scrapers are required.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from job_search.matching.engine import MatchOutcome
from job_search.matching.service import MatchRunSummary
from job_search.memory.models import MatchDecisionEnum
from job_search.orchestrator import JobSearchPipeline, PipelineResult
from job_search.schemas.candidate import CandidateProfile
from job_search.schemas.job_offer import JobOfferCreate, JobSector
from job_search.scrapers.service import ScrapeSummary

PIPELINE_MODULE = "job_search.orchestrator.pipeline"


@pytest.fixture
def profile() -> CandidateProfile:
    return CandidateProfile(name="tester", target_sectors=["data"])


def _offer(external_id: str, title: str) -> JobOfferCreate:
    return JobOfferCreate(
        external_id=external_id,
        source="justjoin",
        title=title,
        company="Acme Corp",
        sector=JobSector.DATA,
        description="Python and SQL data pipelines.",
        skills=["Python", "SQL"],
        url=f"https://justjoin.it/offers/{external_id}",
    )


def _accepted_outcome(external_id: str, title: str) -> MatchOutcome:
    return MatchOutcome(
        offer=_offer(external_id, title),
        decision=MatchDecisionEnum.ACCEPTED,
    )


def test_run_aggregates_counters_and_recommendations(profile: CandidateProfile):
    scrape_summaries = [
        ScrapeSummary(
            source="justjoin",
            sector=JobSector.DATA,
            offers_found=10,
            offers_new=8,
            offers_updated=2,
        )
    ]
    match_summary = MatchRunSummary(
        evaluated=10,
        accepted=2,
        rejected=7,
        skipped=1,
        accepted_outcomes=[
            _accepted_outcome("1", "Data Engineer"),
            _accepted_outcome("2", "Data Analyst"),
        ],
    )

    with patch(
        f"{PIPELINE_MODULE}.scrape_and_persist", return_value=scrape_summaries
    ) as mock_scrape, patch(
        f"{PIPELINE_MODULE}.match_pending_offers", return_value=match_summary
    ) as mock_match:
        result = JobSearchPipeline().run(
            JobSector.DATA,
            profile,
            max_offers=5,
            match_limit=5,
        )

    assert isinstance(result, PipelineResult)
    assert result.sector == JobSector.DATA
    assert result.scraped == 10
    assert result.new_offers == 8
    assert result.updated_offers == 2
    assert result.evaluated == 10
    assert result.accepted == 2
    assert result.rejected == 7
    assert result.skipped == 1
    assert result.recommendations == [
        "Data Engineer @ Acme Corp - https://justjoin.it/offers/1",
        "Data Analyst @ Acme Corp - https://justjoin.it/offers/2",
    ]

    # sync_vectors defaults to True; scrape kwargs forwarded.
    mock_scrape.assert_called_once_with(
        JobSector.DATA,
        source=None,
        sync_vectors=True,
        max_offers=5,
    )
    mock_match.assert_called_once_with(profile, sector=JobSector.DATA, limit=5)


def test_run_continues_when_scrape_errors_but_offers_exist(profile: CandidateProfile):
    scrape_summaries = [
        ScrapeSummary(
            source="pracuj_pl",
            sector=JobSector.DATA,
            offers_found=3,
            offers_new=3,
            offers_updated=0,
            errors=["Cloudflare challenge blocked request"],
        )
    ]
    match_summary = MatchRunSummary(
        evaluated=3,
        accepted=1,
        rejected=2,
        accepted_outcomes=[_accepted_outcome("9", "Data Engineer")],
    )

    with patch(
        f"{PIPELINE_MODULE}.scrape_and_persist", return_value=scrape_summaries
    ), patch(
        f"{PIPELINE_MODULE}.match_pending_offers", return_value=match_summary
    ) as mock_match:
        result = JobSearchPipeline().run(JobSector.DATA, profile)

    assert result.scrape_errors == ["Cloudflare challenge blocked request"]
    assert result.evaluated == 3
    assert result.accepted == 1
    assert len(result.recommendations) == 1
    mock_match.assert_called_once()


def test_run_with_empty_scrape_still_matches_existing_db_offers(
    profile: CandidateProfile,
):
    match_summary = MatchRunSummary(
        evaluated=2,
        accepted=1,
        rejected=1,
        accepted_outcomes=[_accepted_outcome("42", "Data Scientist")],
    )

    with patch(
        f"{PIPELINE_MODULE}.scrape_and_persist", return_value=[]
    ), patch(
        f"{PIPELINE_MODULE}.match_pending_offers", return_value=match_summary
    ) as mock_match:
        result = JobSearchPipeline().run(JobSector.DATA, profile)

    assert result.scraped == 0
    assert result.new_offers == 0
    assert result.evaluated == 2
    assert result.accepted == 1
    assert result.recommendations == [
        "Data Scientist @ Acme Corp - https://justjoin.it/offers/42"
    ]
    mock_match.assert_called_once()


def test_run_records_scrape_exception_and_still_matches(profile: CandidateProfile):
    match_summary = MatchRunSummary(evaluated=0)

    with patch(
        f"{PIPELINE_MODULE}.scrape_and_persist",
        side_effect=RuntimeError("network down"),
    ), patch(
        f"{PIPELINE_MODULE}.match_pending_offers", return_value=match_summary
    ) as mock_match:
        result = JobSearchPipeline().run(JobSector.DATA, profile)

    assert result.scraped == 0
    assert any("network down" in error for error in result.scrape_errors)
    mock_match.assert_called_once()


def test_run_no_sync_vectors_forwarded(profile: CandidateProfile):
    with patch(
        f"{PIPELINE_MODULE}.scrape_and_persist", return_value=[]
    ) as mock_scrape, patch(
        f"{PIPELINE_MODULE}.match_pending_offers",
        return_value=MatchRunSummary(),
    ):
        JobSearchPipeline().run(
            JobSector.AUTOMATION,
            profile,
            source="justjoin",
            sync_vectors=False,
        )

    mock_scrape.assert_called_once_with(
        JobSector.AUTOMATION,
        source="justjoin",
        sync_vectors=False,
    )


def test_run_db_only_skips_scrape(profile: CandidateProfile):
    with patch(
        f"{PIPELINE_MODULE}.scrape_and_persist", return_value=[]
    ) as mock_scrape, patch(
        f"{PIPELINE_MODULE}.match_pending_offers",
        return_value=MatchRunSummary(),
    ) as mock_match:
        JobSearchPipeline().run(
            JobSector.DATA,
            profile,
            db_only=True,
        )

    mock_scrape.assert_not_called()
    mock_match.assert_called_once()
