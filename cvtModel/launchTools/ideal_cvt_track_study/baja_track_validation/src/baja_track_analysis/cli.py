from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

from .config import PipelineConfig
from .definitions import DefinitionValidationError, load_definition_csv
from .pipeline import run_analysis
from .simulation import (
    compare_event_predictions,
    compare_lap_profile,
    compare_profile_event_entries,
)
from .signatures import run_signature_analysis
from .workflow import run_full_workflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="baja-track",
        description="Single-s GPS analysis and CVT-simulator validation targets",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-definitions", help="check that all required FILL cells were resolved")
    validate.add_argument("definitions", type=Path)

    analyze = subparsers.add_parser("analyze", help="run the complete GPS/event analysis")
    analyze.add_argument("--gps", required=True, type=Path)
    analyze.add_argument("--definitions", required=True, type=Path)
    analyze.add_argument("--output", required=True, type=Path)
    analyze.add_argument("--config", type=Path)
    analyze.add_argument(
        "--allow-incomplete-definitions",
        action="store_true",
        help="development only: run with explicit warnings and fallback feature extents/grouping",
    )

    signatures = subparsers.add_parser(
        "verify-signatures",
        help="compare repeatable slowdown at every physical anchor with the whole-track baseline",
    )
    signatures.add_argument("--gps", required=True, type=Path)
    signatures.add_argument("--definitions", required=True, type=Path)
    signatures.add_argument("--output", required=True, type=Path)
    signatures.add_argument("--config", type=Path)
    signatures.add_argument(
        "--allow-incomplete-definitions",
        action="store_true",
        help="development only: allow explicitly flagged definition fallbacks",
    )

    full_run = subparsers.add_parser(
        "full-run",
        help="reproduce the complete cleaning, metrics, signature, grouping, and simulator-export workflow",
    )
    full_run.add_argument("--gps", required=True, type=Path)
    full_run.add_argument("--definitions", required=True, type=Path)
    full_run.add_argument("--output", required=True, type=Path)
    full_run.add_argument("--config", type=Path)
    full_run.add_argument(
        "--allow-incomplete-definitions",
        action="store_true",
        help="development only: allow explicitly flagged definition fallbacks",
    )

    compare_events = subparsers.add_parser("compare-events", help="compare reset-at-entry simulation cases with observed targets")
    compare_events.add_argument("--observed", required=True, type=Path, help="sim_event_cases.csv")
    compare_events.add_argument("--predictions", required=True, type=Path)
    compare_events.add_argument("--output", required=True, type=Path)

    compare_lap = subparsers.add_parser("compare-lap", help="compare a simulated full-lap speed profile with the observed envelope")
    compare_lap.add_argument("--observed-profile", required=True, type=Path)
    compare_lap.add_argument("--predictions", required=True, type=Path)
    compare_lap.add_argument("--event-summary", type=Path)
    compare_lap.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate-definitions":
            definitions, issues = load_definition_csv(args.definitions)
            warning_count = int((issues["severity"] == "warning").sum()) if not issues.empty else 0
            groups = definitions["final_group_id"].nunique()
            print(f"Definition CSV is complete: {len(definitions)} rows, {groups} final groups, {warning_count} warnings.")
            return 0

        if args.command == "analyze":
            config = PipelineConfig.from_toml(args.config)
            result = run_analysis(
                args.gps,
                args.definitions,
                args.output,
                config=config,
                allow_incomplete_definitions=args.allow_incomplete_definitions,
            )
            print(f"Completed: {args.output.resolve()}")
            print(
                f"Detected {len(result.laps)} complete laps; retained "
                f"{int(result.laps['analysis_valid'].sum())}."
            )
            print(
                f"Resolved {len(result.projected_definitions)} physical rows into "
                f"{len(result.analysis_features)} analysis groups."
            )
            print(
                f"Wrote {len(result.event_passes)} event/pass rows; "
                f"{int(result.event_passes['aggregate_eligible'].sum())} are aggregate-eligible."
            )
            return 0

        if args.command == "compare-events":
            observed = pd.read_csv(args.observed)
            predictions = pd.read_csv(args.predictions)
            cases, summary = compare_event_predictions(observed, predictions)
            args.output.mkdir(parents=True, exist_ok=True)
            cases.to_csv(args.output / "event_case_errors.csv", index=False)
            summary.to_csv(args.output / "event_comparison_summary.csv", index=False)
            print(f"Compared {len(cases)} event cases; results: {args.output.resolve()}")
            return 0

        if args.command == "full-run":
            config = PipelineConfig.from_toml(args.config)
            result = run_full_workflow(
                args.gps,
                args.definitions,
                args.output,
                config=config,
                allow_incomplete_definitions=args.allow_incomplete_definitions,
            )
            counts = result.signatures.signatures["slowdown_signature"].value_counts()
            print(f"Completed full workflow: {args.output.resolve()}")
            print(
                f"Retained {int(result.analysis.laps['analysis_valid'].sum())} laps; "
                f"wrote {int(result.analysis.event_passes['aggregate_eligible'].sum())} eligible event cases; "
                f"signatures = {int(counts.get('STRONG', 0))}/"
                f"{int(counts.get('MODERATE', 0))}/"
                f"{int(counts.get('WEAK', 0))} strong/moderate/weak."
            )
            return 0

        if args.command == "verify-signatures":
            config = PipelineConfig.from_toml(args.config)
            result = run_signature_analysis(
                args.gps,
                args.definitions,
                args.output,
                config=config,
                allow_incomplete_definitions=args.allow_incomplete_definitions,
            )
            counts = result.signatures["slowdown_signature"].value_counts()
            print(f"Completed: {args.output.resolve()}")
            print(
                f"Classified {len(result.signatures)} anchors across "
                f"{int(result.analysis.laps['analysis_valid'].sum())} retained laps: "
                f"{int(counts.get('STRONG', 0))} strong, "
                f"{int(counts.get('MODERATE', 0))} moderate, "
                f"{int(counts.get('WEAK', 0))} weak."
            )
            return 0

        if args.command == "compare-lap":
            observed = pd.read_csv(args.observed_profile)
            predictions = pd.read_csv(args.predictions)
            points, summary = compare_lap_profile(observed, predictions)
            args.output.mkdir(parents=True, exist_ok=True)
            points.to_csv(args.output / "lap_profile_errors.csv", index=False)
            summary.to_csv(args.output / "lap_comparison_summary.csv", index=False)
            if args.event_summary:
                entries = compare_profile_event_entries(pd.read_csv(args.event_summary), predictions)
                entries.to_csv(args.output / "lap_event_entry_errors.csv", index=False)
            print(f"Compared {len(summary)} simulated lap profile(s); results: {args.output.resolve()}")
            return 0

        raise AssertionError(f"Unhandled command: {args.command}")
    except DefinitionValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
