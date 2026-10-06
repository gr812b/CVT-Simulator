"""One bounded computation. Imports before the deadline must be stdlib-only."""

import json
import logging
import os
import resource
import signal
import sys
import time
from pathlib import Path

LOG = logging.getLogger("cinder.child")


def apply_limits(envelope):
    """Linux can cap address space; macOS uses the parent's RSS watchdog."""

    def cap(resource_id, requested):
        _, inherited_hard = resource.getrlimit(resource_id)
        limit = (
            requested
            if inherited_hard == resource.RLIM_INFINITY
            else min(requested, inherited_hard)
        )
        resource.setrlimit(resource_id, (limit, limit))

    if sys.platform == "linux":
        cap(resource.RLIMIT_AS, envelope["memory_bytes"])
    cap(resource.RLIMIT_FSIZE, envelope["result_bytes"])
    cap(resource.RLIMIT_CORE, 0)


def monitor_worker_parent(worker_pid):
    """Arm Linux parent-death protection, including a worker running as PID 1."""

    import ctypes

    # Compare against the PID captured by the worker before Popen. Sampling only
    # here could accept a process that adopted us after the real worker exited.
    if os.getppid() != worker_pid:
        return False
    prctl = ctypes.CDLL(None, use_errno=True).prctl
    prctl.argtypes = [ctypes.c_int, *([ctypes.c_ulong] * 4)]
    prctl.restype = ctypes.c_int
    if prctl(1, signal.SIGKILL, 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
        raise OSError(ctypes.get_errno(), "Could not arm worker-parent monitoring")
    # Close the race between checking the parent and installing the signal.
    # PID 1 is a legitimate worker when it is the container's entry process.
    return os.getppid() == worker_pid


def main():
    input_path, output_path = map(Path, sys.argv[1:3])
    envelope = json.loads(input_path.read_text())
    remaining = envelope["deadline_monotonic"] - time.monotonic()
    if remaining <= 0:
        return 124
    # Default SIGALRM terminates even while native solver code holds the GIL.
    signal.signal(signal.SIGALRM, signal.SIG_DFL)
    signal.setitimer(signal.ITIMER_REAL, remaining)
    from app.application.run_failures import RunFailure

    run_id = envelope.get("run_id", "unknown")
    phase = "resource_limits"
    try:
        apply_limits(envelope)
        if sys.platform == "linux":
            worker_pid = envelope["worker_pid"]
            if not monitor_worker_parent(worker_pid):
                LOG.error(
                    "Worker parent changed during startup: expected PID %s, observed PID %s",
                    worker_pid,
                    os.getppid(),
                )
                return 125
        phase = "solver_import"
        from app.application.cinder_gateway import CinderGateway

        gateway = CinderGateway()
        phase = "simulation"
        if gateway.runtime_identity() != envelope["runtime_identity"]:
            payload = {
                "error": {
                    "code": "solver_version_changed",
                    "message": "The solver changed after submission. Rerun to use the currently installed solver.",
                }
            }
        else:

            def checkpoint(result):
                try:
                    encoded = json.dumps(result, allow_nan=False).encode("utf-8")
                except (TypeError, ValueError) as exc:
                    raise RunFailure(
                        "result_serialization_failed",
                        "The simulation produced data that could not be saved. "
                        "Any earlier saved checkpoint is still available.",
                        phase="reporting",
                    ) from exc
                if len(encoded) > envelope["result_bytes"]:
                    raise RunFailure(
                        "run_result_size_limit",
                        "The result exceeded the storage limit. Reduce reporting "
                        "detail or shorten the scenario.",
                        phase="reporting",
                    )
                target = output_path.with_name("checkpoint.json")
                temporary = target.with_suffix(".tmp")
                try:
                    temporary.write_bytes(encoded)
                    temporary.replace(target)
                except OSError as exc:
                    raise RunFailure(
                        "checkpoint_persistence_failed",
                        "The worker could not save the latest simulation data. "
                        "Any earlier saved checkpoint is still available.",
                        phase="reporting",
                    ) from exc

            payload = {
                "result": gateway.run_checkpointed(
                    envelope["input"],
                    checkpoint=checkpoint,
                    course_policy=envelope.get("course_policy"),
                    **envelope["options"],
                )
            }
    except MemoryError:
        LOG.exception("Run %s exhausted its memory budget during %s", run_id, phase)
        payload = {
            "error": {
                "code": "run_memory_limit",
                "message": "The simulation exceeded its memory budget. Shorten the scenario or reduce reporting detail.",
            }
        }
    except RunFailure as exc:
        cause = exc.__cause__ or exc
        LOG.exception(
            "Run %s stopped during %s [%s]: %s: %s",
            run_id,
            exc.phase,
            exc.code,
            type(cause).__name__,
            cause,
        )
        payload = {"error": exc.as_error()}
    except Exception as exc:
        LOG.exception("Run %s failed during %s: %s: %s", run_id, phase, type(exc).__name__, exc)
        messages = {
            "resource_limits": "The worker could not configure its execution limits. The service needs attention.",
            "solver_import": "The simulation runtime could not start. The service needs attention.",
            "simulation": "CINDER encountered an unexpected internal error. Use the run ID to report the problem.",
        }
        payload = {
            "error": {
                "code": f"{phase}_failed",
                "message": messages[phase],
                "details": {"phase": phase},
            }
        }
    try:
        encoded = json.dumps(payload, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        LOG.exception("Run %s result could not be serialized", run_id)
        payload = {
            "error": {
                "code": "result_serialization_failed",
                "message": "The simulation produced data that could not be saved. Any earlier saved checkpoint is still available.",
                "details": {"phase": "reporting"},
            }
        }
        encoded = json.dumps(payload).encode("utf-8")
    if len(encoded) > envelope["result_bytes"]:
        payload = {
            "error": {
                "code": "run_result_size_limit",
                "message": "The result exceeded the storage limit. Reduce reporting detail or shorten the scenario.",
            }
        }
        encoded = json.dumps(payload).encode("utf-8")
    temporary = output_path.with_suffix(".tmp")
    temporary.write_bytes(encoded)
    temporary.replace(output_path)
    return 1 if "error" in payload else 0


if __name__ == "__main__":
    raise SystemExit(main())
