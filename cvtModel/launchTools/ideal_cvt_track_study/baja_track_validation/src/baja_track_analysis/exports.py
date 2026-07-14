from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from .gps_core import add_track_context, create_plots
from .telemetry import OPTIONAL_CHANNEL_ALIASES

if TYPE_CHECKING:
    from .pipeline import AnalysisResult


def export_analysis(result: "AnalysisResult", output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    centre_lat, centre_lon = result.centreline.frame.to_latlon(result.centreline.x, result.centreline.y)
    centreline = pd.DataFrame(
        {
            "s_m": result.centreline.s_nodes_m,
            "latitude": centre_lat,
            "longitude": centre_lon,
            "x_m": result.centreline.x,
            "y_m": result.centreline.y,
        }
    )
    track_profile = add_track_context(result.track_profile, result.centreline)
    cleaning = pd.DataFrame({"check": list(result.cleaning), "value": list(result.cleaning.values())})
    matched_columns = [
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
    matched_columns.extend(
        channel for channel in OPTIONAL_CHANNEL_ALIASES if channel in result.matched_gps
    )
    tables = {
        "cleaning_summary": cleaning,
        "definition_validation": result.definition_issues,
        "lap_summary": result.laps,
        "reference_centreline": centreline,
        "resolved_feature_definitions": result.projected_definitions,
        "analysis_groups": result.analysis_features,
        "track_speed_profile": track_profile,
        "speed_bin_summary": result.speed_bins,
        "event_passes": result.event_passes,
        "event_summary": result.event_summary,
        "individual_feature_passes": result.individual_passes,
        "grouping_suggestions": result.grouping_suggestions,
        "sim_event_cases": result.simulation_cases,
        "sim_event_predictions_template": result.event_prediction_template,
        "sim_lap_profile_predictions_template": result.lap_prediction_template,
        "map_matched_gps": result.matched_gps[matched_columns],
    }
    for name, table in tables.items():
        table.to_csv(output_dir / f"{name}.csv", index=False)

    if result.config.write_excel:
        with pd.ExcelWriter(output_dir / "track_validation_results.xlsx", engine="openpyxl") as writer:
            workbook_tables = {
                "Cleaning": cleaning,
                "Definition QA": result.definition_issues,
                "Laps": result.laps,
                "Events": result.event_summary,
                "Event Passes": result.event_passes,
                "Grouping QA": result.grouping_suggestions,
                "Simulation Cases": result.simulation_cases,
                "Track Profile": track_profile,
                "Speed Bins": result.speed_bins,
                "Resolved Definitions": result.projected_definitions,
            }
            for sheet_name, table in workbook_tables.items():
                table.to_excel(writer, sheet_name=sheet_name[:31], index=False)

    if result.config.write_plots:
        create_plots(
            output_dir,
            result.matched_gps,
            result.laps,
            result.centreline,
            result.analysis_features,
            result.track_profile,
        )

    report = _run_report(result)
    (output_dir / "RUN_REPORT.md").write_text(report, encoding="utf-8")
    manifest = {
        "pipeline_version": "0.2.0",
        "provisional_definition_fallbacks_allowed": result.allow_incomplete_definitions,
        "config": result.config.as_dict(),
        "counts": {
            "clean_gps_rows": int(result.cleaning["output_rows"]),
            "detected_laps": int(len(result.laps)),
            "valid_laps": int(result.laps["analysis_valid"].sum()),
            "physical_definition_rows": int(len(result.projected_definitions)),
            "analysis_groups": int(len(result.analysis_features)),
            "event_passes": int(len(result.event_passes)),
            "valid_event_passes": int(result.event_passes["aggregate_eligible"].sum()),
        },
        "files": sorted(path.name for path in output_dir.iterdir() if path.is_file()),
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _run_report(result: "AnalysisResult") -> str:
    definition_warnings = len(result.definition_issues[result.definition_issues["severity"] == "warning"]) if not result.definition_issues.empty else 0
    grouping_conflicts = int(result.grouping_suggestions["decision_consistency"].ne("CONSISTENT").sum()) if not result.grouping_suggestions.empty else 0
    eligible = result.event_passes[result.event_passes["aggregate_eligible"]]
    lines = [
        "# Baja track validation run",
        "",
        "## Run summary",
        "",
        f"- Clean GPS rows: {result.cleaning['output_rows']} of {result.cleaning['input_rows']}",
        f"- Complete laps detected: {len(result.laps)}",
        f"- Laps retained: {int(result.laps['analysis_valid'].sum())}",
        f"- Reference track length: {result.centreline.length_m:.1f} m",
        f"- Physical definition rows: {len(result.projected_definitions)}",
        f"- Final analysis groups: {len(result.analysis_features)}",
        f"- Aggregate-eligible event passes: {len(eligible)} of {len(result.event_passes)}",
        f"- Definition warnings: {definition_warnings}",
        f"- Grouping decisions requiring review: {grouping_conflicts}",
        f"- Optional telemetry channels: {result.cleaning.get('optional_telemetry_channels') or 'none'}",
        "",
        "## Primary validation artifacts",
        "",
        "- `sim_event_cases.csv`: reset-at-entry cases for obstacle-model validation.",
        "- `event_summary.csv`: median, IQR, and 10th–90th percentile observed targets.",
        "- `track_speed_profile.csv`: full-lap observed median and variability envelope.",
        "- `grouping_suggestions.csv`: whether adjacent responses are distinguishable in this GPS data.",
        "- `sim_event_predictions_template.csv`: fill with event-simulation predictions, then run `compare-events`.",
        "- `sim_lap_profile_predictions_template.csv`: fill with a simulated speed profile, then run `compare-lap`.",
        "",
        "## Interpretation rules",
        "",
        "- Entry speed is the immediate pre-group initial condition. Approach speed and approach acceleration remain separate diagnostics.",
        "- End speed is measured at the physical disturbance end. Post-event and recovery quantities are diagnostics, not manually defined exits.",
        "- Specific kinetic-energy change is observed vehicle-state change in J/kg. It is not obstacle energy loss.",
        "- Grouping combines only the GPS-observed response; individual physical subfeatures remain in `resolved_feature_definitions.csv`.",
        "- Event-by-event cases reset to measured entry conditions to isolate the obstacle model. Full-lap comparison propagates continuously and tests accumulated model/CVT behaviour.",
        "",
        "## Fundamental limitations",
        "",
        "Without optional telemetry, GPS alone cannot identify throttle demand, braking, grade work, wheel slip, CVT ratio, engine RPM, suspension work, soil deformation, or dissipated obstacle energy. Even with telemetry, grade, tire slip calibration, and terrain losses remain confounded. Use paired design comparisons and uncertainty sweeps; do not interpret these outputs as an absolute reconstruction of track forces or driver behaviour.",
    ]
    if result.allow_incomplete_definitions:
        lines.extend(
            [
                "",
                "> **Provisional run:** incomplete definition fallbacks were enabled. Do not use its event targets for final simulator validation.",
            ]
        )
    return "\n".join(lines) + "\n"
