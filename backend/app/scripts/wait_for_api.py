"""Wait for this image's API after migration, for a Watchtower post-update hook."""

from __future__ import annotations

import argparse
import logging
import math
import time
from collections.abc import Callable

from app.core.deployment import ApiReadinessGate

LOG = logging.getLogger("cinder.deployment")


def wait_until_ready(ready: Callable[[], bool], *, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if ready():
            return True
        time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=120.0, help="Maximum wait in seconds.")
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be a positive, finite number of seconds.")
    logging.basicConfig(level=logging.INFO)
    try:
        ready = ApiReadinessGate(args.url)
    except ValueError as exc:
        parser.error(str(exc))
    if not wait_until_ready(ready, timeout_seconds=args.timeout):
        LOG.error("API did not become ready within %.0f seconds", args.timeout)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
