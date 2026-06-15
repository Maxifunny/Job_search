"""Keyword and title-based false-positive filters."""

from config.sector_loader import SectorConfig, SectorConfigError, resolve_sector
from job_search.schemas.candidate import CandidateProfile
from job_search.schemas.job_offer import JobOfferCreate


class FalsePositiveFilter:
    """Reject obvious mismatches before expensive LLM calls."""

    @classmethod
    def _structured_offer_text(cls, offer: JobOfferCreate) -> str:
        skills = " ".join(offer.skills)
        requirements = offer.requirements or ""
        return " ".join([offer.title, requirements, skills]).lower()

    @classmethod
    def _contains_any(cls, text: str, keywords: tuple[str, ...] | list[str]) -> bool:
        return any(keyword in text for keyword in keywords)

    @classmethod
    def _sector_rules(cls, sector_id: str) -> SectorConfig | None:
        try:
            return resolve_sector(sector_id)
        except SectorConfigError:
            return None

    @classmethod
    def should_reject(
        cls, offer: JobOfferCreate, profile: CandidateProfile
    ) -> tuple[bool, str | None]:
        title_lower = offer.title.lower()
        structured_text = cls._structured_offer_text(offer)

        for keyword in profile.excluded_keywords:
            if keyword.lower() in title_lower:
                return True, f"Excluded keyword in title: {keyword}"

        sector_config = cls._sector_rules(offer.sector)
        if sector_config is None:
            return False, None

        for false_positive in sector_config.false_positive_title_keywords:
            if false_positive in title_lower:
                if not cls._contains_any(
                    structured_text, sector_config.required_skill_keywords
                ):
                    return True, (
                        f"Likely false positive for {sector_config.display_name}: "
                        f"{false_positive}"
                    )

        return False, None
