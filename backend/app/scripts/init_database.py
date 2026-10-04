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
        "--preset-path",
        type=Path,
        default=None,
        help="Optional baseline preset JSON used to seed the demo objects.",
    )
    args = parser.parse_args()

    settings = Settings.from_environment()
    if args.database_url is not None:
        settings = replace(settings, database_url=args.database_url)
    create_and_seed_database(settings, preset_path=args.preset_path)
    print(f"Database created and seeded: {settings.database_url}")


if __name__ == "__main__":
    main()
