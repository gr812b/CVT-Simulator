from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from .config import PipelineConfig
from .pipeline import AnalysisResult, run_analysis
from .signatures import SignatureResult, analyze_signatures_from_analysis


@dataclass
class FullWorkflowResult:
    analysis: AnalysisResult
    signatures: SignatureResult
    output_dir: Path


def run_full_workflow(
    gps_csv: Path,
    definition_csv: Path,
    output_dir: Path,
    *,
    config: PipelineConfig | None = None,
    allow_incomplete_definitions: bool = False,
) -> FullWorkflowResult:
    """Reproduce the complete measurement-to-simulator-validation workflow."""

    config = config or PipelineConfig()
    analysis_dir = output_dir / "analysis"
    signature_dir = output_dir / "signatures"
    analysis = run_analysis(
        gps_csv,
        definition_csv,
        analysis_dir,
        config=config,
        allow_incomplete_definitions=allow_incomplete_definitions,
    )
    signatures = analyze_signatures_from_analysis(
        analysis,
        output_dir=signature_dir,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    result = FullWorkflowResult(analysis=analysis, signatures=signatures, output_dir=output_dir)
    (output_dir / "FULL_RUN_REPORT.md").write_text(_full_run_report(result), encoding="utf-8")
    manifest = {
        "pipeline_version": "0.2.0",
        "gps_input": str(gps_csv.resolve()),
        "definition_input": str(definition_csv.resolve()),
        "provisional_definition_fallbacks_allowed": allow_incomplete_definitions,
        "config": config.as_dict(),
        "counts": {
            "clean_gps_rows": int(analysis.cleaning["output_rows"]),
            "complete_laps": int(len(analysis.laps)),
            "retained_laps": int(analysis.laps["analysis_valid"].sum()),
            "physical_definitions": int(len(analysis.projected_definitions)),
            "analysis_groups": int(len(analysis.analysis_features)),
            "event_passes": int(len(analysis.event_passes)),
            "eligible_event_passes": int(analysis.event_passes["aggregate_eligible"].sum()),
            "signature_counts": {
                key: int(value)
                for key, value in signatures.signatures["slowdown_signature"].value_counts().items()
            },
        },
        "primary_outputs": {
            "analysis_report": "analysis/RUN_REPORT.md",
            "event_metrics": "analysis/event_passes.csv",
            "event_summary": "analysis/event_summary.csv",
            "grouping_audit": "analysis/grouping_suggestions.csv",
            "simulation_cases": "analysis/sim_event_cases.csv",
            "lap_profile": "analysis/track_speed_profile.csv",
            "signature_report": "signatures/SIGNATURE_REPORT.md",
            "anchor_signatures": "signatures/anchor_slowdown_signatures.csv",
        },
    }
    (output_dir / "full_run_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def _full_run_report(result: FullWorkflowResult) -> str:
    analysis = result.analysis
    signature_counts = result.signatures.signatures["slowdown_signature"].value_counts()
    lines = [
        "# Complete Baja GPS-to-simulator validation run",
        "",
        "## Reproduced pipeline",
        "",
        "1. Strict obstacle-definition validation.",
        "2. GPS timestamp/coordinate/speed cleaning and lap segmentation.",
        "3. Reference centreline construction and ordered single-`s` map matching.",
        "4. Physical-feature projection and declared response grouping.",
        "5. Per-pass approach, entry, minimum, end, traversal, kinetic-state-change, and recovery metrics.",
        "6. Robust median/IQR/percentile event summaries and grouping identifiability audit.",
        "7. Uniform-anchor slowdown signatures relative to the whole-track baseline.",
        "8. Reset-at-entry event cases and continuous-lap templates for simulator validation.",
        "",
        "## Run counts",
        "",
        f"- Clean GPS rows: {analysis.cleaning['output_rows']}",
        f"- Complete laps detected: {len(analysis.laps)}",
        f"- Laps retained: {int(analysis.laps['analysis_valid'].sum())}",
        f"- Physical definitions: {len(analysis.projected_definitions)}",
        f"- Analysis groups: {len(analysis.analysis_features)}",
        f"- Aggregate-eligible event passes: {int(analysis.event_passes['aggregate_eligible'].sum())} of {len(analysis.event_passes)}",
        f"- Slowdown signatures: {int(signature_counts.get('STRONG', 0))} strong, {int(signature_counts.get('MODERATE', 0))} moderate, {int(signature_counts.get('WEAK', 0))} weak",
        "",
        "## Interpretation boundary",
        "",
        "These outputs measure repeatable vehicle speed states and provide validation targets. They do not identify absolute terrain-energy loss, braking causation, grade work, or tire slip from GPS alone. Use paired candidate comparisons and uncertainty sweeps.",
    ]
    return "\n".join(lines) + "\n"
