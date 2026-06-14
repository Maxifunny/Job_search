"""High-level pipeline: scrape → store → match → recommend."""

from dataclasses import dataclass, field

from job_search.schemas.candidate import CandidateProfile
from job_search.schemas.job_offer import JobOfferCreate, JobSector


@dataclass
class PipelineResult:
    sector: JobSector
    scraped: int = 0
    new_offers: int = 0
    matched: list[JobOfferCreate] = field(default_factory=list)
    rejected: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


class JobSearchPipeline:
    """
    Master orchestrator coordinating scrapers, memory, and matching.

    Full implementation will be wired once subagent modules are complete.
    """

    def run(self, sector: JobSector, profile: CandidateProfile) -> PipelineResult:
        raise NotImplementedError("Wire submodules after agent tasks are merged")
