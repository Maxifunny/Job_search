"""Candidate profile and preference schemas."""

from pydantic import BaseModel, Field


class SkillEntry(BaseModel):
    """Single skill with optional proficiency metadata."""

    name: str
    level: str | None = None
    years: float | None = None


class CandidateProfile(BaseModel):
    """User profile used for semantic and LLM-based matching."""

    name: str = "default"
    target_sectors: list[str] = Field(default_factory=lambda: ["data", "automation"])
    target_roles: list[str] = Field(
        default_factory=lambda: [
            "Data Analyst",
            "Data Engineer",
            "Data Scientist",
            "Automatyk",
            "Programista PLC",
            "Automation Engineer",
        ]
    )
    skills: list[SkillEntry] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    min_salary: float | None = None
    remote_only: bool = False
    excluded_keywords: list[str] = Field(
        default_factory=lambda: ["data entry", "junior bez doświadczenia"]
    )
    cv_text: str | None = None
    notes: str | None = None
