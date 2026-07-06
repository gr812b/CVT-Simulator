"""In-memory run records with an interface suitable for later persistence."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Literal, Protocol
import copy

from app.core.errors import RunNotFoundError

RunStatus = Literal["queued", "validating", "running", "completed", "failed", "timed_out"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class RunRecord:
    id: str
    status: RunStatus
    submitted_at: datetime
    input_document_snapshot: dict[str, Any]
    input_fingerprint: str
    include_reported_segments: bool
    include_raw_trace: bool
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result_snapshot: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


class RunStore(Protocol):
    def create(self, record: RunRecord) -> RunRecord:
        raise NotImplementedError

    def get(self, run_id: str) -> RunRecord:
        raise NotImplementedError

    def replace(self, record: RunRecord) -> RunRecord:
        raise NotImplementedError


class InMemoryRunStore:
    """Thread-safe process-local storage used until persistence is introduced."""

    def __init__(self) -> None:
        self._records: dict[str, RunRecord] = {}
        self._lock = RLock()

    def create(self, record: RunRecord) -> RunRecord:
        with self._lock:
            if record.id in self._records:
                raise ValueError(f"Run {record.id!r} already exists.")
            stored = _copy_record(record)
            self._records[stored.id] = stored
            return _copy_record(stored)

    def get(self, run_id: str) -> RunRecord:
        with self._lock:
            try:
                return _copy_record(self._records[run_id])
            except KeyError as error:
                raise RunNotFoundError(run_id) from error

    def replace(self, record: RunRecord) -> RunRecord:
        with self._lock:
            if record.id not in self._records:
                raise RunNotFoundError(record.id)
            stored = _copy_record(record)
            self._records[stored.id] = stored
            return _copy_record(stored)


def _copy_record(record: RunRecord) -> RunRecord:
    return replace(
        record,
        input_document_snapshot=copy.deepcopy(record.input_document_snapshot),
        result_snapshot=copy.deepcopy(record.result_snapshot),
        error=copy.deepcopy(record.error),
    )
