from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .config import PipelineConfig
from .definitions import load_definition_csv
from .exports import export_analysis
from .gps_core import (
    Centreline,
    LocalFrame,
    build_analysis_features,
    build_centreline,
    build_lap_table,
    build_track_profile,
    detect_gate_crossings,
    load_and_clean_gps,
    map_match_laps,
    project_obstacles,
)
from .grouping import suggest_adjacent_grouping
from .metrics import (
    add_event_geometry,
    build_simulation_cases,
    build_speed_bin_summary,
    extract_event_passes,
    summarize_event_passes,
)
from .simulation import event_prediction_template, lap_prediction_template
from .telemetry import attach_optional_telemetry


@dataclass
class AnalysisResult:
    config: PipelineConfig
    allow_incomplete_definitions: bool
    cleaning: dict[str, object]
    definition_issues: pd.DataFrame
    laps: pd.DataFrame
    centreline: Centreline
    matched_gps: pd.DataFrame
    projected_definitions: pd.DataFrame
    analysis_features: pd.DataFrame
    track_profile: pd.DataFrame
    individual_passes: pd.DataFrame
    event_passes: pd.DataFrame
    event_summary: pd.DataFrame
    grouping_suggestions: pd.DataFrame
    speed_bins: pd.DataFrame
    simulation_cases: pd.DataFrame
    event_prediction_template: pd.DataFrame
    lap_prediction_template: pd.DataFrame


def run_analysis(
    gps_csv: Path,
    definition_csv: Path,
    output_dir: Path | None = None,
    *,
    config: PipelineConfig | None = None,
    allow_incomplete_definitions: bool = False,
) -> AnalysisResult:
    config = config or PipelineConfig()
    gps, cleaning = load_and_clean_gps(gps_csv, config.gps)
    gps, telemetry_channels = attach_optional_telemetry(gps, gps_csv)
    cleaning["optional_telemetry_channels"] = ";".join(telemetry_channels)
    definitions, definition_issues = load_definition_csv(
        definition_csv,
        allow_incomplete=allow_incomplete_definitions,
    )

    gate_match = definitions[
        definitions["name"].str.casefold() == config.gps.lap_gate_name.casefold()
    ]
    if gate_match.empty:
        raise ValueError(f"Lap gate {config.gps.lap_gate_name!r} was not found in the definition CSV")
    gate = gate_match.iloc[0]
    frame = LocalFrame(float(gps["lat"].median()), float(gps["lon"].median()))
    crossings = detect_gate_crossings(
        gps,
        frame,
        float(gate["latitude"]),
        float(gate["longitude"]),
        config.gps,
    )
    if len(crossings) < 3:
        raise ValueError(f"Only {len(crossings)} lap-gate visits were found; at least 3 are required")
    laps = build_lap_table(gps, crossings, config.gps)
    centreline = build_centreline(gps, laps, frame, config.gps)
    matched, laps = map_match_laps(gps, laps, centreline)
    projected = project_obstacles(definitions, centreline)

    individual_features = add_event_geometry(projected, centreline.length_m)
    individual_features["analysis_group_id"] = individual_features["sequence"].map(
        lambda sequence: f"DEF_{int(sequence):02d}"
    )
    grouped = build_analysis_features(projected, centreline.length_m)
    grouped = add_event_geometry(grouped, centreline.length_m)
    role_by_group = definitions.groupby("final_group_id")["analysis_role"].agg(
        lambda values: "track_event" if (values == "track_event").any() else "turn_context"
    )
    grouped["analysis_role"] = grouped["analysis_group_id"].map(role_by_group).fillna(
        grouped.get("analysis_role", "track_event")
    )

    track_profile, lap_profiles = build_track_profile(matched, laps, centreline, config.gps)
    sample_period = float(cleaning["median_sample_period_s"])
    individual_passes = extract_event_passes(
        matched,
        laps,
        individual_features,
        lap_profiles,
        centreline,
        config,
        sample_period,
    )
    event_passes = extract_event_passes(
        matched,
        laps,
        grouped,
        lap_profiles,
        centreline,
        config,
        sample_period,
    )
    event_summary = summarize_event_passes(event_passes, grouped)
    grouping = suggest_adjacent_grouping(individual_features, individual_passes, config)
    speed_bins = build_speed_bin_summary(matched, laps)
    cases = build_simulation_cases(event_passes)

    result = AnalysisResult(
        config=config,
        allow_incomplete_definitions=allow_incomplete_definitions,
        cleaning=cleaning,
        definition_issues=definition_issues,
        laps=laps,
        centreline=centreline,
        matched_gps=matched,
        projected_definitions=projected,
        analysis_features=grouped,
        track_profile=track_profile,
        individual_passes=individual_passes,
        event_passes=event_passes,
        event_summary=event_summary,
        grouping_suggestions=grouping,
        speed_bins=speed_bins,
        simulation_cases=cases,
        event_prediction_template=event_prediction_template(cases),
        lap_prediction_template=lap_prediction_template(track_profile),
    )
    if output_dir is not None:
        export_analysis(result, output_dir)
    return result
