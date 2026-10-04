"""One bounded computation. Imports before the deadline must be stdlib-only."""

import json
import os
import resource
import signal
import sys
import time
from pathlib import Path


def main():
    input_path, output_path = map(Path, sys.argv[1:3])
    envelope = json.loads(input_path.read_text())
    remaining = envelope["deadline_monotonic"] - time.monotonic()
    if remaining <= 0:
        return 124
    # Default SIGALRM terminates even while native solver code holds the GIL.
    signal.signal(signal.SIGALRM, signal.SIG_DFL)
    signal.setitimer(signal.ITIMER_REAL, remaining)
    resource.setrlimit(
        resource.RLIMIT_AS, (envelope["memory_bytes"], envelope["memory_bytes"])
    )
    resource.setrlimit(
        resource.RLIMIT_FSIZE, (envelope["result_bytes"], envelope["result_bytes"])
    )
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if sys.platform == "linux":
        import ctypes

        parent = os.getppid()
        ctypes.CDLL(None).prctl(1, signal.SIGKILL)
        if os.getppid() != parent or parent == 1:
            return 125
    from app.application.cinder_gateway import CinderGateway

    gateway = CinderGateway()
    try:
        if gateway.runtime_identity() != envelope["runtime_identity"]:
            payload = {
                "error": {
                    "code": "solver_version_changed",
                    "message": "The solver changed after submission. Rerun to use the currently installed solver.",
                }
            }
        else:
            payload = {
                "result": gateway.run_simulation(
                    envelope["input"], **envelope["options"]
                )
            }
    except Exception:
        payload = {
            "error": {
                "code": "simulation_failed",
                "message": "The solver could not complete this input. Review the tune, road and numerical settings before retrying.",
            }
        }
    output_path.write_text(json.dumps(payload, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
