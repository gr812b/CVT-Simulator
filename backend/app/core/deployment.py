"""Image identity and a fail-closed API readiness check for worker rollouts."""

from __future__ import annotations

import json
import logging
from http.client import HTTPException
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

LOG = logging.getLogger("cinder.deployment")
IMAGE_REVISION_HEADER = "X-Cinder-Image-Revision"
IMAGE_REVISION_FILE = Path(__file__).resolve().parents[2] / "image-revision.txt"


def image_revision() -> str | None:
    """Read the revision baked into the image by the publication workflow."""
    try:
        return IMAGE_REVISION_FILE.read_text(encoding="utf-8").strip() or None
    except FileNotFoundError:
        return None


class ApiReadinessGate:
    """Allow intake only while the matching API image is serving after migration.

    A gate is optional for local workers. Published deployments enable it so a
    worker cannot consume the queue while its API is stopped or still on another
    image. In-flight simulations continue to completion independently of this
    intake check. Orderly shutdown of workers before migrations is still required.
    """

    def __init__(self, api_url: str, *, timeout_seconds: float = 2.0):
        self.revision = image_revision()
        if not self.revision or self.revision.lower() in {
            "unknown",
            "development",
            "unversioned",
        }:
            raise ValueError(
                "API readiness requires CVT_IMAGE_REVISION baked into the backend image. "
                "Use a published image or build with --build-arg CVT_IMAGE_REVISION=<commit>."
            )
        self.health_url = api_url.rstrip("/") + "/api/v1/health"
        self.timeout_seconds = timeout_seconds
        self._last_state: tuple[bool, str] | None = None

    def __call__(self) -> bool:
        try:
            with urlopen(self.health_url, timeout=self.timeout_seconds) as response:
                body = response.read(4097)
                if response.status != 200 or len(body) > 4096:
                    return self._state(False, "the API health response is not ready")
                health = json.loads(body)
                if not isinstance(health, dict) or (
                    health.get("status") != "ok" or health.get("api_version") != "v1"
                ):
                    return self._state(False, "the API health response is not ready")
                if response.headers.get(IMAGE_REVISION_HEADER) != self.revision:
                    return self._state(False, "the API is not on this worker's image revision")
        except (URLError, HTTPException, OSError, ValueError):
            return self._state(False, "the API is unavailable or its health response is invalid")
        return self._state(True, "the API is ready")

    def _state(self, ready: bool, reason: str) -> bool:
        state = (ready, reason)
        if state != self._last_state:
            if ready:
                LOG.info("API is ready for image %s; worker intake is enabled", self.revision)
            else:
                LOG.info("Worker intake is paused: %s", reason)
            self._last_state = state
        return ready
