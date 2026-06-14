"""Job offer domain schemas."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class JobSector(str, Enum):
    """Primary job categories supported by the system."""

    DATA = "data"
    AUTOMATION = "automation"


class JobOfferCreate(BaseModel):
    """Payload for ingesting a new job offer from any scraper source."""

    external_id: str = Field(..., description="Unique ID within the source portal")
    source: str = Field(..., description="Portal name, e.g. justjoin, pracuj_pl")
    title: str
    company: str
    location: str | None = None
    sector: JobSector
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


class JobOfferRead(JobOfferCreate):
    """Job offer as stored and returned by the system."""

    id: int
    content_hash: str
    first_seen_at: datetime
    last_seen_at: datetime
    is_active: bool = True
