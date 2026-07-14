from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .config import PipelineConfig, SignatureConfig
from .gps_core import build_track_profile
from .metrics import add_event_geometry, extract_event_passes
from .pipeline import AnalysisResult, run_analysis


SIGNATURE_ORDER = ("STRONG", "MODERATE", "WEAK", "INSUFFICIENT_LAPS")
SIGNATURE_COLORS = {
    "STRONG": "#2E7D32",
    "MODERATE": "#E6A700",
    "WEAK": "#C75B12",
    "INSUFFICIENT_LAPS": "#757575",
}


@dataclass
class SignatureResult:
    analysis: AnalysisResult
    anchor_passes: pd.DataFrame
    signatures: pd.DataFrame
    signature_summary: pd.DataFrame
    track_baseline: pd.DataFrame
    run_summary: pd.DataFrame


def run_signature_analysis(
    gps_csv: Path,
    definition_csv: Path,
    output_dir: Path | None = None,
    *,
    config: PipelineConfig | None = None,
    allow_incomplete_definitions: bool = False,
) -> SignatureResult:
    """Evaluate repeatable local slowdown evidence at every physical anchor.

    Every definition uses the same local point window for this diagnostic.
    Physical interval lengths and declared response groups therefore cannot
    inflate or merge the location signature.
    """

    config = config or PipelineConfig()
    analysis = run_analysis(
        gps_csv,
        definition_csv,
        config=config,
        allow_incomplete_definitions=allow_incomplete_definitions,
    )
    return analyze_signatures_from_analysis(analysis, output_dir=output_dir)


def analyze_signatures_from_analysis(
    analysis: AnalysisResult,
    *,
    output_dir: Path | None = None,
) -> SignatureResult:
    """Build anchor signatures from an already completed core analysis."""

    config = analysis.config
    track_profile, lap_profiles = build_track_profile(
        analysis.matched_gps,
        analysis.laps,
        analysis.centreline,
        config.gps,
    )
    anchor_features = _anchor_features(
        analysis.projected_definitions,
        analysis.centreline.length_m,
        config.signature.local_half_window_m,
    )
    anchor_passes = extract_event_passes(
        analysis.matched_gps,
        analysis.laps,
        anchor_features,
        lap_profiles,
        analysis.centreline,
        config,
        float(analysis.cleaning["median_sample_period_s"]),
    )
    baseline = build_track_slowdown_baseline(
        track_profile,
        analysis.centreline.length_m,
        config,
    )
    signatures = summarize_anchor_signatures(
        anchor_passes,
        anchor_features,
        baseline["track_slowdown_kmh"].to_numpy(float),
        config.signature,
    )
    summary = summarize_signature_classes(signatures)
    run_summary = build_signature_run_summary(analysis, signatures)
    result = SignatureResult(
        analysis=analysis,
        anchor_passes=anchor_passes,
        signatures=signatures,
        signature_summary=summary,
        track_baseline=baseline,
        run_summary=run_summary,
    )
    if output_dir is not None:
        export_signature_analysis(result, output_dir)
    return result


def _anchor_features(
    projected_definitions: pd.DataFrame,
    track_length_m: float,
    half_window_m: float,
) -> pd.DataFrame:
    features = projected_definitions.sort_values("sequence").reset_index(drop=True).copy()
    features["definition_kind"] = features["kind"]
    features["physical_group_id"] = features["final_group_id"]
    features["kind"] = "point"
    features["feature_start_rel_m"] = -half_window_m
    features["feature_end_rel_m"] = half_window_m
    features["source_members"] = features["name"]
    features["analysis_group_id"] = features["sequence"].map(
        lambda sequence: f"ANCHOR_{int(sequence):02d}"
    )
    return add_event_geometry(features, track_length_m)


