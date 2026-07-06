"""Private primitive parsing helpers shared by CINDER public documents.

Document codecs intentionally keep their explicit mechanical mapping logic.
This module only centralizes ordinary JSON shape and scalar checks so new
versioned document types do not copy the same validation implementation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import isfinite
from typing import Any


class DesignDocumentError(ValueError):
    """Raised when a CINDER public document is malformed or unsupported."""


def require_mapping(value: object, path: str) -> Mapping[str, Any]:
    """Return a JSON object or raise a document-shape error."""

    if not isinstance(value, Mapping):
        raise DesignDocumentError(f"{path} must be an object.")
    return value


def require_sequence(value: object, path: str) -> Sequence[Any]:
    """Return a JSON array-like sequence or raise a document-shape error."""

    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise DesignDocumentError(f"{path} must be an array.")
    return value


def require(mapping: Mapping[str, Any], key: str) -> Any:
    """Return one required object member with a stable error message."""

    try:
        return mapping[key]
    except KeyError as error:
        raise DesignDocumentError(f"Missing required field {key!r}.") from error


def require_number(mapping: Mapping[str, Any], key: str) -> float:
    """Read one finite JSON number."""

    return require_finite_number(require(mapping, key), key)


def optional_number(mapping: Mapping[str, Any], key: str, *, default: float) -> float:
    """Read one optional finite JSON number."""

    return default if key not in mapping else require_number(mapping, key)


def require_finite_number(value: object, path: str) -> float:
    """Validate a finite numeric scalar supplied directly or from a member."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DesignDocumentError(f"{path} must be a finite number.")
    numeric = float(value)
    if not isfinite(numeric):
        raise DesignDocumentError(f"{path} must be finite.")
    return numeric


def require_number_or_infinity(mapping: Mapping[str, Any], key: str) -> float:
    """Read a finite number or the explicit JSON string ``\"infinity\"``."""

    value = require(mapping, key)
    if isinstance(value, str) and value == "infinity":
        return float("inf")
    return require_finite_number(value, key)


def require_integer(mapping: Mapping[str, Any], key: str) -> int:
    """Read one JSON integer, excluding booleans."""

    value = require(mapping, key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise DesignDocumentError(f"{key} must be an integer.")
    return value


def require_string(mapping: Mapping[str, Any], key: str) -> str:
    """Read one non-empty JSON string."""

    value = require(mapping, key)
    if not isinstance(value, str) or not value.strip():
        raise DesignDocumentError(f"{key} must be a non-empty string.")
    return value


def require_boolean(mapping: Mapping[str, Any], key: str) -> bool:
    """Read one JSON boolean."""

    value = require(mapping, key)
    if not isinstance(value, bool):
        raise DesignDocumentError(f"{key} must be a boolean.")
    return value
