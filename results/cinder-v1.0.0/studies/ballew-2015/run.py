"""Re-run the Ballew (2015) model-to-model benchmark against cinder-cvt==1.0.0."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np

import cinder
from cinder.contracts import (
    project_assembly_validation,
    project_simulation_result,
    validate_assembly,
)

from benchmark.constants import PUBLISHED, resolved_parameter_document
from benchmark.metrics import (
    compute_error_metrics,
    historical_regression,
    metric_document,
    plot_protocol,
    write_comparison_csv,
)
from benchmark.reference import (
    REFERENCE_FILES,
    build_reference_ratio,
    load_series,
    materialize_reference_data,
    reference_hash_document,
)
from migrate_legacy import ensure_reference_assets

from benchmark.simulation import (
    build_closed_loop_setup,
    build_force_replay_setup,
    controller_force_for_sample,
    run_setup,
    sample_dense,
)

STUDY_ROOT = Path(__file__).resolve().parent
RELEASE_ROOT = STUDY_ROOT.parents[1]
VERIFY = RELEASE_ROOT / "verify_environment.py"
STUDY_FILE = STUDY_ROOT / "study.json"
ARTIFACTS_ROOT = STUDY_ROOT / "artifacts"
ARTIFACTS = ARTIFACTS_ROOT / "rerun-v1.0.0"
EXPECTED_CINDER_VERSION = "1.0.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--protocol",
        choices=("both", "force-replay", "closed-loop"),
        default="both",
    )
    parser.add_argument("--no-plots", action="store_true")
    parser.add_argument("--keep-artifacts", action="store_true")
    parser.add_argument("--rtol", type=float)
    parser.add_argument("--atol", type=float)
    parser.add_argument("--max-step", type=float)
    parser.add_argument("--maximum-transitions", type=int)
    return parser.parse_args()


def _write_report_csv(payload: dict, path: Path) -> None:
    columns = payload["report_table"]["columns"]
    keys = [column["key"] for column in columns]
    values = [column["values"] for column in columns]
    row_count = payload["report_table"]["row_count"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(keys)
        for row in range(row_count):
            writer.writerow([column[row] for column in values])


def _validate_setup(setup, output_dir: Path) -> None:
    report = validate_assembly(setup.assembly)
    projected = project_assembly_validation(report)
    (output_dir / "assembly_validation.json").write_text(
        json.dumps(projected, indent=2) + "\n", encoding="utf-8"
    )
    if not report.is_valid:
        messages = [
            f"[{finding.severity}] {finding.document_path or '/'}: {finding.message}"
            for finding in report.findings
        ]
        raise RuntimeError("Ballew assembly failed CINDER validation:\n" + "\n".join(messages))


def _solver_for(spec: dict, protocol: str, args: argparse.Namespace) -> dict[str, object]:
    base = dict(spec["protocols"][protocol]["solver"])
    if args.rtol is not None:
        base["relative_tolerance"] = args.rtol
    if args.atol is not None:
        base["absolute_tolerance"] = args.atol
    if args.max_step is not None:
        base["max_step_s"] = args.max_step
    if args.maximum_transitions is not None:
        base["maximum_transitions"] = args.maximum_transitions
    return base


def _run_protocol(
    *,
    protocol: str,
    spec: dict,
    reference_dir: Path,
    make_plots: bool,
    args: argparse.Namespace,
) -> dict[str, object]:
    output_dir = ARTIFACTS / protocol
    output_dir.mkdir(parents=True, exist_ok=True)

    input_ref = load_series(
        reference_dir / "figure_41_input_rpm.csv", value_column="input_rpm"
    )
    output_ref = load_series(
        reference_dir / "figure_41_output_rpm.csv", value_column="output_rpm"
    )
    force_ref = load_series(
        reference_dir / "figure_45_primary_force.csv",
        value_column="primary_axial_force_n",
    )
    ratio_ref = build_reference_ratio(input_ref, output_ref)

    if protocol == "force_replay":
        setup = build_force_replay_setup(reference_dir / "figure_45_primary_force.csv")
    elif protocol == "closed_loop":
        setup = build_closed_loop_setup()
    else:
        raise ValueError(protocol)

    _validate_setup(setup, output_dir)
    solver = _solver_for(spec, protocol, args)
    result = run_setup(
        setup,
        relative_tolerance=float(solver["relative_tolerance"]),
        absolute_tolerance=float(solver["absolute_tolerance"]),
        max_step_s=float(solver["max_step_s"]),
        maximum_transitions=int(solver["maximum_transitions"]),
        report_step_s=float(solver["report_step_s"]),
        method=str(solver["method"]),
    )

    projected = project_simulation_result(result)
    (output_dir / "result.json").write_text(
        json.dumps(projected, indent=2) + "\n", encoding="utf-8"
    )
    _write_report_csv(projected, output_dir / "report.csv")

    base_payload: dict[str, object] = {
        "protocol": protocol,
        "completed": bool(result.completed),
        "termination_reason": str(result.termination_reason),
        "final_time_s": float(result.final_time),
        "segment_count": len(result.trace.segments),
        "transition_count": len(result.transitions),
        "solver": solver,
    }
    if not result.completed:
        (output_dir / "metrics.json").write_text(
            json.dumps(base_payload, indent=2) + "\n", encoding="utf-8"
        )
        return base_payload

    input_pred = sample_dense(setup, result, input_ref.time_s)
    output_pred = sample_dense(setup, result, output_ref.time_s)
    ratio_pred = sample_dense(setup, result, ratio_ref.time_s)

    metrics: dict[str, object] = {
        "primary_rpm": metric_document(
            compute_error_metrics(reference=input_ref.value, predicted=input_pred.primary_rpm)
        ),
        "secondary_rpm": metric_document(
            compute_error_metrics(
                reference=output_ref.value, predicted=output_pred.secondary_rpm
            )
        ),
        "speed_ratio": metric_document(
            compute_error_metrics(reference=ratio_ref.value, predicted=ratio_pred.speed_ratio)
        ),
    }

    write_comparison_csv(
        output_dir / "primary_rpm_comparison.csv",
        time_s=input_ref.time_s,
        reference=input_ref.value,
        predicted=input_pred.primary_rpm,
        reference_name="ballew_primary_rpm",
        predicted_name="cinder_primary_rpm",
    )
    write_comparison_csv(
        output_dir / "secondary_rpm_comparison.csv",
        time_s=output_ref.time_s,
        reference=output_ref.value,
        predicted=output_pred.secondary_rpm,
        reference_name="ballew_secondary_rpm",
        predicted_name="cinder_secondary_rpm",
    )
    write_comparison_csv(
        output_dir / "speed_ratio_comparison.csv",
        time_s=ratio_ref.time_s,
        reference=ratio_ref.value,
        predicted=ratio_pred.speed_ratio,
        reference_name="ballew_speed_ratio",
        predicted_name="cinder_speed_ratio",
    )

    force_pred = None
    if protocol == "closed_loop":
        force_times = force_ref.time_s[1:]
        force_sample = sample_dense(setup, result, force_times)
        force_pred = controller_force_for_sample(setup, force_sample)
        metrics["primary_force"] = metric_document(
            compute_error_metrics(reference=force_ref.value[1:], predicted=force_pred)
        )
        write_comparison_csv(
            output_dir / "primary_force_comparison.csv",
            time_s=force_times,
            reference=force_ref.value[1:],
            predicted=force_pred,
            reference_name="ballew_primary_force_n",
            predicted_name="cinder_primary_force_n",
        )
        base_payload["mean_cinder_primary_force_n"] = float(np.mean(force_pred))
        base_payload["mean_ballew_primary_force_n"] = float(np.mean(force_ref.value[1:]))

    base_payload["metrics"] = metrics
    base_payload["historical_v1_0_0_regression"] = historical_regression(
        protocol=protocol,
        metrics=metrics,
        transition_count=len(result.transitions),
    )
    (output_dir / "metrics.json").write_text(
        json.dumps(base_payload, indent=2) + "\n", encoding="utf-8"
    )

    if make_plots:
        plot_protocol(
            output_dir / "comparison.png",
            protocol_name=(
                "Ballew 2015 force replay"
                if protocol == "force_replay"
                else "Ballew 2015 reconstructed closed loop"
            ),
            input_ref=input_ref,
            input_pred=input_pred.primary_rpm,
            output_ref=output_ref,
            output_pred=output_pred.secondary_rpm,
            ratio_ref=ratio_ref,
            ratio_pred=ratio_pred.speed_ratio,
            force_ref=force_ref,
            force_pred=force_pred,
        )
    return base_payload


def _write_headline(results: dict[str, dict[str, object]]) -> None:
    rows = []
    for protocol, payload in results.items():
        metrics = payload.get("metrics", {})
        row = {
            "protocol": protocol,
            "completed": payload["completed"],
            "primary_rpm_rmse": metrics.get("primary_rpm", {}).get(
                "root_mean_square_error"
            ),
            "secondary_rpm_rmse": metrics.get("secondary_rpm", {}).get(
                "root_mean_square_error"
            ),
            "speed_ratio_rmse": metrics.get("speed_ratio", {}).get(
                "root_mean_square_error"
            ),
            "primary_force_rmse_n": metrics.get("primary_force", {}).get(
                "root_mean_square_error"
            ),
            "transition_count": payload.get("transition_count"),
        }
        rows.append(row)
    with (ARTIFACTS / "headline_metrics.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "cinder_version": cinder.__version__,
        "results": results,
    }
    (ARTIFACTS / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "# Ballew 2015 rerun summary",
        "",
        f"CINDER: `{cinder.__version__}`",
        "",
        "| Protocol | Primary RPM RMSE | Secondary RPM RMSE | Ratio RMSE | Force RMSE |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        def fmt(value, suffix=""):
            return "—" if value is None else f"{float(value):.6g}{suffix}"
        lines.append(
            f"| {row['protocol']} | {fmt(row['primary_rpm_rmse'], ' rpm')} | "
            f"{fmt(row['secondary_rpm_rmse'], ' rpm')} | {fmt(row['speed_ratio_rmse'])} | "
            f"{fmt(row['primary_force_rmse_n'], ' N')} |"
        )
    lines.extend(
        [
            "",
            "Historical v1.0.0 values are stored in each protocol's `metrics.json` as a regression reference.",
            "A nonzero raw transition-count delta is not by itself a physics regression because zero-crossing bookkeeping is tolerance-sensitive.",
        ]
    )
    (ARTIFACTS / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    subprocess.run([sys.executable, str(VERIFY)], check=True)
    if cinder.__version__ != EXPECTED_CINDER_VERSION:
        raise SystemExit(
            f"Expected CINDER {EXPECTED_CINDER_VERSION}, found {cinder.__version__}."
        )

    spec = json.loads(STUDY_FILE.read_text(encoding="utf-8"))
    ensure_reference_assets()
    reference_dir = materialize_reference_data(study_root=STUDY_ROOT)

    if ARTIFACTS.exists() and not args.keep_artifacts:
        shutil.rmtree(ARTIFACTS)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    resolved = {
        "study": spec,
        "cinder_version": cinder.__version__,
        "cinder_module_path": str(Path(cinder.__file__).resolve()),
        "parameters": resolved_parameter_document(),
        "reference_files": reference_hash_document(reference_dir),
        "reference_runtime_directory": str(reference_dir.resolve()),
    }
    (ARTIFACTS / "resolved_study.json").write_text(
        json.dumps(resolved, indent=2) + "\n", encoding="utf-8"
    )

    protocols = (
        ("force_replay", "closed_loop")
        if args.protocol == "both"
        else (("force_replay",) if args.protocol == "force-replay" else ("closed_loop",))
    )
    results: dict[str, dict[str, object]] = {}
    for protocol in protocols:
        print(f"Running {protocol}...")
        results[protocol] = _run_protocol(
            protocol=protocol,
            spec=spec,
            reference_dir=reference_dir,
            make_plots=not args.no_plots,
            args=args,
        )
        print(
            f"  completed={results[protocol]['completed']} "
            f"transitions={results[protocol]['transition_count']}"
        )

    _write_headline(results)
    print(f"Artifacts: {ARTIFACTS}")
    return 0 if all(bool(result["completed"]) for result in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