def build_track_slowdown_baseline(
    track_profile: pd.DataFrame,
    track_length_m: float,
    config: PipelineConfig,
) -> pd.DataFrame:
    """Apply the anchor statistic at regular points around the entire lap."""

    track = track_profile.sort_values("s_m")
    s = track["s_m"].to_numpy(float)
    speed = track["median_speed_kmh"].to_numpy(float)
    s_augmented = np.r_[s - track_length_m, s, s + track_length_m]
    speed_augmented = np.r_[speed, speed, speed]
    anchors = np.arange(0.0, track_length_m, config.signature.baseline_step_m)
    relative = np.arange(
        -config.metric.approach_distance_m,
        config.signature.local_half_window_m + config.signature.interpolation_step_m / 2,
        config.signature.interpolation_step_m,
    )
    approach_mask = (
        (relative >= -config.metric.approach_distance_m)
        & (relative <= -config.metric.approach_gap_m)
    )
    local_mask = (
        (relative >= -config.signature.local_half_window_m)
        & (relative <= config.signature.local_half_window_m)
    )
    rows = []
    for anchor in anchors:
        values = np.interp(anchor + relative, s_augmented, speed_augmented)
        approach = float(np.median(values[approach_mask]))
        local_minimum = float(np.min(values[local_mask]))
        rows.append(
            {
                "s_m": float(anchor),
                "approach_speed_kmh": approach,
                "local_min_speed_kmh": local_minimum,
                "track_slowdown_kmh": approach - local_minimum,
            }
        )
    return pd.DataFrame(rows)


def summarize_anchor_signatures(
    passes: pd.DataFrame,
    features: pd.DataFrame,
    track_baseline: np.ndarray,
    config: SignatureConfig,
) -> pd.DataFrame:
    feature_lookup = features.set_index("sequence")
    rows = []
    for sequence, all_passes in passes.groupby("sequence", sort=True):
        valid = all_passes[all_passes["aggregate_eligible"]].copy()
        slowdown = valid["approach_speed_kmh"] - valid["event_min_speed_kmh"]
        median_slowdown = float(slowdown.median()) if len(slowdown) else math.nan
        fraction = (
            float((slowdown > config.slowdown_event_threshold_kmh).mean())
            if len(slowdown)
            else math.nan
        )
        percentile = (
            float(100.0 * np.mean(track_baseline <= median_slowdown))
            if np.isfinite(median_slowdown)
            else math.nan
        )
        signature = classify_signature(
            valid_laps=len(valid),
            track_percentile=percentile,
            slowdown_lap_fraction=fraction,
            config=config,
        )
        feature = feature_lookup.loc[int(sequence)]
        rows.append(
            {
                "sequence": int(sequence),
                "name": feature["name"],
                "analysis_role": feature["analysis_role"],
                "definition_kind": feature["definition_kind"],
                "physical_group_id": feature["physical_group_id"],
                "anchor_s_m": float(feature["anchor_s_m"]),
                "anchor_projection_error_m": float(feature["anchor_projection_error_m"]),
                "valid_laps": int(len(valid)),
                "median_approach_to_local_min_kmh": median_slowdown,
                "p25_approach_to_local_min_kmh": float(slowdown.quantile(0.25)) if len(slowdown) else math.nan,
                "p75_approach_to_local_min_kmh": float(slowdown.quantile(0.75)) if len(slowdown) else math.nan,
                "fraction_laps_slowdown_gt_threshold": fraction,
                "slowdown_threshold_kmh": config.slowdown_event_threshold_kmh,
                "track_slowdown_percentile": percentile,
                "slowdown_signature": signature,
                "interpretation": _interpretation(signature),
            }
        )
    return pd.DataFrame(rows).sort_values("sequence").reset_index(drop=True)


def classify_signature(
    *,
    valid_laps: int,
    track_percentile: float,
    slowdown_lap_fraction: float,
    config: SignatureConfig,
) -> str:
    if valid_laps < config.minimum_valid_laps:
        return "INSUFFICIENT_LAPS"
    if (
        track_percentile >= config.strong_track_percentile
        and slowdown_lap_fraction >= config.strong_lap_fraction
    ):
        return "STRONG"
    if (
        track_percentile >= config.moderate_track_percentile
        or slowdown_lap_fraction >= config.moderate_lap_fraction
    ):
        return "MODERATE"
    return "WEAK"


def summarize_signature_classes(signatures: pd.DataFrame) -> pd.DataFrame:
    rows = []
    total = len(signatures)
    for label in SIGNATURE_ORDER:
        group = signatures[signatures["slowdown_signature"] == label]
        if group.empty:
            continue
        rows.append(
            {
                "slowdown_signature": label,
                "anchor_count": int(len(group)),
                "fraction_of_anchors": float(len(group) / total) if total else math.nan,
                "median_slowdown_kmh": float(group["median_approach_to_local_min_kmh"].median()),
                "median_lap_fraction_above_threshold": float(
                    group["fraction_laps_slowdown_gt_threshold"].median()
                ),
                "median_track_percentile": float(group["track_slowdown_percentile"].median()),
                "members": "; ".join(group["name"].astype(str)),
            }
        )
    return pd.DataFrame(rows)


