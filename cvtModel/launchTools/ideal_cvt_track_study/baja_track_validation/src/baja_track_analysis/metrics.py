from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .config import PipelineConfig
from .gps_core import Centreline, circular_relative_s, interpolate_lap_profile


PASS_METRICS = (
    "approach_speed_kmh",
    "entry_speed_kmh",
    "approach_acceleration_mps2",
    "event_min_speed_kmh",
    "distance_to_min_m",
    "end_speed_kmh",
    "post_event_speed_kmh",
    "ordered_entry_to_min_change_kmh",
    "signed_entry_to_end_change_kmh",
    "specific_ke_change_to_min_j_per_kg",
    "specific_ke_change_to_end_j_per_kg",
    "event_time_s",
    "recovery_distance_m",
    "recovery_time_s",
)

OPTIONAL_TELEMETRY_METRICS = (
    "approach_throttle_pct",
    "entry_throttle_pct",
    "event_throttle_pct",
    "full_throttle_fraction_approach",
    "full_throttle_fraction_event",
    "approach_brake_fraction",
    "event_brake_fraction",
    "positive_driver_demand_fraction_event",
    "entry_engine_rpm",
    "event_engine_rpm_median",
    "power_band_fraction_event",
    "entry_primary_rpm",
    "event_primary_rpm_median",
    "entry_secondary_rpm",
    "event_secondary_rpm_median",
    "entry_cvt_ratio",
    "event_cvt_ratio_median",
    "event_wheel_slip_proxy_median",
    "event_wheel_slip_fraction",
)

TELEMETRY_COVERAGE_METRICS = (
    "throttle_sample_coverage_event",
    "brake_sample_coverage_event",
    "engine_rpm_sample_coverage_event",
    "primary_rpm_sample_coverage_event",
    "secondary_rpm_sample_coverage_event",
    "cvt_ratio_sample_coverage_event",
    "wheel_speed_sample_coverage_event",
)


def add_event_geometry(features: pd.DataFrame, track_length_m: float) -> pd.DataFrame:
    """Add absolute event bounds and recovery space to ordered analysis groups."""

    out = features.sort_values(["sequence", "name"]).reset_index(drop=True).copy()
    if "final_group_id" not in out:
        out["final_group_id"] = [f"E{int(sequence):02d}" for sequence in out["sequence"]]
    out["analysis_group_id"] = out["final_group_id"].astype(str)
    out["event_start_s_m"] = (out["anchor_s_m"] + out["feature_start_rel_m"]) % track_length_m
    out["event_end_s_m"] = (out["anchor_s_m"] + out["feature_end_rel_m"]) % track_length_m
    out["event_length_m"] = out["feature_end_rel_m"] - out["feature_start_rel_m"]

    absolute_starts = out["anchor_s_m"].to_numpy(float) + out["feature_start_rel_m"].to_numpy(float)
    absolute_ends = out["anchor_s_m"].to_numpy(float) + out["feature_end_rel_m"].to_numpy(float)
    gaps = []
    for index in range(len(out)):
        if index + 1 < len(out):
            next_start = absolute_starts[index + 1]
            while next_start < absolute_ends[index] - track_length_m / 2:
                next_start += track_length_m
        else:
            next_start = absolute_starts[0] + track_length_m
        gaps.append(float(next_start - absolute_ends[index]))
    out["distance_to_next_event_m"] = gaps
    out["recovery_space_before_next_m"] = np.maximum(out["distance_to_next_event_m"], 0.0)
    return out


