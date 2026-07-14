from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


OPTIONAL_CHANNEL_ALIASES = {
    "throttle_pct": ("throttle_pct", "throttle_percent", "throttle_position_pct"),
    "brake_active": ("brake_active", "brake", "brake_pressed"),
    "engine_rpm": ("engine_rpm", "rpm"),
    "primary_rpm": ("primary_rpm", "cvt_primary_rpm"),
    "secondary_rpm": ("secondary_rpm", "cvt_secondary_rpm"),
    "cvt_ratio": ("cvt_ratio", "ratio"),
    "wheel_speed_kmh": ("wheel_speed_kmh", "driven_wheel_speed_kmh"),
}


def attach_optional_telemetry(cleaned_gps: pd.DataFrame, source_csv: Path) -> tuple[pd.DataFrame, list[str]]:
    """Attach recognized timestamp-aligned channels without making them required."""

    raw = pd.read_csv(source_csv)
    if "timestamp" not in raw:
        return cleaned_gps, []
    lower_to_original = {str(column).casefold(): str(column) for column in raw.columns}
    selected: dict[str, str] = {}
    for canonical, aliases in OPTIONAL_CHANNEL_ALIASES.items():
        for alias in aliases:
            if alias.casefold() in lower_to_original:
                selected[canonical] = lower_to_original[alias.casefold()]
                break
    if not selected:
        return cleaned_gps, []

    telemetry = pd.DataFrame({"timestamp": pd.to_datetime(raw["timestamp"], errors="coerce")})
    for canonical, source in selected.items():
        if canonical == "brake_active":
            telemetry[canonical] = _coerce_boolean_numeric(raw[source])
        else:
            telemetry[canonical] = pd.to_numeric(raw[source], errors="coerce")
    telemetry = telemetry.dropna(subset=["timestamp"])
    telemetry = telemetry.groupby("timestamp", as_index=False)[list(selected)].median(numeric_only=True)
    merged = cleaned_gps.merge(telemetry, on="timestamp", how="left", validate="one_to_one")
    return merged, list(selected)


def _coerce_boolean_numeric(values: pd.Series) -> pd.Series:
    normalized = values.astype(str).str.strip().str.casefold()
    mapping = {
        "true": 1.0,
        "yes": 1.0,
        "on": 1.0,
        "pressed": 1.0,
        "false": 0.0,
        "no": 0.0,
        "off": 0.0,
        "released": 0.0,
    }
    mapped = normalized.map(mapping)
    numeric = pd.to_numeric(values, errors="coerce")
    return mapped.where(mapped.notna(), numeric).clip(0.0, 1.0)

