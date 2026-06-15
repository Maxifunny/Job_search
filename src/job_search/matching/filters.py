"""Keyword and title-based false-positive filters."""

from job_search.schemas.candidate import CandidateProfile
from job_search.schemas.job_offer import JobOfferCreate


class FalsePositiveFilter:
    """Reject obvious mismatches before expensive LLM calls."""

    DATA_FALSE_POSITIVES = (
        "data entry",
        "wprowadzanie danych",
        "wprowadzania danych",
    )
    AUTOMATION_FALSE_POSITIVES = ("operator produkcji", "operator maszyn", "monter")
    ANALYTICAL_SKILLS = (
        "python",
        "sql",
        "pandas",
        "spark",
        "tableau",
        "power bi",
        "analityk",
        "analytics",
        "data engineer",
        "data analyst",
        "data scientist",
        "etl",
        "dbt",
    )
    AUTOMATION_SKILLS = ("plc", "scada", "siemens", "tia portal", "allen-bradley")

    @classmethod
    def _structured_offer_text(cls, offer: JobOfferCreate) -> str:
        skills = " ".join(offer.skills)
        requirements = offer.requirements or ""
        return " ".join([offer.title, requirements, skills]).lower()

    @classmethod
    def _contains_any(cls, text: str, keywords: tuple[str, ...]) -> bool:
        return any(keyword in text for keyword in keywords)

    @classmethod
    def should_reject(
        cls, offer: JobOfferCreate, profile: CandidateProfile
    ) -> tuple[bool, str | None]:
        title_lower = offer.title.lower()
        structured_text = cls._structured_offer_text(offer)

        for keyword in profile.excluded_keywords:
            if keyword.lower() in title_lower:
                return True, f"Excluded keyword in title: {keyword}"

        if offer.sector.value == "data":
            for false_positive in cls.DATA_FALSE_POSITIVES:
                if false_positive in title_lower:
                    if not cls._contains_any(structured_text, cls.ANALYTICAL_SKILLS):
                        return True, (
                            f"Likely false positive for Data sector: {false_positive}"
                        )

        if offer.sector.value == "automation":
            for false_positive in cls.AUTOMATION_FALSE_POSITIVES:
                if false_positive in title_lower:
                    if not cls._contains_any(structured_text, cls.AUTOMATION_SKILLS):
                        return True, (
                            "Likely false positive for Automation sector: "
                            f"{false_positive}"
                        )

        return False, None