def extract_event_passes(
    matched: pd.DataFrame,
    laps: pd.DataFrame,
    features: pd.DataFrame,
    lap_profiles: dict[int, pd.DataFrame],
    centreline: Centreline,
    config: PipelineConfig,
    median_sample_period_s: float,
) -> pd.DataFrame:
    """Compute ordered per-pass metrics for simulation validation.

    Entry speed is sampled immediately before the resolved group start.
    Approach speed is a separate upstream median. End speed is at the physical
    end of the group; post-event speed is only a diagnostic. Specific kinetic
    energy changes are observations, never labelled obstacle energy loss.
    """

    cfg = config.metric
    lap_lookup = laps.set_index("lap_id")
    rows: list[dict[str, object]] = []

    for _, feature in features.iterrows():
        start = float(feature["feature_start_rel_m"])
        end = float(feature["feature_end_rel_m"])
        event_length = end - start
        gap_to_next = float(feature["distance_to_next_event_m"])
        available_recovery = max(0.0, min(gap_to_next, cfg.recovery_limit_m))
        grid_low = start - cfg.approach_distance_m - 2.0
        grid_high = end + max(cfg.recovery_limit_m, cfg.post_event_gap_m + cfg.post_event_window_m) + 2.0
        rel_grid = np.arange(grid_low, grid_high + cfg.spatial_step_m / 2, cfg.spatial_step_m)
        absolute_grid = (float(feature["anchor_s_m"]) + rel_grid) % centreline.length_m

        for lap_id, profile in lap_profiles.items():
            speed = interpolate_lap_profile(profile, centreline, absolute_grid)
            approach_speed = _median_between(speed, rel_grid, start - cfg.approach_distance_m, start - cfg.approach_gap_m)
            entry_speed = _median_between(speed, rel_grid, start - cfg.immediate_entry_window_m, start)
            event_mask = _mask(rel_grid, start, end, speed)
            if event_mask.any():
                event_indices = np.flatnonzero(event_mask)
                local_min_index = event_indices[int(np.nanargmin(speed[event_mask]))]
                event_min = float(speed[local_min_index])
                distance_to_min = float(rel_grid[local_min_index] - start)
            else:
                event_min = math.nan
                distance_to_min = math.nan
            end_speed = _median_between(speed, rel_grid, end - cfg.end_speed_window_m, end + cfg.end_speed_window_m)
            post_event_speed = _median_between(
                speed,
                rel_grid,
                end + cfg.post_event_gap_m,
                end + cfg.post_event_gap_m + cfg.post_event_window_m,
            )
            approach_accel = _spatial_acceleration(
                speed,
                rel_grid,
                start - cfg.approach_distance_m,
                start,
            )
            event_time = _travel_time(speed, rel_grid, start, end)

            recovery_distance = math.nan
            recovery_time = math.nan
            recovered_before_next: bool | float = False
            if np.isfinite(entry_speed) and available_recovery > 0:
                threshold = cfg.recovery_fraction * entry_speed
                recovery_mask = (
                    (rel_grid >= end)
                    & (rel_grid <= end + available_recovery)
                    & np.isfinite(speed)
                    & (speed >= threshold)
                )
                if recovery_mask.any():
                    recovery_location = float(rel_grid[np.flatnonzero(recovery_mask)[0]])
                    recovery_distance = recovery_location - end
                    recovery_time = _travel_time(speed, rel_grid, end, recovery_location)
                    recovered_before_next = True

            lap_segment = matched[matched["lap_id"] == lap_id]
            rel_samples = circular_relative_s(
                lap_segment["s_m"].to_numpy(float),
                float(feature["anchor_s_m"]),
                centreline.length_m,
            )
            approach_sample_mask = (
                (rel_samples >= start - cfg.approach_distance_m)
                & (rel_samples <= start - cfg.approach_gap_m)
            )
            entry_sample_mask = (rel_samples >= start - cfg.immediate_entry_window_m) & (rel_samples <= start)
            event_sample_mask = (rel_samples >= start) & (rel_samples <= end)
            complete_sample_mask = (
                (rel_samples >= start - cfg.approach_distance_m)
                & (rel_samples <= end + cfg.end_speed_window_m)
            )
            zone_errors = lap_segment.loc[complete_sample_mask, "map_error_m"]
            median_map_error = float(zone_errors.median()) if len(zone_errors) else math.nan
            maximum_map_error = float(zone_errors.max()) if len(zone_errors) else math.nan
            finite_reference_speeds = [
                value for value in (entry_speed, approach_speed) if np.isfinite(value)
            ]
            nominal_resolution = (
                max([0.0, *finite_reference_speeds]) / 3.6 * median_sample_period_s
                if finite_reference_speeds
                else math.nan
            )
            effective_resolution = (
                max(nominal_resolution, 2.0 * median_map_error)
                if np.isfinite(nominal_resolution) and np.isfinite(median_map_error)
                else nominal_resolution
            )

            flags: list[str] = []
            fatal = False
            if not bool(lap_lookup.loc[lap_id, "analysis_valid"]):
                flags.append("lap_excluded_from_aggregate")
                fatal = True
            if int(event_sample_mask.sum()) < cfg.minimum_raw_samples_in_event:
                flags.append("few_raw_samples_in_event")
            if int(complete_sample_mask.sum()) < cfg.minimum_raw_samples_approach_through_end:
                flags.append("few_raw_samples_approach_through_end")
                fatal = True
            if np.isfinite(maximum_map_error) and maximum_map_error > config.gps.maximum_map_error_m:
                flags.append("high_map_error")
                fatal = True
            if any(not np.isfinite(value) for value in (approach_speed, entry_speed, event_min, end_speed, event_time)):
                flags.append("incomplete_metric_window")
                fatal = True
            if np.isfinite(effective_resolution) and event_length < effective_resolution:
                flags.append("event_shorter_than_effective_gps_resolution")
            if gap_to_next < 0:
                flags.append("event_extent_overlaps_next_event")

            telemetry = _telemetry_metrics(
                lap_segment,
                approach_sample_mask,
                entry_sample_mask,
                event_sample_mask,
                config,
            )
            if "throttle_pct" not in lap_segment:
                flags.append("driver_demand_unknown")
            elif "brake_active" not in lap_segment:
                flags.append("brake_state_unknown")

            entry_mps = entry_speed / 3.6
            min_mps = event_min / 3.6
            end_mps = end_speed / 3.6
            group_id = str(feature["analysis_group_id"])
            rows.append(
                {
                    "case_id": f"{group_id}__lap_{int(lap_id):03d}",
                    "analysis_group_id": group_id,
                    "sequence": int(feature["sequence"]),
                    "event_name": feature["name"],
                    "source_members": feature.get("source_members", feature["name"]),
                    "analysis_role": feature.get("analysis_role", "track_event"),
                    "lap_id": int(lap_id),
                    "lap_analysis_valid": bool(lap_lookup.loc[lap_id, "analysis_valid"]),
                    "event_start_s_m": float(feature["event_start_s_m"]),
                    "event_end_s_m": float(feature["event_end_s_m"]),
                    "event_length_m": event_length,
                    "distance_to_next_event_m": gap_to_next,
                    "available_recovery_distance_m": available_recovery,
                    "approach_speed_kmh": approach_speed,
                    "entry_speed_kmh": entry_speed,
                    "approach_acceleration_mps2": approach_accel,
                    "event_min_speed_kmh": event_min,
                    "distance_to_min_m": distance_to_min,
                    "end_speed_kmh": end_speed,
                    "post_event_speed_kmh": post_event_speed,
                    "ordered_entry_to_min_change_kmh": entry_speed - event_min,
                    "signed_entry_to_end_change_kmh": end_speed - entry_speed,
                    "specific_ke_change_to_min_j_per_kg": 0.5 * (entry_mps**2 - min_mps**2),
                    "specific_ke_change_to_end_j_per_kg": 0.5 * (entry_mps**2 - end_mps**2),
                    "event_time_s": event_time,
                    "recovery_threshold_fraction": cfg.recovery_fraction,
                    "recovery_distance_m": recovery_distance,
                    "recovery_time_s": recovery_time,
                    "recovered_before_next_event": recovered_before_next,
                    "raw_samples_immediate_entry": int(entry_sample_mask.sum()),
                    "raw_samples_in_event": int(event_sample_mask.sum()),
                    "raw_samples_approach_through_end": int(complete_sample_mask.sum()),
                    "median_map_error_m": median_map_error,
                    "maximum_map_error_m": maximum_map_error,
                    "nominal_distance_per_sample_m": nominal_resolution,
                    "effective_gps_resolution_m": effective_resolution,
                    "aggregate_eligible": not fatal,
                    "quality_flags": ";".join(flags),
                    **telemetry,
                }
            )
    return pd.DataFrame(rows)


