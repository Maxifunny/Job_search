"""Job offer domain schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, field_validator

from config.sector_loader import resolve_sector


class JobSector:
    """
    Validated job sector identifier backed by config/sectors/*.json.

    Built-in constants ``DATA`` and ``AUTOMATION`` are singleton instances.
    Any sector slug with a JSON config can be constructed via ``JobSector("slug")``.
    """

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        resolve_sector(value)
        self._value = value

    @property
    def value(self) -> str:
        return self._value

    def __str__(self) -> str:
        return self._value

    def __eq__(self, other: object) -> bool:
        if isinstance(other, JobSector):
            return self._value == other._value
        if isinstance(other, str):
            return self._value == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._value)

    def __repr__(self) -> str:
        return f"JobSector({self._value!r})"


for _attr, _slug in (("DATA", "data"), ("AUTOMATION", "automation")):
    _builtin = JobSector.__new__(JobSector)
    object.__setattr__(_builtin, "_value", _slug)
    setattr(JobSector, _attr, _builtin)


def coerce_sector_id(sector: JobSector | str) -> str:
    """Normalize a sector argument to its string slug."""
    return sector.value if isinstance(sector, JobSector) else sector


class JobOfferCreate(BaseModel):
    """Payload for ingesting a new job offer from any scraper source."""

    external_id: str = Field(..., description="Unique ID within the source portal")
    source: str = Field(..., description="Portal name, e.g. justjoin, pracuj_pl")
    title: str
    company: str
    location: str | None = None
    sector: str = Field(..., description="Sector slug from config/sectors/")
    description: str
    requirements: str | None = None
    skills: list[str] = Field(default_factory=list)
    salary_min: float | None = None
    salary_max: float | None = None
    currency: str | None = "PLN"
    employment_type: str | None = None
    remote: bool | None = None
    url: HttpUrl | str
    posted_at: datetime | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("sector", mode="before")
    @classmethod
    def validate_sector(cls, value: str | JobSector) -> str:
        sector_id = value.value if isinstance(value, JobSector) else value
        resolve_sector(sector_id)
        return sector_id


class JobOfferRead(JobOfferCreate):
    """Job offer as stored and returned by the system."""

    id: int
    content_hash: str
    first_seen_at: datetime
    last_seen_at: datetime
    is_active: bool = True
