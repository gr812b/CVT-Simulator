"""Stable API failures without leaking CINDER or worker tracebacks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ApiProblem(Exception):
    """One intentional client-facing API failure."""

    status_code: int
    code: str
    message: str
    details: Any | None = None


class RunNotFoundError(ApiProblem):
    def __init__(self, run_id: str) -> None:
        super().__init__(404, "run_not_found", f"No run exists with id {run_id!r}.")


class PresetNotFoundError(ApiProblem):
    def __init__(self, preset_id: str) -> None:
        super().__init__(404, "preset_not_found", f"No preset exists with id {preset_id!r}.")
