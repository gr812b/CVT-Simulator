"""Spawn-safe process entrypoint for one CINDER simulation run."""

from __future__ import annotations

from collections.abc import Mapping
from multiprocessing.queues import Queue
from typing import Any
import traceback

from .cinder_gateway import CinderGateway


def execute_simulation_worker(
    document: Mapping[str, Any],
    *,
    include_reported_segments: bool,
    include_raw_trace: bool,
    result_queue: Queue,
) -> None:
    """Run in a child process and send only JSON-safe data back to the parent."""

    try:
        result = CinderGateway().run_simulation(
            document,
            include_reported_segments=include_reported_segments,
            include_raw_trace=include_raw_trace,
        )
        result_queue.put({"kind": "completed", "result": result})
    except Exception as error:  # Parent intentionally receives no traceback.
        result_queue.put(
            {
                "kind": "failed",
                "message": str(error),
                "exception_type": type(error).__name__,
                "debug_traceback": traceback.format_exc(),
            }
        )
