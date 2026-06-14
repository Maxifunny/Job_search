"""Tests for offer deduplication logic."""

from job_search.memory.repositories import compute_content_hash
from job_search.schemas.job_offer import JobOfferCreate, JobSector


def test_content_hash_is_stable():
    offer = JobOfferCreate(
        external_id="123",
        source="justjoin",
        title="Data Engineer",
        company="Acme",
        sector=JobSector.DATA,
        description="Python, SQL, Spark",
        url="https://example.com/job/123",
    )
    assert compute_content_hash(offer) == compute_content_hash(offer)


def test_content_hash_changes_when_description_changes():
    base = dict(
        external_id="123",
        source="justjoin",
        title="Data Engineer",
        company="Acme",
        sector=JobSector.DATA,
        url="https://example.com/job/123",
    )
    first = JobOfferCreate(description="Python, SQL", **base)
    second = JobOfferCreate(description="Python, SQL, Spark", **base)
    assert compute_content_hash(first) != compute_content_hash(second)
