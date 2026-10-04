"""Create and seed the local database.

Usage:
    python -m app.scripts.init_database
    CVT_DATABASE_URL=postgresql+psycopg://... python -m app.scripts.init_database
"""

from __future__ import annotations

from argparse import ArgumentParser
from dataclasses import replace
from pathlib import Path

from app.core.settings import Settings
from app.database.bootstrap import create_and_seed_database


def main() -> None:
    parser = ArgumentParser(description="Create and seed the CVT Simulator database.")
    parser.add_argument(
        "--database-url",
        default=None,
        help="SQLAlchemy database URL. Defaults to CVT_DATABASE_URL or local SQLite.",
    )
    parser.add_argument(
        "--development-fixtures",
        action="store_true",
        help="Also add two isolated passwordless local accounts and public setups (development only).",
    )
    parser.add_argument(
        "--preset-path",
        type=Path,
        default=None,
        help="Optional baseline preset JSON used to seed the demo objects.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the selected local SQLite development database before creating a fresh public workspace.",
    )
    args = parser.parse_args()

    settings = Settings.from_environment()
    if args.database_url is not None:
        settings = replace(settings, database_url=args.database_url)
    if args.development_fixtures and settings.environment != "development":
        parser.error("Development fixtures are unavailable in production.")
    if args.reset:
        from sqlalchemy.engine import make_url

        url = make_url(settings.database_url)
        if (
            settings.environment != "development"
            or url.get_backend_name() != "sqlite"
            or not url.database
            or url.database == ":memory:"
        ):
            parser.error(
                "--reset requires a file-backed SQLite database in development mode."
            )
        database = Path(url.database).resolve()
        for path in (
            database,
            Path(str(database) + "-wal"),
            Path(str(database) + "-shm"),
        ):
            path.unlink(missing_ok=True)
        print(f"Reset local development database: {database}")
    create_and_seed_database(settings, preset_path=args.preset_path)
    if args.development_fixtures:
        from app.database.development_fixtures import seed_development_fixtures
        from app.database.session import make_engine, make_session_factory

        factory = make_session_factory(make_engine(settings.database_url))
        with factory() as session:
            seed_development_fixtures(session)
            session.commit()
    print(f"Database created and seeded: {settings.database_url}")


if __name__ == "__main__":
    main()
