"""Canonical JSON hashing helpers used by versions and runs."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json_hash(payload: Any) -> str:
    """Return a stable SHA-256 hash for JSON-compatible data."""

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
