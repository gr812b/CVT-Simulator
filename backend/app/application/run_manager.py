"""Process-backed Phase-2 simulation runs with an in-memory lifecycle store."""

from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import json
import multiprocessing
from queue import Empty
from threading import Thread
import time
from typing import Any, Literal
from uuid import uuid4

from app.application.cinder_gateway import CinderGateway
from app.core.errors import ApiProblem
from app.storage.run_store import InMemoryRunStore, RunRecord, RunStore, utc_now

from .worker import execute_simulation_worker


class RunManager:
    """Submit, monitor, and retrieve complete CINDER simulation documents.

    The only durable truth captured by a run is a deep-copied input document
    plus its result/error snapshot.  This keeps later database replacement
    straightforward and preserves reproducibility when presets are edited.
    """

    def __init__(
        self,
        *,
        gateway: CinderGateway,
        store: RunStore | None = None,
        timeout_seconds: float = 120.0,
        executor_mode: Literal["process", "inline"] = "process",
    ) -> None:
        if timeout_seconds <= 0.0:
            raise ValueError("timeout_seconds must be positive.")
        self._gateway = gateway
        self._store = store or InMemoryRunStore()
        self._timeout_seconds = timeout_seconds
        self._executor_mode = executor_mode
        self._mp_context = multiprocessing.get_context("spawn")

    def submit(
        self,
        document: dict[str, Any],
        *,
        include_reported_segments: bool = False,
        include_raw_trace: bool = False,
    ) -> RunRecord:
        """Validate and enqueue a reproducible simulation document."""

        snapshot = copy.deepcopy(document)
        validation = self._gateway.validate_simulation_case(snapshot)
        if not bool(validation.get("is_valid")):
            raise ApiProblem(
                422,
                "simulation_case_invalid",
                "The simulation-case document failed CINDER validation.",
                {"validation": validation},
            )

        record = RunRecord(
            id=str(uuid4()),
            status="queued",
            submitted_at=utc_now(),
            input_document_snapshot=snapshot,
            input_fingerprint=_fingerprint(snapshot),
            include_reported_segments=include_reported_segments,
            include_raw_trace=include_raw_trace,
        )
        self._store.create(record)
        if self._executor_mode == "inline":
            self._execute_inline(record.id)
        else:
            self._start_process(record.id)
        return self._store.get(record.id)

    def status(self, run_id: str) -> RunRecord:
        return self._store.get(run_id)

    def completed_result(self, run_id: str) -> RunRecord:
        record = self._store.get(run_id)
        if record.status != "completed" or record.result_snapshot is None:
            raise ApiProblem(
                409,
                "run_result_not_available",
                f"Run {run_id!r} is {record.status}; a result is not available yet.",
                {"status": record.status},
            )
        return record

    def _execute_inline(self, run_id: str) -> None:
        """Run synchronously for endpoint tests and simple local debugging."""

        record = self._mark_running(run_id)
        try:
            result = self._gateway.run_simulation(
                record.input_document_snapshot,
                include_reported_segments=record.include_reported_segments,
                include_raw_trace=record.include_raw_trace,
            )
        except Exception as error:
            self._mark_failed(run_id, error)
        else:
            self._mark_completed(run_id, result)

    def _start_process(self, run_id: str) -> None:
        record = self._store.get(run_id)
        result_queue = self._mp_context.Queue()
        process = self._mp_context.Process(
            target=execute_simulation_worker,
            kwargs={
                "document": record.input_document_snapshot,
                "include_reported_segments": record.include_reported_segments,
                "include_raw_trace": record.include_raw_trace,
                "result_queue": result_queue,
            },
            daemon=True,
        )
        process.start()
        self._mark_running(run_id)
        monitor = Thread(
            target=self._monitor_process,
            args=(run_id, process, result_queue),
            daemon=True,
            name=f"cinder-run-{run_id}",
        )
        monitor.start()

    def _monitor_process(self, run_id: str, process: Any, result_queue: Any) -> None:
        deadline = time.monotonic() + self._timeout_seconds
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0.0:
                    if process.is_alive():
                        process.kill()
                    self._mark_timed_out(run_id)
                    return
                try:
                    message = result_queue.get(timeout=min(0.2, remaining))
                except Empty:
                    if not process.is_alive():
                        self._mark_failed_message(
                            run_id,
                            "Simulation process terminated unexpectedly.",
                            "worker_terminated",
                        )
                        return
                    continue

                kind = message.get("kind")
                if kind == "completed":
                    self._mark_completed(run_id, message["result"])
                    return
                if kind == "failed":
                    self._mark_failed_message(
                        run_id,
                        str(message.get("message", "Simulation worker failed.")),
                        str(message.get("exception_type", "worker_error")),
                    )
                    return
                self._mark_failed_message(
                    run_id, "Worker returned an unknown message.", "worker_protocol"
                )
                return
        finally:
            if process.is_alive():
                process.kill()
            process.join(timeout=2.0)
            result_queue.close()
            result_queue.join_thread()

    def _mark_running(self, run_id: str) -> RunRecord:
        record = self._store.get(run_id)
        updated = replace(record, status="running", started_at=utc_now())
        return self._store.replace(updated)

    def _mark_completed(self, run_id: str, result: dict[str, Any]) -> RunRecord:
        record = self._store.get(run_id)
        updated = replace(
            record,
            status="completed",
            completed_at=utc_now(),
            result_snapshot=copy.deepcopy(result),
            error=None,
        )
        return self._store.replace(updated)

    def _mark_failed(self, run_id: str, error: Exception) -> RunRecord:
        return self._mark_failed_message(run_id, str(error), type(error).__name__)

    def _mark_failed_message(self, run_id: str, message: str, code: str) -> RunRecord:
        record = self._store.get(run_id)
        updated = replace(
            record,
            status="failed",
            completed_at=utc_now(),
            error={"code": code, "message": message},
        )
        return self._store.replace(updated)

    def _mark_timed_out(self, run_id: str) -> RunRecord:
        record = self._store.get(run_id)
        updated = replace(
            record,
            status="timed_out",
            completed_at=utc_now(),
            error={
                "code": "run_timeout",
                "message": f"Simulation exceeded the {self._timeout_seconds:g}s run limit.",
            },
        )
        return self._store.replace(updated)


def _fingerprint(document: dict[str, Any]) -> str:
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
