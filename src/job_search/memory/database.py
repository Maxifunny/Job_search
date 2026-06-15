"""Database engine and session management."""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config.settings import get_settings
from job_search.memory.models import Base


def _configure_sqlite(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_db_engine(database_url: str | None = None) -> Engine:
    """Create SQLAlchemy engine with sensible defaults for SQLite/PostgreSQL."""
    url = database_url or get_settings().database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, echo=False, future=True, connect_args=connect_args)
    if url.startswith("sqlite"):
        _configure_sqlite(engine)
    return engine


def init_database(engine: Engine | None = None) -> None:
    """Create all tables if they do not exist."""
    engine = engine or create_db_engine()
    Base.metadata.create_all(bind=engine)


def _alembic_config():
    from alembic.config import Config

    root = Path(__file__).resolve().parents[3]
    ini_path = root / "alembic.ini"
    if not ini_path.exists():
        ini_path = root / "migrations" / "alembic.ini"
    return Config(str(ini_path))


def _sector_column_is_string(engine: Engine) -> bool:
    inspector = inspect(engine)
    if not inspector.has_table("job_offers"):
        return False
    columns = {column["name"]: column for column in inspector.get_columns("job_offers")}
    sector_type = columns["sector"]["type"]
    type_name = type(sector_type).__name__.upper()
    return "VARCHAR" in type_name or "STRING" in type_name or "TEXT" in type_name


def migrate_database(engine: Engine | None = None) -> None:
    """Apply Alembic migrations up to head.

    If the database was created earlier via ``init-db`` without Alembic tracking,
    stamp the current schema revision before upgrading.
    """
    from alembic import command

    engine = engine or create_db_engine()
    cfg = _alembic_config()
    inspector = inspect(engine)

    if inspector.has_table("job_offers") and not inspector.has_table("alembic_version"):
        if _sector_column_is_string(engine):
            command.stamp(cfg, "002_sector_string")
        else:
            command.stamp(cfg, "001_initial_schema")

    command.upgrade(cfg, "head")




SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=create_db_engine())


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Provide a transactional database session."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
