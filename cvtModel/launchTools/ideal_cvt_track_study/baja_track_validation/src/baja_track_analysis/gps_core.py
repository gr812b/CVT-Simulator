#!/usr/bin/env python3
"""Single-s GPS track analysis for Baja/CVT design studies.

This script replaces independent obstacle-radius searches with one ordered track
coordinate, s. It:

1. validates and lightly cleans the GPS log without globally smoothing it;
2. detects complete laps at an obstacle used as a lap gate;
3. builds a reference centreline from the cleanest fast lap;
4. projects every retained lap and every obstacle onto the same s coordinate;
5. creates a spatial speed profile and signed, ordered obstacle metrics; and
6. writes quality flags wherever the GPS-only data cannot support a conclusion.

The current legacy ``Obstacles.txt`` (a printed pandas table) is accepted so an
old analysis can be rerun. A pipe-delimited definition file is preferred; the
format is documented in the generated ``Obstacles_must_fill.txt`` file.

Important: GPS speed alone does not identify throttle demand, wheel slip,
terrain force, CVT ratio, engine RPM, or obstacle energy. The outputs therefore
describe observed vehicle speed response and data quality. They do not label a
speed reduction as energy loss or as a drivetrain limitation.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "mplconfig"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


EARTH_RADIUS_M = 6_371_008.8

REQUIRED_GPS_COLUMNS = ("timestamp", "lat", "lon", "speed_kmh")

# The old report was sorted alphabetically, so its row order cannot establish
# course order. This names-only list preserves the order of the source script.
# A new obstacle file should provide the sequence column explicitly.
LEGACY_COURSE_ORDER = [
    "Turn 1",
    "Turn 2",
    "Long Hill",
    "Bump 4",
    "Turn 5",
    "Bump 6",
    "Turn 7",
    "Crazy Ruts",
    "Banked Turn",
    "Turn 10",
    "Slaloms 11",
    "Turn 12",
    "Slaloms 13",
    "Turn 14",
    "Hills 15",
    "Pit",
    "Hill 18",
    "Bumps 20",
    "Ruts 21",
    "Big Hill",
    "Bumps 23",
    "Hill/Tires",
    "Long Hill 25",
    "Drop",
    "Turn 27",
    "Turn 28",
    "Hills 29",
    "Ruts 30",
    "Ruts 31",
    "Bumps 32",
    "Pipe 33",
    "Tires 34",
    "Turn 35",
    "Logs",
    "Turn 37",
    "Ruts 38",
    "Turn 39",
    "Pipe 40",
    "Hole",
    "Long Pit",
]


@dataclass
class AnalysisConfig:
    lap_gate_name: str = "Turn 1"
    lap_gate_radius_m: float = 15.0
    minimum_lap_time_s: float = 120.0
    stationary_speed_kmh: float = 3.0
    maximum_reasonable_speed_kmh: float = 80.0
    maximum_normal_time_step_s: float = 2.5
    maximum_map_error_m: float = 20.0
    centreline_spacing_m: float = 3.0
    profile_spacing_m: float = 5.0
    speed_outlier_threshold_kmh: float = 12.0
    default_recovery_fraction: float = 0.98
    default_recovery_limit_m: float = 60.0


@dataclass
class LocalFrame:
    lat0_deg: float
    lon0_deg: float

    def to_xy(self, lat: Iterable[float], lon: Iterable[float]) -> tuple[np.ndarray, np.ndarray]:
        lat_a = np.asarray(lat, dtype=float)
        lon_a = np.asarray(lon, dtype=float)
        lat0_rad = math.radians(self.lat0_deg)
        x = np.radians(lon_a - self.lon0_deg) * EARTH_RADIUS_M * math.cos(lat0_rad)
        y = np.radians(lat_a - self.lat0_deg) * EARTH_RADIUS_M
        return x, y

    def to_latlon(self, x: Iterable[float], y: Iterable[float]) -> tuple[np.ndarray, np.ndarray]:
        x_a = np.asarray(x, dtype=float)
        y_a = np.asarray(y, dtype=float)
        lat0_rad = math.radians(self.lat0_deg)
        lat = self.lat0_deg + np.degrees(y_a / EARTH_RADIUS_M)
        lon = self.lon0_deg + np.degrees(x_a / (EARTH_RADIUS_M * math.cos(lat0_rad)))
        return lat, lon


@dataclass
class Centreline:
    x: np.ndarray
    y: np.ndarray
    s_nodes_m: np.ndarray
    frame: LocalFrame

    def __post_init__(self) -> None:
        self.ax = self.x[:-1]
        self.ay = self.y[:-1]
        self.dx = np.diff(self.x)
        self.dy = np.diff(self.y)
        self.segment_length_m = np.hypot(self.dx, self.dy)
        self.segment_length_sq = np.maximum(self.segment_length_m**2, 1e-12)
        self.length_m = float(self.s_nodes_m[-1])

    def all_projections(self, px: float, py: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        t = ((px - self.ax) * self.dx + (py - self.ay) * self.dy) / self.segment_length_sq
        t = np.clip(t, 0.0, 1.0)
        qx = self.ax + t * self.dx
        qy = self.ay + t * self.dy
        distance_m = np.hypot(px - qx, py - qy)
        s_m = self.s_nodes_m[:-1] + t * self.segment_length_m
        return s_m, distance_m, qx, qy

    def project_with_progress(self, px: float, py: float, progress_guess_m: float) -> tuple[float, float, float, float]:
        s_raw, distance_m, qx, qy = self.all_projections(px, py)
        # Express every wrapped candidate on the copy of the lap closest to the
        # speed-integrated progress estimate. This prevents switches between
        # nearby but non-consecutive track branches.
        s_unwrapped = s_raw + np.round((progress_guess_m - s_raw) / self.length_m) * self.length_m
        progress_error_m = s_unwrapped - progress_guess_m
        score = distance_m**2 + (0.08 * progress_error_m) ** 2
        best = int(np.argmin(score))
        return float(s_unwrapped[best]), float(distance_m[best]), float(qx[best]), float(qy[best])

    def distinct_candidates(self, px: float, py: float, count: int = 12, separation_m: float = 18.0) -> list[dict]:
        s_m, distance_m, qx, qy = self.all_projections(px, py)
        candidates: list[dict] = []
        for idx in np.argsort(distance_m):
            s = float(s_m[idx])
            circular_distance = [
                min(abs(s - c["s_m"]), self.length_m - abs(s - c["s_m"])) for c in candidates
            ]
            if candidates and min(circular_distance) < separation_m:
                continue
            candidates.append(
                {
                    "s_m": s,
                    "error_m": float(distance_m[idx]),
                    "qx": float(qx[idx]),
                    "qy": float(qy[idx]),
                }
            )
            if len(candidates) >= count:
                break
        return candidates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", required=True, type=Path, help="GPS CSV containing timestamp, lat, lon, speed_kmh")
    parser.add_argument("--obstacles", required=True, type=Path, help="Legacy report or new pipe-delimited obstacle file")
    parser.add_argument("--output-dir", type=Path, default=Path("track_analysis_improved_output"))
    parser.add_argument("--lap-gate", default="Turn 1", help="Obstacle name used as the lap start/finish gate")
    parser.add_argument("--profile-spacing-m", type=float, default=5.0)
    parser.add_argument("--centreline-spacing-m", type=float, default=3.0)
    return parser.parse_args()


def numeric_or_nan(value: object) -> float:
    if value is None:
        return float("nan")
    text = str(value).strip()
    if not text:
        return float("nan")
    try:
        return float(text)
    except ValueError:
        return float("nan")


def infer_kind(name: str) -> str:
    lower = name.lower()
    if "turn" in lower:
        return "turn_apex"
    if any(token in lower for token in ("hill", "ruts", "slalom", "bumps", "pit", "logs", "tires")):
        return "interval"
    return "point"


def load_legacy_obstacles(path: Path) -> pd.DataFrame:
    rows = []
    # Latitude/longitude in the legacy report always contain decimal points.
    # Requiring those points prevents the numeric suffix in names such as
    # ``Turn 1`` or ``Ruts 21`` from being mistaken for the latitude.
    pattern = re.compile(
        r"^\s*\d+\s+(.*?)\s+([+-]?\d{1,2}\.\d+)\s+([+-]?\d{1,3}\.\d+)(?:\s|$)"
    )
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        name, lat, lon = match.groups()
        lat_f, lon_f = float(lat), float(lon)
        if not (-90 <= lat_f <= 90 and -180 <= lon_f <= 180):
            continue
        rows.append({"name": name.strip(), "latitude": lat_f, "longitude": lon_f})
    if not rows:
        raise ValueError(f"Could not parse any obstacle coordinates from legacy file: {path}")
    out = pd.DataFrame(rows).drop_duplicates(subset="name", keep="first")
    order = {name: i + 1 for i, name in enumerate(LEGACY_COURSE_ORDER)}
    out["sequence"] = out["name"].map(order)
    unknown = out["sequence"].isna()
    if unknown.any():
        start = len(order) + 1
        out.loc[unknown, "sequence"] = np.arange(start, start + int(unknown.sum()))
    out["kind"] = out["name"].map(infer_kind)
    out["input_format"] = "legacy_printed_report"
    return out.sort_values("sequence").reset_index(drop=True)


def load_pipe_obstacles(path: Path) -> pd.DataFrame:
    useful_lines = [
        line for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not useful_lines:
        raise ValueError(f"Obstacle definition file is empty: {path}")
    reader = csv.DictReader(useful_lines, delimiter="|")
    rows = [{str(k).strip(): str(v).strip() for k, v in row.items()} for row in reader]
    out = pd.DataFrame(rows)
    aliases = {
        "obstacle": "name",
        "lat": "latitude",
        "lon": "longitude",
        "anchor_lat": "latitude",
        "anchor_lon": "longitude",
        "start_lat": "start_latitude",
        "start_lon": "start_longitude",
        "end_lat": "end_latitude",
        "end_lon": "end_longitude",
    }
    out.columns = [aliases.get(c.strip().lower(), c.strip().lower()) for c in out.columns]
    for required in ("name", "latitude", "longitude"):
        if required not in out.columns:
            raise ValueError(f"Preferred obstacle file is missing required column: {required}")
    if "sequence" not in out:
        out["sequence"] = np.arange(1, len(out) + 1)
    if "kind" not in out:
        out["kind"] = out["name"].map(infer_kind)
    out["input_format"] = "pipe_delimited_definition"
    return out


def load_obstacles(path: Path) -> pd.DataFrame:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    first_useful = next((line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")), "")
    if "|" in first_useful:
        out = load_pipe_obstacles(path)
    else:
        out = load_legacy_obstacles(path)

    numeric_columns = [
        "sequence",
        "latitude",
        "longitude",
        "start_latitude",
        "start_longitude",
        "end_latitude",
        "end_longitude",
        "feature_before_m",
        "feature_after_m",
        "entry_before_start_m",
        "entry_gap_m",
        "exit_gap_m",
        "exit_length_m",
        "recovery_limit_m",
    ]
    for col in numeric_columns:
        if col not in out:
            out[col] = np.nan
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out["sequence"] = out["sequence"].fillna(pd.Series(np.arange(1, len(out) + 1), index=out.index)).astype(int)
    out["name"] = out["name"].astype(str).str.strip()
    out["kind"] = out["kind"].fillna("").astype(str).str.strip().str.lower()
    out.loc[~out["kind"].isin(["point", "interval", "turn_apex"]), "kind"] = out.loc[
        ~out["kind"].isin(["point", "interval", "turn_apex"]), "name"
    ].map(infer_kind)
    if out["name"].duplicated().any():
        duplicates = out.loc[out["name"].duplicated(keep=False), "name"].tolist()
        raise ValueError(f"Duplicate obstacle names: {duplicates}")
    invalid_coords = ~out["latitude"].between(-90, 90) | ~out["longitude"].between(-180, 180)
    if invalid_coords.any():
        raise ValueError(f"Invalid anchor coordinates for: {out.loc[invalid_coords, 'name'].tolist()}")
    return out.sort_values(["sequence", "name"]).reset_index(drop=True)


def local_distance_m(frame: LocalFrame, lat: np.ndarray, lon: np.ndarray, lat_ref: float, lon_ref: float) -> np.ndarray:
    x, y = frame.to_xy(lat, lon)
    xr, yr = frame.to_xy([lat_ref], [lon_ref])
    return np.hypot(x - xr[0], y - yr[0])


def load_and_clean_gps(path: Path, cfg: AnalysisConfig) -> tuple[pd.DataFrame, dict]:
    raw = pd.read_csv(path)
    missing = [column for column in REQUIRED_GPS_COLUMNS if column not in raw.columns]
    if missing:
        raise ValueError(f"GPS CSV is missing columns: {missing}")

    report: dict[str, object] = {"input_rows": len(raw)}
    df = raw[list(REQUIRED_GPS_COLUMNS)].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    for col in ("lat", "lon", "speed_kmh"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    valid = (
        df["timestamp"].notna()
        & df["lat"].between(-90, 90)
        & df["lon"].between(-180, 180)
        & df["speed_kmh"].between(0, cfg.maximum_reasonable_speed_kmh)
    )
    report["invalid_rows_removed"] = int((~valid).sum())
    df = df.loc[valid].sort_values("timestamp", kind="stable").reset_index(drop=True)

    report["duplicate_timestamps_merged"] = int(df["timestamp"].duplicated(keep=False).sum())
    if df["timestamp"].duplicated().any():
        df = (
            df.groupby("timestamp", as_index=False, sort=True)[["lat", "lon", "speed_kmh"]]
            .median(numeric_only=True)
            .reset_index(drop=True)
        )

    dt = df["timestamp"].diff().dt.total_seconds()
    df["dt_s"] = dt
    report["nonpositive_time_steps"] = int((dt <= 0).sum())
    report["time_gaps_over_limit"] = int((dt > cfg.maximum_normal_time_step_s).sum())
    report["median_sample_period_s"] = float(dt[dt > 0].median())

    # A Hampel-like one-sample replacement removes isolated sensor spikes while
    # retaining real accelerations. Unlike the previous rolling median, normal
    # samples are not blurred across an obstacle.
    local_median = df["speed_kmh"].rolling(5, center=True, min_periods=3).median()
    spike = (df["speed_kmh"] - local_median).abs() > cfg.speed_outlier_threshold_kmh
    df["speed_analysis_kmh"] = df["speed_kmh"].where(~spike, local_median)
    report["isolated_speed_spikes_replaced"] = int(spike.sum())

    frame = LocalFrame(float(df["lat"].median()), float(df["lon"].median()))
    x, y = frame.to_xy(df["lat"], df["lon"])
    df["x_m"] = x
    df["y_m"] = y
    df["gps_step_m"] = np.r_[np.nan, np.hypot(np.diff(x), np.diff(y))]
    df["speed_step_m"] = df["speed_analysis_kmh"] / 3.6 * df["dt_s"].fillna(0).clip(lower=0)
    df["stationary"] = df["speed_analysis_kmh"] < cfg.stationary_speed_kmh
    df["time_gap"] = df["dt_s"] > cfg.maximum_normal_time_step_s

    report["output_rows"] = len(df)
    report["duration_s"] = float((df["timestamp"].iloc[-1] - df["timestamp"].iloc[0]).total_seconds())
    report["reported_speed_distance_m"] = float(df["speed_step_m"].sum())
    report["raw_gps_path_distance_m"] = float(np.nansum(df["gps_step_m"]))
    report["stationary_time_fraction"] = float(df["stationary"].mean())
    return df, report


def detect_gate_crossings(
    df: pd.DataFrame,
    frame: LocalFrame,
    gate_lat: float,
    gate_lon: float,
    cfg: AnalysisConfig,
) -> list[int]:
    distance = local_distance_m(
        frame,
        df["lat"].to_numpy(),
        df["lon"].to_numpy(),
        gate_lat,
        gate_lon,
    )
    inside = np.flatnonzero(distance <= cfg.lap_gate_radius_m)
    groups: list[list[int]] = []
    for idx in inside:
        if not groups:
            groups.append([int(idx)])
            continue
        dt = (df.loc[idx, "timestamp"] - df.loc[groups[-1][-1], "timestamp"]).total_seconds()
        if dt > 3.0:
            groups.append([int(idx)])
        else:
            groups[-1].append(int(idx))
    candidates = [min(group, key=lambda i: distance[i]) for group in groups]

    merged: list[int] = []
    for idx in candidates:
        if not merged:
            merged.append(idx)
            continue
        elapsed = (df.loc[idx, "timestamp"] - df.loc[merged[-1], "timestamp"]).total_seconds()
        if elapsed >= cfg.minimum_lap_time_s:
            merged.append(idx)
        elif distance[idx] < distance[merged[-1]]:
            merged[-1] = idx
    return merged


def build_lap_table(df: pd.DataFrame, crossings: list[int], cfg: AnalysisConfig) -> pd.DataFrame:
    rows = []
    for lap_id, (start, end) in enumerate(zip(crossings[:-1], crossings[1:]), start=1):
        segment = df.iloc[start : end + 1]
        duration_s = float((segment["timestamp"].iloc[-1] - segment["timestamp"].iloc[0]).total_seconds())
        distance_m = float(segment["speed_step_m"].sum())
        stationary_fraction = float(segment["stationary"].mean())
        rows.append(
            {
                "lap_id": lap_id,
                "start_index": start,
                "end_index": end,
                "start_time": segment["timestamp"].iloc[0],
                "end_time": segment["timestamp"].iloc[-1],
                "duration_s": duration_s,
                "speed_integrated_distance_m": distance_m,
                "stationary_fraction": stationary_fraction,
                "median_speed_kmh": float(segment["speed_analysis_kmh"].median()),
                "max_speed_kmh": float(segment["speed_analysis_kmh"].max()),
                "time_gap_count": int(segment["time_gap"].sum()),
            }
        )
    laps = pd.DataFrame(rows)
    if laps.empty:
        raise ValueError("No complete laps were found between lap-gate visits")
    distance_median = float(laps["speed_integrated_distance_m"].median())
    laps["distance_ratio_to_median"] = laps["speed_integrated_distance_m"] / distance_median
    laps["analysis_valid"] = (
        laps["distance_ratio_to_median"].between(0.85, 1.15)
        & (laps["stationary_fraction"] <= 0.15)
        & (laps["time_gap_count"] == 0)
    )
    if not laps["analysis_valid"].any():
        laps["analysis_valid"] = laps["distance_ratio_to_median"].between(0.75, 1.25) & (laps["time_gap_count"] == 0)
    valid = laps[laps["analysis_valid"]]
    reference_idx = valid["duration_s"].idxmin()
    laps["reference_lap"] = False
    laps.loc[reference_idx, "reference_lap"] = True
    return laps


def build_centreline(
    df: pd.DataFrame,
    laps: pd.DataFrame,
    frame: LocalFrame,
    cfg: AnalysisConfig,
) -> Centreline:
    ref = laps.loc[laps["reference_lap"]].iloc[0]
    segment = df.iloc[int(ref["start_index"]) : int(ref["end_index"]) + 1].copy()
    # A short median followed by a three-point mean removes metre-scale GPS
    # zig-zag that otherwise inflates s. Smoothing is along time within one lap,
    # so nearby but non-consecutive branches are never averaged together.
    x = (
        segment["x_m"]
        .rolling(5, center=True, min_periods=1)
        .median()
        .rolling(3, center=True, min_periods=1)
        .mean()
        .to_numpy()
    )
    y = (
        segment["y_m"]
        .rolling(5, center=True, min_periods=1)
        .median()
        .rolling(3, center=True, min_periods=1)
        .mean()
        .to_numpy()
    )
    endpoint = np.array([(x[0] + x[-1]) / 2, (y[0] + y[-1]) / 2])
    x[0], y[0] = endpoint
    x[-1], y[-1] = endpoint

    keep = np.ones(len(x), dtype=bool)
    if len(x) > 2:
        keep[1:] = np.hypot(np.diff(x), np.diff(y)) >= 0.5
        keep[-1] = True
    x = x[keep]
    y = y[keep]
    raw_step = np.hypot(np.diff(x), np.diff(y))
    valid_segment = raw_step > 1e-6
    if not valid_segment.all():
        keep_nodes = np.r_[True, valid_segment]
        x, y = x[keep_nodes], y[keep_nodes]
        raw_step = np.hypot(np.diff(x), np.diff(y))
    raw_s = np.r_[0.0, np.cumsum(raw_step)]
    total_length = float(raw_s[-1])
    uniform_s = np.arange(0.0, total_length, cfg.centreline_spacing_m)
    if len(uniform_s) == 0 or uniform_s[-1] < total_length:
        uniform_s = np.r_[uniform_s, total_length]
    uniform_x = np.interp(uniform_s, raw_s, x)
    uniform_y = np.interp(uniform_s, raw_s, y)
    uniform_x[-1], uniform_y[-1] = uniform_x[0], uniform_y[0]
    segment_lengths = np.hypot(np.diff(uniform_x), np.diff(uniform_y))
    exact_s = np.r_[0.0, np.cumsum(segment_lengths)]
    return Centreline(uniform_x, uniform_y, exact_s, frame)


def map_match_laps(
    df: pd.DataFrame,
    laps: pd.DataFrame,
    centreline: Centreline,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    matched_rows = []
    laps = laps.copy()
    for row_idx, lap in laps.iterrows():
        start, end = int(lap["start_index"]), int(lap["end_index"])
        segment = df.iloc[start : end + 1].copy()
        step = segment["speed_step_m"].to_numpy(dtype=float)
        progress = np.cumsum(np.nan_to_num(step, nan=0.0))
        progress -= progress[0]
        if progress[-1] <= 0:
            progress_guess = np.linspace(0.0, centreline.length_m, len(segment))
        else:
            progress_guess = progress / progress[-1] * centreline.length_m

        matched_s = []
        errors = []
        qx_values = []
        qy_values = []
        for px, py, guess in zip(segment["x_m"], segment["y_m"], progress_guess):
            s, error, qx, qy = centreline.project_with_progress(float(px), float(py), float(guess))
            matched_s.append(s)
            errors.append(error)
            qx_values.append(qx)
            qy_values.append(qy)
        segment["lap_id"] = int(lap["lap_id"])
        segment["s_m"] = np.clip(matched_s, 0.0, centreline.length_m)
        segment["map_error_m"] = errors
        segment["matched_x_m"] = qx_values
        segment["matched_y_m"] = qy_values
        segment["elapsed_lap_s"] = (segment["timestamp"] - segment["timestamp"].iloc[0]).dt.total_seconds()
        matched_rows.append(segment)

        laps.loc[row_idx, "median_map_error_m"] = float(np.median(errors))
        laps.loc[row_idx, "p95_map_error_m"] = float(np.quantile(errors, 0.95))
        laps.loc[row_idx, "maximum_map_error_m"] = float(np.max(errors))
        ds = np.diff(np.asarray(matched_s))
        laps.loc[row_idx, "large_backward_match_count"] = int((ds < -20.0).sum())
        if int((ds < -20.0).sum()) > 0 or float(np.quantile(errors, 0.95)) > 20.0:
            laps.loc[row_idx, "analysis_valid"] = False
    return pd.concat(matched_rows, ignore_index=True), laps


def default_feature_half_width(kind: str) -> float:
    if kind == "point":
        return 5.0
    if kind == "turn_apex":
        return 12.0
    return 15.0


def choose_ordered_obstacle_candidates(
    obstacles: pd.DataFrame,
    centreline: Centreline,
    candidate_lists: list[list[dict]],
) -> list[int]:
    costs: list[np.ndarray] = []
    back: list[np.ndarray] = []
    first_candidates = candidate_lists[0]
    first_s = np.array([min(c["s_m"], centreline.length_m - c["s_m"]) for c in first_candidates])
    first_error = np.array([c["error_m"] for c in first_candidates])
    costs.append(first_error**2 + (first_s / 5.0) ** 2)
    back.append(np.full(len(first_candidates), -1, dtype=int))

    for i in range(1, len(candidate_lists)):
        previous = candidate_lists[i - 1]
        current = candidate_lists[i]
        prev_s = np.array([c["s_m"] for c in previous])
        curr_s = np.array([c["s_m"] for c in current])
        current_cost = np.full(len(current), np.inf)
        current_back = np.full(len(current), -1, dtype=int)
        for j, s_now in enumerate(curr_s):
            ds = s_now - prev_s
            order_penalty = np.where(ds >= -3.0, 0.0, 1_000_000.0 + (-ds) * 10_000.0)
            trial = costs[-1] + order_penalty
            k = int(np.argmin(trial))
            current_cost[j] = trial[k] + current[j]["error_m"] ** 2
            current_back[j] = k
        costs.append(current_cost)
        back.append(current_back)

    chosen = [int(np.argmin(costs[-1]))]
    for i in range(len(candidate_lists) - 1, 0, -1):
        chosen.append(int(back[i][chosen[-1]]))
    return list(reversed(chosen))


def project_obstacles(
    obstacles: pd.DataFrame,
    centreline: Centreline,
) -> pd.DataFrame:
    x, y = centreline.frame.to_xy(obstacles["latitude"], obstacles["longitude"])
    candidate_lists = [centreline.distinct_candidates(float(px), float(py)) for px, py in zip(x, y)]
    # The first definition is also the lap gate, so make its nearest projection
    # at either side of the closed polyline exactly s=0. Without this synthetic
    # gate candidate, the ordered solver can reject the geometrically correct
    # final-segment projection merely because it is numerically close to L.
    if candidate_lists:
        gate_near = [
            candidate for candidate in candidate_lists[0]
            if min(candidate["s_m"], centreline.length_m - candidate["s_m"]) <= 50.0
        ]
        if gate_near:
            gate_best = min(gate_near, key=lambda candidate: candidate["error_m"])
            synthetic_gate = dict(gate_best)
            synthetic_gate["s_m"] = 0.0
            nonduplicate = [
                candidate for candidate in candidate_lists[0]
                if min(
                    abs(candidate["s_m"] - gate_best["s_m"]),
                    centreline.length_m - abs(candidate["s_m"] - gate_best["s_m"]),
                ) >= 18.0
            ]
            candidate_lists[0] = [synthetic_gate, *nonduplicate]
    chosen_indices = choose_ordered_obstacle_candidates(obstacles, centreline, candidate_lists)
    rows = []
    for (_, obstacle), px, py, candidates, chosen_idx in zip(
        obstacles.iterrows(), x, y, candidate_lists, chosen_indices
    ):
        chosen = candidates[chosen_idx]
        alternatives = [c for i, c in enumerate(candidates) if i != chosen_idx]
        nearest_alternative = min(alternatives, key=lambda c: c["error_m"]) if alternatives else None
        projected_lat, projected_lon = centreline.frame.to_latlon([chosen["qx"]], [chosen["qy"]])
        half_default = default_feature_half_width(obstacle["kind"])
        before = obstacle["feature_before_m"] if pd.notna(obstacle["feature_before_m"]) else half_default
        after = obstacle["feature_after_m"] if pd.notna(obstacle["feature_after_m"]) else half_default
        extent_source = "configured_offsets" if pd.notna(obstacle["feature_before_m"]) or pd.notna(obstacle["feature_after_m"]) else "assumed_default"

        # Explicit start/end GPS coordinates take precedence over offsets. They
        # are projected independently and expressed near the anchor.
        if all(pd.notna(obstacle[col]) for col in ("start_latitude", "start_longitude")):
            sx, sy = centreline.frame.to_xy([obstacle["start_latitude"]], [obstacle["start_longitude"]])
            start_candidate = min(centreline.distinct_candidates(float(sx[0]), float(sy[0])), key=lambda c: abs(c["s_m"] - chosen["s_m"]))
            feature_start_rel = start_candidate["s_m"] - chosen["s_m"]
            extent_source = "explicit_start_end_gps" if all(
                pd.notna(obstacle[col]) for col in ("end_latitude", "end_longitude")
            ) else "explicit_start_only"
        else:
            feature_start_rel = -float(before)

        if all(pd.notna(obstacle[col]) for col in ("end_latitude", "end_longitude")):
            ex, ey = centreline.frame.to_xy([obstacle["end_latitude"]], [obstacle["end_longitude"]])
            end_candidate = min(centreline.distinct_candidates(float(ex[0]), float(ey[0])), key=lambda c: abs(c["s_m"] - chosen["s_m"]))
            feature_end_rel = end_candidate["s_m"] - chosen["s_m"]
        else:
            feature_end_rel = float(after)
        if feature_end_rel <= feature_start_rel:
            feature_end_rel += centreline.length_m

        entry_before = obstacle["entry_before_start_m"] if pd.notna(obstacle["entry_before_start_m"]) else 30.0
        entry_gap = obstacle["entry_gap_m"] if pd.notna(obstacle["entry_gap_m"]) else 10.0
        exit_gap = obstacle["exit_gap_m"] if pd.notna(obstacle["exit_gap_m"]) else 5.0
        exit_length = obstacle["exit_length_m"] if pd.notna(obstacle["exit_length_m"]) else 15.0
        recovery_limit = obstacle["recovery_limit_m"] if pd.notna(obstacle["recovery_limit_m"]) else 60.0
        flags = []
        if chosen["error_m"] > 12.0:
            flags.append("anchor_far_from_reference_line")
        if nearest_alternative and nearest_alternative["error_m"] - chosen["error_m"] < 3.0:
            flags.append("multiple_nearby_track_branches")
        if obstacle["kind"] == "interval" and extent_source == "assumed_default":
            flags.append("interval_extent_must_be_measured")
        if obstacle["input_format"] == "legacy_printed_report":
            flags.append("legacy_input_needs_new_definition")

        row = obstacle.to_dict()
        row.update(
            {
                "anchor_s_m": float(chosen["s_m"]),
                "anchor_projection_error_m": float(chosen["error_m"]),
                "projected_latitude": float(projected_lat[0]),
                "projected_longitude": float(projected_lon[0]),
                "nearest_alternative_error_m": float(nearest_alternative["error_m"]) if nearest_alternative else np.nan,
                "nearest_alternative_s_m": float(nearest_alternative["s_m"]) if nearest_alternative else np.nan,
                "feature_start_rel_m": float(feature_start_rel),
                "feature_end_rel_m": float(feature_end_rel),
                "entry_start_rel_m": float(feature_start_rel - entry_before),
                "entry_end_rel_m": float(feature_start_rel - entry_gap),
                "exit_start_rel_m": float(feature_end_rel + exit_gap),
                "exit_end_rel_m": float(feature_end_rel + exit_gap + exit_length),
                "recovery_limit_m": float(recovery_limit),
                "extent_source": extent_source,
                "review_flags": ";".join(flags),
            }
        )
        rows.append(row)

    resolved = pd.DataFrame(rows).sort_values("sequence").reset_index(drop=True)
    # Flag feature zones that overlap their course-order neighbours. This is a
    # definition issue: the analyst must either separate the features or declare
    # them a compound group.
    for i in range(len(resolved) - 1):
        current_end = resolved.loc[i, "anchor_s_m"] + resolved.loc[i, "feature_end_rel_m"]
        next_start = resolved.loc[i + 1, "anchor_s_m"] + resolved.loc[i + 1, "feature_start_rel_m"]
        if next_start < current_end:
            for idx in (i, i + 1):
                existing = [f for f in str(resolved.loc[idx, "review_flags"]).split(";") if f]
                if "overlaps_adjacent_feature" not in existing:
                    existing.append("overlaps_adjacent_feature")
                resolved.loc[idx, "review_flags"] = ";".join(existing)
    return resolved


def build_analysis_features(obstacles: pd.DataFrame, track_length_m: float) -> pd.DataFrame:
    """Collapse declared compound groups into one analysis interval.

    Definition rows remain intact in ``obstacle_definitions_resolved.csv``. A
    nonblank compound_group (other than SEPARATE) causes its member definitions
    to be measured as one feature spanning the earliest start to latest end.
    """
    definitions = obstacles.copy()
    if "compound_group" not in definitions:
        definitions["compound_group"] = ""
    group_value = definitions["compound_group"].fillna("").astype(str).str.strip()
    definitions["_group_key"] = group_value.where(~group_value.str.casefold().isin(["", "separate"]), "")
    rows: list[dict] = []
    consumed_groups: set[str] = set()

    for _, obstacle in definitions.sort_values("sequence").iterrows():
        group = str(obstacle["_group_key"])
        if not group:
            row = obstacle.drop(labels=["_group_key"]).to_dict()
            row["source_members"] = obstacle["name"]
            row["analysis_feature_type"] = "individual"
            rows.append(row)
            continue
        if group in consumed_groups:
            continue
        consumed_groups.add(group)
        members = definitions[definitions["_group_key"] == group].sort_values("sequence")
        starts = members["anchor_s_m"] + members["feature_start_rel_m"]
        ends = members["anchor_s_m"] + members["feature_end_rel_m"]
        start_abs = float(starts.min())
        end_abs = float(ends.max())
        midpoint_abs = (start_abs + end_abs) / 2.0
        anchor_s = midpoint_abs % track_length_m
        base = members.iloc[0].drop(labels=["_group_key"]).to_dict()
        names = members["name"].astype(str).tolist()
        combined_flags = sorted(
            {
                flag
                for flags in members["review_flags"].fillna("")
                for flag in str(flags).split(";")
                if flag and flag != "overlaps_adjacent_feature"
            }
        )
        base.update(
            {
                "sequence": int(members["sequence"].min()),
                "name": f"Compound {group}: " + " + ".join(names),
                "kind": "interval",
                "anchor_s_m": anchor_s,
                "feature_start_rel_m": start_abs - midpoint_abs,
                "feature_end_rel_m": end_abs - midpoint_abs,
                "entry_start_rel_m": start_abs - midpoint_abs - 30.0,
                "entry_end_rel_m": start_abs - midpoint_abs - 10.0,
                "exit_start_rel_m": end_abs - midpoint_abs + 5.0,
                "exit_end_rel_m": end_abs - midpoint_abs + 20.0,
                "recovery_limit_m": float(members["recovery_limit_m"].max()),
                "extent_source": "compound_member_union",
                "review_flags": ";".join(combined_flags),
                "source_members": ";".join(names),
                "analysis_feature_type": "compound_group",
            }
        )
        rows.append(base)
    return pd.DataFrame(rows).sort_values(["sequence", "name"]).reset_index(drop=True)


def deduplicated_profile(segment: pd.DataFrame, centreline: Centreline) -> pd.DataFrame:
    good = segment[segment["map_error_m"] <= 20.0][["s_m", "speed_analysis_kmh", "elapsed_lap_s"]].copy()
    good["s_bin"] = good["s_m"].round(1)
    profile = good.groupby("s_bin", as_index=False).agg(
        s_m=("s_m", "median"),
        speed_kmh=("speed_analysis_kmh", "median"),
        elapsed_s=("elapsed_lap_s", "median"),
    )
    return profile.sort_values("s_m")


def circular_relative_s(s_m: np.ndarray, anchor_s_m: float, track_length_m: float) -> np.ndarray:
    return (s_m - anchor_s_m + track_length_m / 2.0) % track_length_m - track_length_m / 2.0


def interpolate_lap_profile(profile: pd.DataFrame, centreline: Centreline, grid_s: np.ndarray) -> np.ndarray:
    s = profile["s_m"].to_numpy(dtype=float)
    v = profile["speed_kmh"].to_numpy(dtype=float)
    if len(s) < 3:
        return np.full(len(grid_s), np.nan)
    # Add wrapped endpoints so the start/finish bin does not depend on which
    # side of the gate got the nearest timestamp.
    s_aug = np.r_[s[-1] - centreline.length_m, s, s[0] + centreline.length_m]
    v_aug = np.r_[v[-1], v, v[0]]
    return np.interp(grid_s, s_aug, v_aug)


def build_track_profile(
    matched: pd.DataFrame,
    laps: pd.DataFrame,
    centreline: Centreline,
    cfg: AnalysisConfig,
) -> tuple[pd.DataFrame, dict[int, pd.DataFrame]]:
    grid_s = np.arange(0.0, centreline.length_m, cfg.profile_spacing_m)
    valid_lap_ids = set(laps.loc[laps["analysis_valid"], "lap_id"].astype(int))
    speed_columns = []
    lap_profiles: dict[int, pd.DataFrame] = {}
    for lap_id, segment in matched.groupby("lap_id"):
        profile = deduplicated_profile(segment, centreline)
        lap_profiles[int(lap_id)] = profile
        if int(lap_id) in valid_lap_ids:
            speed_columns.append(interpolate_lap_profile(profile, centreline, grid_s))
    if not speed_columns:
        raise ValueError("No valid map-matched laps remained for the spatial profile")
    matrix = np.vstack(speed_columns)
    track = pd.DataFrame(
        {
            "s_m": grid_s,
            "median_speed_kmh": np.nanmedian(matrix, axis=0),
            "p25_speed_kmh": np.nanquantile(matrix, 0.25, axis=0),
            "p75_speed_kmh": np.nanquantile(matrix, 0.75, axis=0),
            "minimum_speed_kmh": np.nanmin(matrix, axis=0),
            "maximum_speed_kmh": np.nanmax(matrix, axis=0),
            "valid_lap_count": np.sum(np.isfinite(matrix), axis=0),
        }
    )
    return track, lap_profiles


def interval_stat(rel_grid: np.ndarray, values: np.ndarray, low: float, high: float, statistic: str = "median") -> float:
    selected = values[(rel_grid >= low) & (rel_grid <= high) & np.isfinite(values)]
    if len(selected) == 0:
        return float("nan")
    if statistic == "min":
        return float(np.min(selected))
    return float(np.median(selected))


def obstacle_pass_metrics(
    matched: pd.DataFrame,
    laps: pd.DataFrame,
    obstacles: pd.DataFrame,
    lap_profiles: dict[int, pd.DataFrame],
    centreline: Centreline,
    cfg: AnalysisConfig,
) -> pd.DataFrame:
    rows = []
    lap_lookup = laps.set_index("lap_id")
    local_step = min(2.0, cfg.profile_spacing_m)
    rel_grid = np.arange(-100.0, 121.0, local_step)
    for _, obstacle in obstacles.iterrows():
        absolute_grid = (obstacle["anchor_s_m"] + rel_grid) % centreline.length_m
        for lap_id, profile in lap_profiles.items():
            speed = interpolate_lap_profile(profile, centreline, absolute_grid)
            entry_speed = interval_stat(
                rel_grid, speed, obstacle["entry_start_rel_m"], obstacle["entry_end_rel_m"]
            )
            feature_min = interval_stat(
                rel_grid, speed, obstacle["feature_start_rel_m"], obstacle["feature_end_rel_m"], "min"
            )
            feature_median = interval_stat(
                rel_grid, speed, obstacle["feature_start_rel_m"], obstacle["feature_end_rel_m"]
            )
            anchor_speed = float(np.interp(0.0, rel_grid, speed))
            exit_speed = interval_stat(
                rel_grid, speed, obstacle["exit_start_rel_m"], obstacle["exit_end_rel_m"]
            )

            recovery_distance = np.nan
            if np.isfinite(entry_speed):
                recovery_mask = (
                    (rel_grid >= obstacle["feature_end_rel_m"])
                    & (rel_grid <= obstacle["feature_end_rel_m"] + obstacle["recovery_limit_m"])
                    & np.isfinite(speed)
                    & (speed >= cfg.default_recovery_fraction * entry_speed)
                )
                if recovery_mask.any():
                    recovery_distance = float(
                        rel_grid[np.flatnonzero(recovery_mask)[0]] - obstacle["feature_end_rel_m"]
                    )

            # Approximate traversal time by integrating ds/v on the spatial
            # profile. It is reported as observed time, not dissipated energy.
            feature_mask = (
                (rel_grid >= obstacle["feature_start_rel_m"])
                & (rel_grid <= obstacle["feature_end_rel_m"])
                & np.isfinite(speed)
            )
            if feature_mask.sum() >= 2:
                feature_s = rel_grid[feature_mask]
                feature_v = np.maximum(speed[feature_mask] / 3.6, 0.5)
                feature_time_s = float(np.trapezoid(1.0 / feature_v, feature_s))
            else:
                feature_time_s = np.nan

            lap_segment = matched[matched["lap_id"] == lap_id]
            rel_samples = circular_relative_s(
                lap_segment["s_m"].to_numpy(), obstacle["anchor_s_m"], centreline.length_m
            )
            quality_zone = (
                (rel_samples >= obstacle["entry_start_rel_m"])
                & (rel_samples <= obstacle["exit_end_rel_m"])
            )
            zone_errors = lap_segment.loc[quality_zone, "map_error_m"]
            quality_flags = []
            if not bool(lap_lookup.loc[lap_id, "analysis_valid"]):
                quality_flags.append("lap_excluded_from_aggregate")
            if len(zone_errors) < 3:
                quality_flags.append("few_raw_samples_in_zone")
            if len(zone_errors) and float(zone_errors.max()) > cfg.maximum_map_error_m:
                quality_flags.append("high_map_error_in_zone")
            if any(not np.isfinite(x) for x in (entry_speed, feature_min, exit_speed)):
                quality_flags.append("incomplete_metric_window")

            rows.append(
                {
                    "sequence": int(obstacle["sequence"]),
                    "obstacle": obstacle["name"],
                    "lap_id": int(lap_id),
                    "lap_analysis_valid": bool(lap_lookup.loc[lap_id, "analysis_valid"]),
                    "anchor_s_m": float(obstacle["anchor_s_m"]),
                    "entry_speed_kmh": entry_speed,
                    "feature_min_speed_kmh": feature_min,
                    "feature_median_speed_kmh": feature_median,
                    "anchor_speed_kmh": anchor_speed,
                    "exit_speed_kmh": exit_speed,
                    "ordered_entry_to_min_change_kmh": entry_speed - feature_min,
                    "signed_entry_to_exit_change_kmh": exit_speed - entry_speed,
                    "feature_traversal_time_s": feature_time_s,
                    "recovery_distance_m": recovery_distance,
                    "raw_samples_in_entry_to_exit_zone": int(quality_zone.sum()),
                    "median_map_error_in_zone_m": float(zone_errors.median()) if len(zone_errors) else np.nan,
                    "quality_flags": ";".join(quality_flags),
                }
            )
    return pd.DataFrame(rows)


def q25(series: pd.Series) -> float:
    return float(series.quantile(0.25))


def q75(series: pd.Series) -> float:
    return float(series.quantile(0.75))


def summarize_obstacles(passes: pd.DataFrame, obstacles: pd.DataFrame) -> pd.DataFrame:
    valid = passes[passes["lap_analysis_valid"] & passes["quality_flags"].eq("")].copy()
    metrics = [
        "entry_speed_kmh",
        "feature_min_speed_kmh",
        "ordered_entry_to_min_change_kmh",
        "signed_entry_to_exit_change_kmh",
        "feature_traversal_time_s",
        "recovery_distance_m",
    ]
    rows = []
    for (sequence, name), group in valid.groupby(["sequence", "obstacle"], sort=True):
        row: dict[str, object] = {
            "sequence": int(sequence),
            "obstacle": name,
            "valid_passes": int(len(group)),
        }
        for metric in metrics:
            row[f"median_{metric}"] = float(group[metric].median())
            row[f"p25_{metric}"] = q25(group[metric])
            row[f"p75_{metric}"] = q75(group[metric])
        rows.append(row)
    summary = pd.DataFrame(rows)
    definition_cols = [
        "sequence",
        "name",
        "kind",
        "anchor_s_m",
        "anchor_projection_error_m",
        "feature_start_rel_m",
        "feature_end_rel_m",
        "extent_source",
        "review_flags",
    ]
    definitions = obstacles[definition_cols].rename(columns={"name": "obstacle"})
    return definitions.merge(summary, on=["sequence", "obstacle"], how="left").sort_values("sequence")


def add_track_context(track: pd.DataFrame, centreline: Centreline) -> pd.DataFrame:
    x = np.interp(track["s_m"], centreline.s_nodes_m, centreline.x)
    y = np.interp(track["s_m"], centreline.s_nodes_m, centreline.y)
    lat, lon = centreline.frame.to_latlon(x, y)
    out = track.copy()
    out.insert(1, "latitude", lat)
    out.insert(2, "longitude", lon)
    return out


def create_plots(
    output_dir: Path,
    matched: pd.DataFrame,
    laps: pd.DataFrame,
    centreline: Centreline,
    obstacles: pd.DataFrame,
    track_profile: pd.DataFrame,
) -> None:
    plt.figure(figsize=(10, 8))
    plt.plot(centreline.x, centreline.y, color="0.25", linewidth=1.4, label="Reference centreline")
    ox, oy = centreline.frame.to_xy(obstacles["latitude"], obstacles["longitude"])
    px, py = centreline.frame.to_xy(obstacles["projected_latitude"], obstacles["projected_longitude"])
    for x0, y0, x1, y1 in zip(ox, oy, px, py):
        plt.plot([x0, x1], [y0, y1], color="0.75", linewidth=0.7)
    plt.scatter(ox, oy, s=18, color="#d95f02", label="Supplied anchor")
    plt.scatter(px, py, s=13, color="#1b9e77", label="Projected s")
    for _, row in obstacles.iterrows():
        x_label, y_label = centreline.frame.to_xy([row["projected_latitude"]], [row["projected_longitude"]])
        plt.text(x_label[0] + 2, y_label[0] + 2, str(int(row["sequence"])), fontsize=7)
    plt.axis("equal")
    plt.xlabel("East [m]")
    plt.ylabel("North [m]")
    plt.title("Reference centreline and obstacle projection (labels = sequence)")
    plt.legend(loc="best")
    plt.tight_layout()
    plt.savefig(output_dir / "01_track_and_obstacle_projection.png", dpi=180)
    plt.close()

    plt.figure(figsize=(14, 6))
    s = track_profile["s_m"].to_numpy()
    median = track_profile["median_speed_kmh"].to_numpy()
    p25 = track_profile["p25_speed_kmh"].to_numpy()
    p75 = track_profile["p75_speed_kmh"].to_numpy()
    plt.fill_between(s, p25, p75, color="#80b1d3", alpha=0.35, label="25th–75th percentile")
    plt.plot(s, median, color="#1f4e79", linewidth=1.5, label="Median valid-lap speed")
    ymax = max(1.0, float(np.nanmax(p75)))
    for _, row in obstacles.iterrows():
        plt.axvline(row["anchor_s_m"], color="0.65", linewidth=0.35, alpha=0.7)
        plt.text(row["anchor_s_m"], ymax * 1.01, str(int(row["sequence"])), rotation=90, fontsize=6, ha="center")
    plt.xlabel("Track coordinate s [m]")
    plt.ylabel("GPS speed [km/h]")
    plt.title("Spatial speed profile (numbers correspond to obstacle sequence)")
    plt.ylim(bottom=0)
    plt.legend(loc="lower right")
    plt.tight_layout()
    plt.savefig(output_dir / "02_spatial_speed_profile.png", dpi=180)
    plt.close()

    colors = ["#1b9e77" if valid else "#d95f02" for valid in laps["analysis_valid"]]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(laps["lap_id"].astype(str), laps["duration_s"], color=colors)
    for _, row in laps.iterrows():
        if row["reference_lap"]:
            # Categorical bar positions are zero based.
            ax.text(int(row["lap_id"]) - 1, row["duration_s"] + 5, "reference", ha="center", fontsize=8)
    ax.set_xlabel("Detected lap")
    ax.set_ylabel("Gate-to-gate duration [s]")
    ax.set_title("Lap selection (green = retained for aggregate profile)")
    fig.tight_layout()
    lap_plot_path = output_dir / "03_lap_quality.png"
    fig.savefig(lap_plot_path, dpi=180)
    plt.close(fig)
    if not lap_plot_path.exists() or lap_plot_path.stat().st_size == 0:
        raise OSError(f"Failed to render {lap_plot_path}")


def write_must_fill(path: Path, obstacles: pd.DataFrame) -> None:
    interval = obstacles["kind"].eq("interval") & obstacles["extent_source"].eq("assumed_default")
    geometry = obstacles["review_flags"].str.contains(
        "anchor_far_from_reference_line|multiple_nearby_track_branches|overlaps_adjacent_feature",
        regex=True,
        na=False,
    )
    review = obstacles[interval | geometry].copy()

    lines = [
        "# OBSTACLE DEFINITION ITEMS THAT MUST BE CHECKED",
        "# This is the short human correction request, not the direct script input.",
        "# Return this file, then merge its answers into Obstacles_improved_input.txt.",
        "# Keep the | separators and leave a field blank only if it truly does not apply.",
        "#",
        "# For an interval, record GPS at the physical START and END in driving direction.",
        "# For a bad/ambiguous anchor, record one corrected centre/apex GPS point.",
        "# For touching features, put the same compound_group on rows that should be analysed as one event;",
        "# otherwise write SEPARATE in notes and make sure their start/end points do not overlap.",
        "# kind must be point, interval, or turn_apex.",
        "#",
        "sequence | name | kind | corrected_anchor_lat | corrected_anchor_lon | start_lat | start_lon | end_lat | end_lon | compound_group_or_SEPARATE | response_notes | required_action",
    ]
    for _, row in review.iterrows():
        flags = str(row["review_flags"]).replace("legacy_input_needs_new_definition;", "").replace(";legacy_input_needs_new_definition", "")
        if flags == "legacy_input_needs_new_definition":
            flags = ""
        lines.append(
            f"{int(row['sequence'])} | {row['name']} | {row['kind']} |  |  |  |  |  |  |  |  | {flags}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_preferred_obstacle_input(path: Path, obstacles: pd.DataFrame) -> None:
    """Write a complete definition file that can be fed back to this script."""
    lines = [
        "# COMPLETE PREFERRED OBSTACLE INPUT — directly accepted by trackAnalysis_improved.py",
        "# Keep every row. Fill fields whose notes begin MUST. Coordinates are decimal degrees.",
        "# Interval start/end must be recorded in driving direction.",
        "# Use the same nonblank compound_group ID to analyse several inseparable rows as one interval.",
        "#",
        "sequence | name | kind | latitude | longitude | start_latitude | start_longitude | end_latitude | end_longitude | compound_group | notes",
    ]
    for _, row in obstacles.iterrows():
        actions = []
        flags = [
            flag for flag in str(row["review_flags"]).split(";")
            if flag and flag != "legacy_input_needs_new_definition"
        ]
        if "interval_extent_must_be_measured" in flags:
            actions.append("MUST fill start/end")
        if "anchor_far_from_reference_line" in flags or "multiple_nearby_track_branches" in flags:
            actions.append("MUST verify/correct anchor")
        if "overlaps_adjacent_feature" in flags:
            actions.append("MUST mark compound group or confirm SEPARATE")
        note = "; ".join(actions) if actions else "anchor usable for first run"

        def formatted_optional(column: str) -> str:
            value = row.get(column, np.nan)
            return f"{float(value):.7f}" if pd.notna(value) else ""

        compound = str(row.get("compound_group", "")).strip()
        if compound.lower() == "nan":
            compound = ""
        lines.append(
            " | ".join(
                [
                    str(int(row["sequence"])),
                    str(row["name"]),
                    str(row["kind"]),
                    f"{float(row['latitude']):.7f}",
                    f"{float(row['longitude']):.7f}",
                    formatted_optional("start_latitude"),
                    formatted_optional("start_longitude"),
                    formatted_optional("end_latitude"),
                    formatted_optional("end_longitude"),
                    compound,
                    note,
                ]
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_report(
    path: Path,
    cfg: AnalysisConfig,
    cleaning: dict,
    laps: pd.DataFrame,
    centreline: Centreline,
    obstacles: pd.DataFrame,
    passes: pd.DataFrame,
) -> None:
    valid_laps = int(laps["analysis_valid"].sum())
    ref_lap = int(laps.loc[laps["reference_lap"], "lap_id"].iloc[0])
    ref_speed_distance = float(laps.loc[laps["reference_lap"], "speed_integrated_distance_m"].iloc[0])
    geometry_distance_difference = (centreline.length_m / ref_speed_distance - 1.0) * 100.0
    valid_passes = passes[passes["lap_analysis_valid"] & passes["quality_flags"].eq("")]
    interval_assumptions = int(
        (obstacles["kind"].eq("interval") & obstacles["extent_source"].eq("assumed_default")).sum()
    )
    projection_warnings = int(
        obstacles["review_flags"].str.contains("anchor_far_from_reference_line|multiple_nearby_track_branches", regex=True).sum()
    )
    lines = [
        "IMPROVED SINGLE-s TRACK ANALYSIS — FIRST-RUN REPORT",
        "",
        "Run scope",
        f"- Clean GPS rows: {cleaning['output_rows']} of {cleaning['input_rows']}",
        f"- Median sample period: {cleaning['median_sample_period_s']:.3f} s",
        f"- Isolated speed spikes replaced: {cleaning['isolated_speed_spikes_replaced']}",
        f"- Time gaps over {cfg.maximum_normal_time_step_s:.1f} s: {cleaning['time_gaps_over_limit']}",
        f"- Gate-to-gate laps detected: {len(laps)}",
        f"- Laps retained for aggregate results: {valid_laps}",
        f"- Reference centreline lap: {ref_lap}",
        f"- Reference track length: {centreline.length_m:.1f} m",
        f"- Centreline vs reference-lap speed-integrated distance: {geometry_distance_difference:+.1f}%",
        f"- Obstacles projected onto s: {len(obstacles)}",
        f"- Obstacle/lap rows passing aggregate quality checks: {len(valid_passes)}",
        "",
        "Definition work still required",
        f"- Interval features using assumed ±15 m extents: {interval_assumptions}",
        f"- Anchor/branch projection warnings: {projection_warnings}",
        "- See Obstacles_must_fill.txt and obstacle_definitions_resolved.csv.",
        "",
        "What these results mean",
        "- s is a single ordered distance around the lap, so entry, feature, exit, and recovery are not mixed up by timestamp order.",
        "- The reported entry-to-minimum change is ordered: the entry zone is before the defined feature and the minimum is inside it.",
        "- Medians and 25th–75th percentile ranges describe repeatability across retained laps.",
        "- Excluded pit/stopped/incomplete laps remain visible in lap_summary.csv and obstacle_passes.csv.",
        "",
        "GPS-only limitations (must not be over-interpreted)",
        "- No throttle signal: the analysis cannot know whether the driver wanted maximum acceleration.",
        "- No RPM/CVT-ratio/wheel-speed channels: it cannot directly identify time outside the power band, CVT shift delay, or wheel slip.",
        "- Speed change is not energy dissipation. Grade, braking, turning, impacts, suspension motion, soil deformation, and driver choice are confounded.",
        "- A reference line from one lap is an analysis coordinate, not a surveyed track centreline; map-error and definition flags must be reviewed.",
        "- The 1 Hz source limits spatial resolution. Interpolation helps align laps but does not create new measurements.",
        "",
        "Recommended next channels for the CVT/gearing question",
        "- Engine RPM, primary and secondary pulley speed (or ratio), driven-wheel speed, throttle position, brake state, and a higher-rate GPS/IMU.",
        "- With throttle, evaluate only driver-demanded acceleration windows; with RPM/ratio, measure power-band occupancy and shift recovery directly.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def export_outputs(
    output_dir: Path,
    cleaning: dict,
    laps: pd.DataFrame,
    centreline: Centreline,
    obstacles: pd.DataFrame,
    analysis_features: pd.DataFrame,
    track_profile: pd.DataFrame,
    passes: pd.DataFrame,
    summary: pd.DataFrame,
    matched: pd.DataFrame,
    cfg: AnalysisConfig,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    centre_lat, centre_lon = centreline.frame.to_latlon(centreline.x, centreline.y)
    centre_df = pd.DataFrame(
        {"s_m": centreline.s_nodes_m, "latitude": centre_lat, "longitude": centre_lon, "x_m": centreline.x, "y_m": centreline.y}
    )
    track_profile = add_track_context(track_profile, centreline)
    matched_export = matched[
        [
            "timestamp",
            "lap_id",
            "lat",
            "lon",
            "speed_kmh",
            "speed_analysis_kmh",
            "s_m",
            "map_error_m",
            "elapsed_lap_s",
        ]
    ].copy()

    laps.to_csv(output_dir / "lap_summary.csv", index=False)
    centre_df.to_csv(output_dir / "reference_centreline.csv", index=False)
    obstacles.to_csv(output_dir / "obstacle_definitions_resolved.csv", index=False)
    analysis_features.to_csv(output_dir / "analysis_features.csv", index=False)
    track_profile.to_csv(output_dir / "track_speed_profile.csv", index=False)
    passes.to_csv(output_dir / "obstacle_passes.csv", index=False)
    summary.to_csv(output_dir / "obstacle_summary.csv", index=False)
    matched_export.to_csv(output_dir / "map_matched_gps.csv", index=False)

    cleaning_df = pd.DataFrame({"check": list(cleaning), "value": list(cleaning.values())})
    with pd.ExcelWriter(output_dir / "track_analysis_improved.xlsx", engine="openpyxl") as writer:
        cleaning_df.to_excel(writer, sheet_name="Cleaning", index=False)
        laps.to_excel(writer, sheet_name="Laps", index=False)
        summary.to_excel(writer, sheet_name="Obstacle Summary", index=False)
        passes.to_excel(writer, sheet_name="Obstacle Passes", index=False)
        obstacles.to_excel(writer, sheet_name="Definitions", index=False)
        analysis_features.to_excel(writer, sheet_name="Analysis Features", index=False)
        track_profile.to_excel(writer, sheet_name="Track Profile", index=False)
        centre_df.to_excel(writer, sheet_name="Centreline", index=False)

    write_must_fill(output_dir / "Obstacles_must_fill.txt", obstacles)
    write_preferred_obstacle_input(output_dir / "Obstacles_improved_input.txt", obstacles)
    write_report(
        output_dir / "FIRST_RUN_REPORT.txt",
        cfg,
        cleaning,
        laps,
        centreline,
        obstacles,
        passes,
    )
    create_plots(output_dir, matched, laps, centreline, obstacles, track_profile)


def main() -> int:
    args = parse_args()
    cfg = AnalysisConfig(
        lap_gate_name=args.lap_gate,
        profile_spacing_m=args.profile_spacing_m,
        centreline_spacing_m=args.centreline_spacing_m,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    gps, cleaning = load_and_clean_gps(args.csv, cfg)
    obstacles = load_obstacles(args.obstacles)
    gate_match = obstacles[obstacles["name"].str.casefold() == cfg.lap_gate_name.casefold()]
    if gate_match.empty:
        raise ValueError(f"Lap gate obstacle {cfg.lap_gate_name!r} was not found")
    gate = gate_match.iloc[0]
    frame = LocalFrame(float(gps["lat"].median()), float(gps["lon"].median()))
    crossings = detect_gate_crossings(gps, frame, float(gate["latitude"]), float(gate["longitude"]), cfg)
    if len(crossings) < 3:
        raise ValueError(f"Only {len(crossings)} lap-gate visits were found; at least 3 are needed")
    laps = build_lap_table(gps, crossings, cfg)
    centreline = build_centreline(gps, laps, frame, cfg)
    matched, laps = map_match_laps(gps, laps, centreline)
    projected_obstacles = project_obstacles(obstacles, centreline)
    analysis_features = build_analysis_features(projected_obstacles, centreline.length_m)
    track_profile, lap_profiles = build_track_profile(matched, laps, centreline, cfg)
    passes = obstacle_pass_metrics(
        matched,
        laps,
        analysis_features,
        lap_profiles,
        centreline,
        cfg,
    )
    summary = summarize_obstacles(passes, analysis_features)
    export_outputs(
        args.output_dir,
        cleaning,
        laps,
        centreline,
        projected_obstacles,
        analysis_features,
        track_profile,
        passes,
        summary,
        matched,
        cfg,
    )

    print(f"Completed: {args.output_dir.resolve()}")
    print(f"Detected {len(laps)} complete laps; retained {int(laps['analysis_valid'].sum())} for aggregate results.")
    print(f"Reference centreline length: {centreline.length_m:.1f} m")
    print(f"Projected {len(projected_obstacles)} obstacles; wrote {len(passes)} obstacle/lap rows.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
