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
    llm_fallback_models: list[str] = Field(default_factory=list, alias="LLM_FALLBACK_MODELS")
    llm_retry_attempts: int = Field(default=2, alias="LLM_RETRY_ATTEMPTS")
    embedding_model: str = Field(
        default="text-embedding-3-small",
        alias="EMBEDDING_MODEL",
    )
    embedding_fallback_models: list[str] = Field(
        default_factory=list,
        alias="EMBEDDING_FALLBACK_MODELS",
    )
    log_api_quota: bool = Field(default=True, alias="LOG_API_QUOTA")

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

    notifier_enabled: bool = Field(default=False, alias="NOTIFIER_ENABLED")
    notifier_max_offers: int = Field(default=10, alias="NOTIFIER_MAX_OFFERS")
    notifier_secret: str = Field(default="", alias="NOTIFIER_SECRET")
    notifier_public_base_url: str = Field(default="", alias="NOTIFIER_PUBLIC_BASE_URL")

    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_from: str = Field(default="", alias="SMTP_FROM")
    smtp_to: str = Field(default="", alias="SMTP_TO")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")

    @field_validator("llm_fallback_models", "embedding_fallback_models", mode="before")
    @classmethod
    def _parse_model_list(cls, value: object) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        if isinstance(value, list):
            return [str(part).strip() for part in value if str(part).strip()]
        return []


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
