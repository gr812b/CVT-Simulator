"""HTTP-level checks for the database-backed library lifecycle."""

from __future__ import annotations

from app.scripts.smoke_library_database import main as run_library_smoke


def test_library_database_smoke_script_exercises_lifecycle_routes() -> None:
    run_library_smoke()
