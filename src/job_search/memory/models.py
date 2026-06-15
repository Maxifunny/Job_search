"""SQLAlchemy ORM models for short- and long-term relational memory."""

from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class MatchDecisionEnum(str, PyEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class JobOffer(Base):
    """
    Canonical store of processed job offers.

    Deduplication key: (source, external_id) and content_hash.
    The system must never recommend the same offer twice.
    """

    __tablename__ = "job_offers"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_offer_source_external_id"),
        Index("ix_job_offers_content_hash", "content_hash"),
        Index("ix_job_offers_sector_active", "sector", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255))
    sector: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    requirements: Mapped[str | None] = mapped_column(Text)
    skills_json: Mapped[str | None] = mapped_column(Text)
    salary_min: Mapped[float | None] = mapped_column(Float)
    salary_max: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(8), default="PLN")
    employment_type: Mapped[str | None] = mapped_column(String(64))
    remote: Mapped[bool | None] = mapped_column(Boolean)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    match_results: Mapped[list["MatchResult"]] = relationship(
        back_populates="job_offer", cascade="all, delete-orphan"
    )
    recommendations: Mapped[list["Recommendation"]] = relationship(
        back_populates="job_offer", cascade="all, delete-orphan"
    )


class ScrapeRun(Base):
    """Audit log of scraper executions (short-term operational memory)."""

    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    sector: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    offers_found: Mapped[int] = mapped_column(Integer, default=0)
    offers_new: Mapped[int] = mapped_column(Integer, default=0)
    offers_updated: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="running")
    error_message: Mapped[str | None] = mapped_column(Text)


class MatchResult(Base):
    """Persisted LLM and semantic scoring for an offer vs. a candidate profile."""

    __tablename__ = "match_results"
    __table_args__ = (
        UniqueConstraint(
            "job_offer_id", "candidate_name", name="uq_match_offer_candidate"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_offer_id: Mapped[int] = mapped_column(
        ForeignKey("job_offers.id", ondelete="CASCADE"), nullable=False
    )
    candidate_name: Mapped[str] = mapped_column(String(128), default="default")
    semantic_score: Mapped[float | None] = mapped_column(Float)
    llm_score: Mapped[float | None] = mapped_column(Float)
    llm_confidence: Mapped[float | None] = mapped_column(Float)
    decision: Mapped[MatchDecisionEnum] = mapped_column(
        Enum(MatchDecisionEnum), default=MatchDecisionEnum.PENDING
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    matched_skills_json: Mapped[str | None] = mapped_column(Text)
    missing_skills_json: Mapped[str | None] = mapped_column(Text)
    llm_explanation: Mapped[str | None] = mapped_column(Text)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    job_offer: Mapped[JobOffer] = relationship(back_populates="match_results")


class Recommendation(Base):
    """
    Long-term memory of offers already shown to the user.

    Prevents duplicate recommendations even if the offer is re-scraped.
    """

    __tablename__ = "recommendations"
    __table_args__ = (
        UniqueConstraint(
            "job_offer_id", "candidate_name", name="uq_recommendation_offer_candidate"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_offer_id: Mapped[int] = mapped_column(
        ForeignKey("job_offers.id", ondelete="CASCADE"), nullable=False
    )
    candidate_name: Mapped[str] = mapped_column(String(128), default="default")
    recommended_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    channel: Mapped[str | None] = mapped_column(String(64))
    user_action: Mapped[str | None] = mapped_column(String(64))

    job_offer: Mapped[JobOffer] = relationship(back_populates="recommendations")


class UserPreference(Base):
    """Structured long-term preferences (complement to vector store)."""

    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_name: Mapped[str] = mapped_column(String(128), unique=True)
    profile_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EmbeddingCache(Base):
    """Cache of text embeddings to reduce OpenAI API calls."""

    __tablename__ = "embedding_cache"
    __table_args__ = (
        UniqueConstraint("text_hash", "model", name="uq_embedding_cache_text_model"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
