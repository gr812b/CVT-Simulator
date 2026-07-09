"""Database bootstrap helpers for local development and tests."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.settings import Settings
from app.database.base import Base
from app.database.seed import seed_database
from app.database.session import make_engine, make_session_factory


def create_database(engine: Engine) -> None:
    """Create all ORM-managed tables.

    Production deployments should prefer Alembic migrations. This helper is for
    local SQLite files and tests.
    """

    Base.metadata.create_all(engine)


def create_and_seed_database(settings: Settings, *, preset_path: Path | None = None) -> None:
    """Create tables and insert deterministic seed data."""

    engine = make_engine(settings.database_url, echo=settings.database_echo)
    create_database(engine)
    factory = make_session_factory(engine)
    with factory() as session:
        seed_database(session, preset_path=preset_path)
        session.commit()


def seed_existing_database(session: Session, *, preset_path: Path | None = None) -> None:
    """Seed rows into an existing transactional session."""

    seed_database(session, preset_path=preset_path)
