"""Explicit, offline maintenance of disposable development databases."""

from __future__ import annotations

from pathlib import Path

import psutil
from sqlalchemy import Engine, inspect
from sqlalchemy.exc import SQLAlchemyError

from app.database.base import Base


class DatabaseNotReadyError(RuntimeError):
    """The selected database cannot support the current application schema."""


def reset_sqlite_database(database: Path) -> None:
    """Remove a stopped development database and its complete journal family.

    Callers must stop the API, workers and database tools before calling this.
    The open-file check catches accidentally surviving connections, including
    older app versions. It is best effort (OS permissions can hide handles) and
    cannot prevent a new process starting afterward.
    Never remove a journal independently when trying to preserve a database.
    """

    database = database.resolve()
    paths = tuple(Path(str(database) + suffix) for suffix in ("", "-journal", "-wal", "-shm"))
    for process in psutil.process_iter():
        try:
            if any(Path(file.path) in paths for file in process.open_files()):
                raise DatabaseNotReadyError(
                    f"Cannot reset {database}: process {process.pid} still has it open. "
                    "Stop the API, all workers and database tools, then retry."
                )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            # System processes can be inaccessible even to the current user.
            # The explicit requirement to stop all database clients still holds.
            continue
    for path in paths:
        path.unlink(missing_ok=True)


def require_current_schema(engine: Engine) -> None:
    """Fail before claiming jobs, with a useful database location and next step."""

    # Ensure all models are registered, even for callers outside the worker.
    from app.database import models  # noqa: F401

    location = engine.url.render_as_string(hide_password=True)
    if (
        engine.dialect.name == "sqlite"
        and engine.url.database not in {None, "", ":memory:"}
        and not engine.url.query.get("uri")
    ):
        location = str(Path(engine.url.database).resolve())
        if not Path(location).is_file():
            raise DatabaseNotReadyError(
                f"Database does not exist: {location}. "
                "Run python -m app.scripts.init_database from backend/ first. "
                "Use the same CVT_DATABASE_URL for initialization, API and worker."
            )
    try:
        with engine.connect() as connection:
            schema = inspect(connection)
            missing_tables = set(Base.metadata.tables) - set(schema.get_table_names())
            if missing_tables:
                detail = "Missing tables: " + ", ".join(sorted(missing_tables))
            else:
                missing_columns = [
                    f"{table.name}.{column}"
                    # Column checks need no dependency order. Current-version
                    # pointers intentionally form cycles with their owners.
                    for table in Base.metadata.tables.values()
                    for column in sorted(
                        set(table.columns.keys())
                        - {item["name"] for item in schema.get_columns(table.name)}
                    )
                ]
                if not missing_columns:
                    return
                detail = "Missing columns: " + ", ".join(missing_columns)
    except SQLAlchemyError as exc:
        detail = str(getattr(exc, "orig", exc))
    raise DatabaseNotReadyError(
        f"Database is not ready: {location}. {detail}. "
        "Check that the API and worker use the same CVT_DATABASE_URL. "
        "For a disposable development database, stop the API and all workers, "
        "then run python -m app.scripts.init_database --reset from backend/ "
        "(deletes saved data). For a maintained database, investigate or migrate it first."
    )
