"""Pydantic schemas shared across modules."""

from job_search.schemas.candidate import CandidateProfile, SkillEntry
from job_search.schemas.job_offer import JobOfferCreate, JobOfferRead, JobSector

__all__ = [
    "CandidateProfile",
    "JobOfferCreate",
    "JobOfferRead",
    "JobSector",
    "SkillEntry",
]