def summarize_event_passes(passes: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for group_id, group_all in passes.groupby("analysis_group_id", sort=False):
        group = group_all[group_all["aggregate_eligible"]]
        first = group_all.iloc[0]
        row: dict[str, object] = {
            "analysis_group_id": group_id,
            "sequence": int(first["sequence"]),
            "event_name": first["event_name"],
            "source_members": first["source_members"],
            "analysis_role": first["analysis_role"],
            "total_passes": int(len(group_all)),
            "valid_passes": int(len(group)),
            "event_start_s_m": float(first["event_start_s_m"]),
            "event_end_s_m": float(first["event_end_s_m"]),
            "event_length_m": float(first["event_length_m"]),
            "distance_to_next_event_m": float(first["distance_to_next_event_m"]),
            "fraction_recovered_before_next": float(group["recovered_before_next_event"].mean()) if len(group) else math.nan,
        }
        metrics = list(PASS_METRICS)
        metrics.extend(
            metric
            for metric in OPTIONAL_TELEMETRY_METRICS
            if metric in group and pd.to_numeric(group[metric], errors="coerce").notna().any()
        )
        for metric in metrics:
            values = pd.to_numeric(group[metric], errors="coerce").dropna()
            row[f"median_{metric}"] = float(values.median()) if len(values) else math.nan
            row[f"p25_{metric}"] = float(values.quantile(0.25)) if len(values) else math.nan
            row[f"p75_{metric}"] = float(values.quantile(0.75)) if len(values) else math.nan
            row[f"p10_{metric}"] = float(values.quantile(0.10)) if len(values) else math.nan
            row[f"p90_{metric}"] = float(values.quantile(0.90)) if len(values) else math.nan
        entry = pd.to_numeric(group["entry_speed_kmh"], errors="coerce").dropna()
        row["entry_speed_iqr_kmh"] = float(entry.quantile(0.75) - entry.quantile(0.25)) if len(entry) else math.nan
        row["entry_speed_cv"] = float(entry.std(ddof=1) / entry.mean()) if len(entry) > 1 and entry.mean() else math.nan
        rows.append(row)
    return pd.DataFrame(rows).sort_values("sequence").reset_index(drop=True)


def build_simulation_cases(passes: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "case_id",
        "analysis_group_id",
        "sequence",
        "event_name",
        "source_members",
        "lap_id",
        "event_start_s_m",
        "event_end_s_m",
        "event_length_m",
        "entry_speed_kmh",
        "approach_speed_kmh",
        "approach_acceleration_mps2",
        "event_min_speed_kmh",
        "end_speed_kmh",
        "event_time_s",
        "recovery_distance_m",
        "specific_ke_change_to_min_j_per_kg",
        "specific_ke_change_to_end_j_per_kg",
        "quality_flags",
    ]
    columns.extend(
        metric
        for metric in (*OPTIONAL_TELEMETRY_METRICS, *TELEMETRY_COVERAGE_METRICS)
        if metric in passes and pd.to_numeric(passes[metric], errors="coerce").notna().any()
    )
    cases = passes.loc[passes["aggregate_eligible"], columns].copy()
    cases.insert(10, "entry_speed_mps", cases["entry_speed_kmh"] / 3.6)
    cases.insert(11, "initial_condition_mode", "reset_at_measured_entry")
    return cases.reset_index(drop=True)


def build_speed_bin_summary(matched: pd.DataFrame, laps: pd.DataFrame, bin_width_kmh: float = 5.0) -> pd.DataFrame:
    valid_laps = set(laps.loc[laps["analysis_valid"], "lap_id"].astype(int))
    data = matched[matched["lap_id"].isin(valid_laps)].copy()
    maximum = max(50.0, math.ceil(float(data["speed_analysis_kmh"].max()) / bin_width_kmh) * bin_width_kmh)
    edges = np.arange(0.0, maximum + bin_width_kmh, bin_width_kmh)
    if edges[-1] <= float(data["speed_analysis_kmh"].max()):
        edges = np.r_[edges, edges[-1] + bin_width_kmh]
    data["speed_bin"] = pd.cut(data["speed_analysis_kmh"], bins=edges, right=False, include_lowest=True)
    data["sample_time_s"] = data["dt_s"].fillna(0.0).clip(lower=0.0)
    per_lap = (
        data.groupby(["lap_id", "speed_bin"], observed=False)
        .agg(time_s=("sample_time_s", "sum"), distance_m=("speed_step_m", "sum"), sample_count=("speed_analysis_kmh", "size"))
        .reset_index()
    )
    rows = []
    for interval, group in per_lap.groupby("speed_bin", observed=False):
        rows.append(
            {
                "speed_bin_kmh": str(interval),
                "bin_start_kmh": float(interval.left),
                "bin_end_kmh": float(interval.right),
                "laps": int(group["lap_id"].nunique()),
                "median_time_per_lap_s": float(group["time_s"].median()),
                "p25_time_per_lap_s": float(group["time_s"].quantile(0.25)),
                "p75_time_per_lap_s": float(group["time_s"].quantile(0.75)),
                "median_distance_per_lap_m": float(group["distance_m"].median()),
                "p25_distance_per_lap_m": float(group["distance_m"].quantile(0.25)),
                "p75_distance_per_lap_m": float(group["distance_m"].quantile(0.75)),
            }
        )
    return pd.DataFrame(rows)


def _mask(x: np.ndarray, low: float, high: float, values: np.ndarray) -> np.ndarray:
    return (x >= low) & (x <= high) & np.isfinite(values)


def _median_between(values: np.ndarray, x: np.ndarray, low: float, high: float) -> float:
    selected = values[_mask(x, low, high, values)]
    return float(np.median(selected)) if len(selected) else math.nan


def _spatial_acceleration(values_kmh: np.ndarray, x_m: np.ndarray, low: float, high: float) -> float:
    selected = _mask(x_m, low, high, values_kmh)
    if selected.sum() < 3:
        return math.nan
    x = x_m[selected]
    v_squared = (values_kmh[selected] / 3.6) ** 2
    slope = np.polyfit(x, v_squared, 1)[0]
    return float(0.5 * slope)


def _travel_time(values_kmh: np.ndarray, x_m: np.ndarray, low: float, high: float) -> float:
    selected = _mask(x_m, low, high, values_kmh)
    if selected.sum() < 2 or high <= low:
        return math.nan
    x = x_m[selected]
    speed_mps = np.maximum(values_kmh[selected] / 3.6, 0.25)
    return float(np.trapezoid(1.0 / speed_mps, x))


def _telemetry_metrics(
    samples: pd.DataFrame,
    approach_mask: np.ndarray,
    entry_mask: np.ndarray,
    event_mask: np.ndarray,
    config: PipelineConfig,
) -> dict[str, float]:
    """Summarize optional timestamp-aligned channels over event zones."""

    cfg = config.metric
    result = {metric: math.nan for metric in (*OPTIONAL_TELEMETRY_METRICS, *TELEMETRY_COVERAGE_METRICS)}

    if "throttle_pct" in samples:
        approach_throttle = _numeric_zone(samples, "throttle_pct", approach_mask)
        entry_throttle = _numeric_zone(samples, "throttle_pct", entry_mask)
        event_throttle = _numeric_zone(samples, "throttle_pct", event_mask)
        result.update(
            {
                "approach_throttle_pct": _series_median(approach_throttle),
                "entry_throttle_pct": _series_median(entry_throttle),
                "event_throttle_pct": _series_median(event_throttle),
                "full_throttle_fraction_approach": _fraction_true(
                    approach_throttle >= cfg.full_throttle_threshold_pct,
                    approach_throttle,
                ),
                "full_throttle_fraction_event": _fraction_true(
                    event_throttle >= cfg.full_throttle_threshold_pct,
                    event_throttle,
                ),
                "throttle_sample_coverage_event": _coverage(samples, "throttle_pct", event_mask),
            }
        )

    if "brake_active" in samples:
        approach_brake = _numeric_zone(samples, "brake_active", approach_mask)
        event_brake = _numeric_zone(samples, "brake_active", event_mask)
        result.update(
            {
                "approach_brake_fraction": _fraction_true(
                    approach_brake >= cfg.brake_active_threshold,
                    approach_brake,
                ),
                "event_brake_fraction": _fraction_true(
                    event_brake >= cfg.brake_active_threshold,
                    event_brake,
                ),
                "brake_sample_coverage_event": _coverage(samples, "brake_active", event_mask),
            }
        )

    if "throttle_pct" in samples:
        throttle = pd.to_numeric(samples.loc[event_mask, "throttle_pct"], errors="coerce")
        valid = throttle.notna()
        positive_demand = throttle >= cfg.full_throttle_threshold_pct
        if "brake_active" in samples:
            brake = pd.to_numeric(samples.loc[event_mask, "brake_active"], errors="coerce")
            valid &= brake.notna()
            positive_demand &= brake < cfg.brake_active_threshold
        result["positive_driver_demand_fraction_event"] = (
            float(positive_demand[valid].mean()) if valid.any() else math.nan
        )

    for channel, entry_name, event_name, coverage_name in (
        ("engine_rpm", "entry_engine_rpm", "event_engine_rpm_median", "engine_rpm_sample_coverage_event"),
        ("primary_rpm", "entry_primary_rpm", "event_primary_rpm_median", "primary_rpm_sample_coverage_event"),
        ("secondary_rpm", "entry_secondary_rpm", "event_secondary_rpm_median", "secondary_rpm_sample_coverage_event"),
        ("cvt_ratio", "entry_cvt_ratio", "event_cvt_ratio_median", "cvt_ratio_sample_coverage_event"),
    ):
        if channel not in samples:
            continue
        result[entry_name] = _series_median(_numeric_zone(samples, channel, entry_mask))
        result[event_name] = _series_median(_numeric_zone(samples, channel, event_mask))
        result[coverage_name] = _coverage(samples, channel, event_mask)

    if "engine_rpm" in samples and cfg.power_band_min_rpm is not None:
        rpm = _numeric_zone(samples, "engine_rpm", event_mask)
        inside = (rpm >= cfg.power_band_min_rpm) & (rpm <= cfg.power_band_max_rpm)
        result["power_band_fraction_event"] = _fraction_true(inside, rpm)

    if "wheel_speed_kmh" in samples and "speed_analysis_kmh" in samples:
        wheel = pd.to_numeric(samples.loc[event_mask, "wheel_speed_kmh"], errors="coerce")
        gps_speed = pd.to_numeric(samples.loc[event_mask, "speed_analysis_kmh"], errors="coerce")
        valid = wheel.notna() & gps_speed.notna()
        if valid.any():
            slip = (wheel[valid] - gps_speed[valid]) / np.maximum(gps_speed[valid].abs(), 3.0)
            result["event_wheel_slip_proxy_median"] = float(slip.median())
            result["event_wheel_slip_fraction"] = float(
                (slip.abs() >= cfg.wheel_slip_ratio_threshold).mean()
            )
        result["wheel_speed_sample_coverage_event"] = _coverage(samples, "wheel_speed_kmh", event_mask)

    return result


def _numeric_zone(samples: pd.DataFrame, column: str, mask: np.ndarray) -> pd.Series:
    return pd.to_numeric(samples.loc[mask, column], errors="coerce").dropna()


def _series_median(values: pd.Series) -> float:
    return float(values.median()) if len(values) else math.nan


def _fraction_true(condition: pd.Series, measured: pd.Series) -> float:
    valid = measured.notna()
    return float(condition[valid].mean()) if valid.any() else math.nan


def _coverage(samples: pd.DataFrame, column: str, mask: np.ndarray) -> float:
    count = int(mask.sum())
    if count == 0:
        return math.nan
    return float(pd.to_numeric(samples.loc[mask, column], errors="coerce").notna().mean())
