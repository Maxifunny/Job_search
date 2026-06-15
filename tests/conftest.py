"""Shared pytest fixtures."""

import pytest

from job_search.memory.database import create_db_engine
from job_search.memory.embeddings import EmbeddingService
from job_search.memory.models import Base


class MockEmbeddingService(EmbeddingService):
    """Deterministic embeddings for tests without live API calls."""

    def embed_text(self, text: str) -> list[float]:
        text_lower = text.lower()
        return [
            float("python" in text_lower),
            float("sql" in text_lower),
            float("pandas" in text_lower),
            float("data engineer" in text_lower or "data analyst" in text_lower),
            float("data entry" in text_lower or "wprowadzanie" in text_lower),
        ]


@pytest.fixture
def sqlite_engine():
    engine = create_db_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
