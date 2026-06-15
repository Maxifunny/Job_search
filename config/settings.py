"""Application settings loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for all modules."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    database_url: str = Field(
        default="sqlite:///./data/job_search.db",
        alias="DATABASE_URL",
    )
    chroma_persist_dir: Path = Field(
        default=Path("./data/chroma"),
        alias="CHROMA_PERSIST_DIR",
    )
    chroma_collection_offers: str = Field(
        default="job_offers",
        alias="CHROMA_COLLECTION_OFFERS",
    )
    chroma_collection_preferences: str = Field(
        default="user_preferences",
        alias="CHROMA_COLLECTION_PREFERENCES",
    )

    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_base_url: str = Field(
        default="https://api.openai.com/v1",
        alias="LLM_BASE_URL",
    )
    llm_model: str = Field(default="gpt-4o-mini", alias="LLM_MODEL")
    embedding_model: str = Field(
        default="text-embedding-3-small",
        alias="EMBEDDING_MODEL",
    )

    min_semantic_score: float = Field(default=0.65, alias="MIN_SEMANTIC_SCORE")
    min_llm_confidence: float = Field(default=0.70, alias="MIN_LLM_CONFIDENCE")

    scraper_user_agent: str = Field(
        default="JobSearchBot/1.0",
        alias="SCRAPER_USER_AGENT",
    )
    scraper_request_delay_seconds: float = Field(
        default=2.0,
        alias="SCRAPER_REQUEST_DELAY_SECONDS",
    )
    justjoin_api_base: str = Field(
        default="https://justjoin.it/api/candidate-api",
        alias="JUSTJOIN_API_BASE",
    )
    pracuj_pl_base_url: str = Field(
        default="https://www.pracuj.pl",
        alias="PRACUJ_PL_BASE_URL",
    )
    nofluffjobs_api_base: str = Field(
        default="https://nofluffjobs.com/api",
        alias="NOFLUFFJOBS_API_BASE",
    )
    linkedin_guest_api_base: str = Field(
        default="https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search",
        alias="LINKEDIN_GUEST_API_BASE",
    )
    linkedin_jobs_location: str = Field(
        default="Poland",
        alias="LINKEDIN_JOBS_LOCATION",
    )
    scraper_max_pages: int = Field(default=3, alias="SCRAPER_MAX_PAGES")
    scraper_items_per_page: int = Field(default=50, alias="SCRAPER_ITEMS_PER_PAGE")
    scraper_max_offers_per_query: int = Field(
        default=30,
        alias="SCRAPER_MAX_OFFERS_PER_QUERY",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