def build_signature_run_summary(
    analysis: AnalysisResult,
    signatures: pd.DataFrame,
) -> pd.DataFrame:
    counts = signatures["slowdown_signature"].value_counts()
    facts = {
        "physical_anchors": int(len(signatures)),
        "retained_laps": int(analysis.laps["analysis_valid"].sum()),
        "track_length_m": float(analysis.centreline.length_m),
        "course_order_monotonic": bool(
            analysis.projected_definitions["anchor_s_m"].is_monotonic_increasing
        ),
        "maximum_anchor_projection_error_m": float(
            signatures["anchor_projection_error_m"].max()
        ),
        "strong_count": int(counts.get("STRONG", 0)),
        "moderate_count": int(counts.get("MODERATE", 0)),
        "weak_count": int(counts.get("WEAK", 0)),
        "insufficient_laps_count": int(counts.get("INSUFFICIENT_LAPS", 0)),
    }
    return pd.DataFrame({"check": list(facts), "value": list(facts.values())})


def export_signature_analysis(result: SignatureResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    result.anchor_passes.to_csv(output_dir / "anchor_signature_passes.csv", index=False)
    result.signatures.to_csv(output_dir / "anchor_slowdown_signatures.csv", index=False)
    result.signature_summary.to_csv(output_dir / "signature_class_summary.csv", index=False)
    result.track_baseline.to_csv(output_dir / "track_slowdown_baseline.csv", index=False)
    result.run_summary.to_csv(output_dir / "signature_run_summary.csv", index=False)
    _signature_plot(result.signatures, output_dir / "anchor_slowdown_signatures.png")
    (output_dir / "SIGNATURE_REPORT.md").write_text(
        _signature_report(result),
        encoding="utf-8",
    )


def _signature_plot(signatures: pd.DataFrame, path: Path) -> None:
    figure, axis = plt.subplots(figsize=(14, 6))
    x = signatures["sequence"].to_numpy(int)
    y = signatures["median_approach_to_local_min_kmh"].to_numpy(float)
    colors = [SIGNATURE_COLORS[value] for value in signatures["slowdown_signature"]]
    axis.bar(x, y, color=colors, width=0.8)
    axis.axhline(0.0, color="#333333", linewidth=0.8)
    axis.set_xlabel("Physical feature sequence")
    axis.set_ylabel("Median approach-to-local-min change [km/h]")
    axis.set_title("Repeatable local slowdown signature by supplied anchor")
    axis.grid(axis="y", alpha=0.2)
    handles = [
        plt.Rectangle((0, 0), 1, 1, color=SIGNATURE_COLORS[label], label=label.title())
        for label in SIGNATURE_ORDER
        if label in set(signatures["slowdown_signature"])
    ]
    axis.legend(handles=handles, loc="best")
    figure.tight_layout()
    figure.savefig(path, dpi=170)
    plt.close(figure)


def _signature_report(result: SignatureResult) -> str:
    lines = [
        "# Anchor slowdown-signature verification",
        "",
        "This diagnostic compares the repeatable local slowdown at every supplied anchor with the same statistic evaluated around the full track.",
        "",
        "## Results",
        "",
    ]
    for _, row in result.signature_summary.iterrows():
        lines.append(
            f"- **{row['slowdown_signature'].title()}**: {int(row['anchor_count'])} "
            f"({100 * float(row['fraction_of_anchors']):.1f}%) — {row['members']}"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "A signature measures repeatable speed-state structure near an anchor. It does not prove that the named obstacle caused the slowdown. Driver braking, turns, grade, surface, and adjacent features remain mixed when throttle, brake, elevation, and higher-rate telemetry are unavailable.",
            "",
            "Use strong and moderate anchors as evidence for entry-speed distributions and relative simulator scenarios. Treat weak anchors as review priorities or non-slowdown features, not automatic coordinate failures.",
        ]
    )
    return "\n".join(lines) + "\n"


def _interpretation(signature: str) -> str:
    if signature == "STRONG":
        return "Repeatable unusually strong local slowdown evidence"
    if signature == "MODERATE":
        return "Some repeatable local slowdown evidence"
    if signature == "WEAK":
        return "Weak/no local slowdown evidence; review but do not automatically reject"
    return "Too few eligible laps for classification"
