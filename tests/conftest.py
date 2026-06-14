"""Shared pytest fixtures."""

import pytest

from job_search.memory.database import create_db_engine
from job_search.memory.models import Base


@pytest.fixture
def sqlite_engine():
    engine = create_db_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
