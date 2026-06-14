"""Keyword and title-based false-positive filters."""

from job_search.schemas.candidate import CandidateProfile
from job_search.schemas.job_offer import JobOfferCreate


class FalsePositiveFilter:
    """Reject obvious mismatches before expensive LLM calls."""

    DATA_FALSE_POSITIVES = ("data entry", "wprowadzanie danych")
    AUTOMATION_FALSE_POSITIVES = ("operator maszyn", "monter")

    @classmethod
    def should_reject(
        cls, offer: JobOfferCreate, profile: CandidateProfile
    ) -> tuple[bool, str | None]:
        title_lower = offer.title.lower()
        for keyword in profile.excluded_keywords:
            if keyword.lower() in title_lower:
                return True, f"Excluded keyword in title: {keyword}"

        if offer.sector.value == "data":
            for fp in cls.DATA_FALSE_POSITIVES:
                if fp in title_lower and "scientist" not in title_lower:
                    return True, f"Likely false positive for Data sector: {fp}"

        return False, None
