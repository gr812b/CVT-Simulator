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


def main():
    input_path, output_path = map(Path, sys.argv[1:3])
    envelope = json.loads(input_path.read_text())
    remaining = envelope["deadline_monotonic"] - time.monotonic()
    if remaining <= 0:
        return 124
    # Default SIGALRM terminates even while native solver code holds the GIL.
    signal.signal(signal.SIGALRM, signal.SIG_DFL)
    signal.setitimer(signal.ITIMER_REAL, remaining)
    phase = "resource_limits"
    try:
        apply_limits(envelope)
        if sys.platform == "linux":
            import ctypes

            parent = os.getppid()
            if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL) != 0:
                raise OSError(
                    ctypes.get_errno(), "Could not arm worker-parent monitoring"
                )
            if os.getppid() != parent or parent == 1:
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
                encoded = json.dumps(result, allow_nan=False).encode("utf-8")
                if len(encoded) > envelope["result_bytes"]:
                    raise ValueError("Checkpoint exceeds the result storage limit.")
                target = output_path.with_name("checkpoint.json")
                temporary = target.with_suffix(".tmp")
                temporary.write_bytes(encoded)
                temporary.replace(target)

            payload = {
                "result": gateway.run_checkpointed(
                    envelope["input"],
                    checkpoint=checkpoint,
                    course_policy=envelope.get("course_policy"),
                    **envelope["options"],
                )
            }
    except MemoryError:
        LOG.exception("Memory budget exhausted during %s", phase)
        payload = {
            "error": {
                "code": "run_memory_limit",
                "message": "The simulation exceeded its memory budget. Shorten the scenario or reduce reporting detail.",
            }
        }
    except Exception:
        LOG.exception("Simulation child failed during %s", phase)
        messages = {
            "resource_limits": "The worker could not configure this system's resource limits. See the worker terminal for the startup error.",
            "solver_import": "The simulation runtime could not start. Install the backend requirements in the worker's environment and see its terminal for details.",
            "simulation": "The solver could not complete this input. Review the tune, road and numerical settings; the worker terminal contains the detailed error.",
        }
        payload = {
            "error": {
                "code": f"{phase}_failed",
                "message": messages[phase],
            }
        }
    encoded = json.dumps(payload, allow_nan=False).encode("utf-8")
    if len(encoded) > envelope["result_bytes"]:
        encoded = json.dumps(
            {
                "error": {
                    "code": "run_result_size_limit",
                    "message": "The result exceeded the storage limit. Reduce reporting detail or shorten the scenario.",
                }
            }
        ).encode("utf-8")
    temporary = output_path.with_suffix(".tmp")
    temporary.write_bytes(encoded)
    temporary.replace(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
