"""Output, integration, and plotting helpers for the reduced-belt exploration."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np

STUDY_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = STUDY_ROOT / "artifacts"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_rows(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def finite_values(rows: list[dict[str, Any]], key: str) -> np.ndarray:
    values = []
    for row in rows:
        value = row.get(key)
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            values.append(float(value))
    return np.asarray(values, dtype=float)


def summarize_channel(rows: list[dict[str, Any]], key: str) -> dict[str, float] | None:
    values = finite_values(rows, key)
    if values.size == 0:
        return None
    absolute = np.abs(values)
    return {
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "p05": float(np.percentile(values, 5.0)),
        "p95": float(np.percentile(values, 95.0)),
        "max_abs": float(np.max(absolute)),
        "median_abs": float(np.median(absolute)),
        "p95_abs": float(np.percentile(absolute, 95.0)),
    }


def integrated_abs_share(rows: list[dict[str, Any]], term_key: str, scale_key: str) -> float | None:
    """Time-integrated |term| / time-integrated activity scale, segment aware."""
    numerator = 0.0
    denominator = 0.0
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(int(row.get("segment_index", 0)), []).append(row)
    for group in grouped.values():
        group.sort(key=lambda item: float(item["time_s"]))
        if len(group) < 2:
            continue
        t = np.asarray([float(item["time_s"]) for item in group])
        term = np.asarray([abs(float(item[term_key])) for item in group])
        scale = np.asarray([abs(float(item[scale_key])) for item in group])
        numerator += float(np.trapezoid(term, t))
        denominator += float(np.trapezoid(scale, t))
    if denominator <= 0.0:
        return None
    return numerator / denominator
