"""Four-case numerical-refinement audit for the Ballew closed-loop benchmark."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import sys

import cinder
from cinder.contracts import validate_assembly
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from benchmark.metrics import compute_error_metrics  # noqa: E402
from benchmark.reference import (  # noqa: E402
    build_reference_ratio,
    load_series,
    validate_reference_data,
)
from benchmark.simulation import (  # noqa: E402
    build_closed_loop_setup,
    controller_force_for_sample,
    run_setup,
    sample_dense,
)

STUDY_ROOT = Path(__file__).resolve().parent
RELEASE_ROOT = STUDY_ROOT.parents[1]
VERIFY_ENVIRONMENT = RELEASE_ROOT / "verify_environment.py"
VERIFY_STUDY = STUDY_ROOT / "verify_study.py"
OUTPUT = STUDY_ROOT / "artifacts" / "convergence"
EXPECTED_CINDER_VERSION = "1.0.0"

CASES = (
    ("nominal_1p00ms", 1.0e-7, 1.0e-9, 1.0e-3),
    ("nominal_0p50ms", 1.0e-7, 1.0e-9, 0.5e-3),
    ("nominal_0p25ms", 1.0e-7, 1.0e-9, 0.25e-3),
    ("tight_0p50ms", 3.0e-8, 3.0e-10, 0.5e-3),
)


def _validate_setup(setup) -> None:
    report = validate_assembly(setup.assembly)
    if not report.is_valid:
        messages = [finding.message for finding in report.findings]
        raise RuntimeError(
            "Ballew closed-loop assembly failed validation:\n" + "\n".join(messages)
        )


def _plot(rows: list[dict[str, object]]) -> None:
    completed = [row for row in rows if bool(row["completed"])]
    if not completed:
        return
    labels = [str(row["label"]) for row in completed]
    x = list(range(len(labels)))

    fig, ax = plt.subplots(figsize=(9.0, 5.2))
    ax.plot(x, [float(row["primary_rpm_rmse"]) for row in completed], marker="o", label="Primary RPM RMSE")
    ax.plot(x, [float(row["secondary_rpm_rmse"]) for row in completed], marker="o", label="Secondary RPM RMSE")
    ax.set_xticks(x, labels, rotation=20, ha="right")
    ax.set_ylabel("RMSE [rpm]")
    ax.set_title("Ballew closed loop: numerical refinement of speed errors")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUTPUT / "convergence_speed_rmse.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9.0, 5.2))
    ax.plot(x, [float(row["speed_ratio_rmse"]) for row in completed], marker="o", label="Speed-ratio RMSE")
    ax.set_xticks(x, labels, rotation=20, ha="right")
    ax.set_ylabel("Ratio RMSE")
    ax.set_title("Ballew closed loop: numerical refinement of ratio error")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUTPUT / "convergence_ratio_rmse.png", dpi=180)
    plt.close(fig)


def main() -> int:
    subprocess.run([sys.executable, str(VERIFY_ENVIRONMENT)], check=True)
    subprocess.run([sys.executable, str(VERIFY_STUDY)], check=True)
    if cinder.__version__ != EXPECTED_CINDER_VERSION:
        raise SystemExit(
            f"Expected CINDER {EXPECTED_CINDER_VERSION}, found {cinder.__version__}."
        )

    reference = validate_reference_data(study_root=STUDY_ROOT)
    input_ref = load_series(
        reference / "figure_41_input_rpm.csv",
        value_column="input_rpm",
    )
    output_ref = load_series(
        reference / "figure_41_output_rpm.csv",
        value_column="output_rpm",
    )
    force_ref = load_series(
        reference / "figure_45_primary_force.csv",
        value_column="primary_axial_force_n",
    )
    ratio_ref = build_reference_ratio(input_ref, output_ref)

    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for label, rtol, atol, max_step in CASES:
        print(f"Running {label}...")
        setup = build_closed_loop_setup()
        _validate_setup(setup)
        result = run_setup(
            setup,
            relative_tolerance=rtol,
            absolute_tolerance=atol,
            max_step_s=max_step,
            maximum_transitions=2000,
            report_step_s=0.0002,
            method="LSODA",
        )
        row: dict[str, object] = {
            "label": label,
            "rtol": rtol,
            "atol": atol,
            "max_step_s": max_step,
            "completed": bool(result.completed),
            "termination_reason": str(result.termination_reason),
            "transition_count": len(result.transitions),
            "segment_count": len(result.trace.segments),
        }
        if result.completed:
            input_pred = sample_dense(setup, result, input_ref.time_s)
            output_pred = sample_dense(setup, result, output_ref.time_s)
            ratio_pred = sample_dense(setup, result, ratio_ref.time_s)
            force_sample = sample_dense(setup, result, force_ref.time_s[1:])
            force_pred = controller_force_for_sample(setup, force_sample)
            row.update(
                {
                    "primary_rpm_rmse": compute_error_metrics(
                        reference=input_ref.value,
                        predicted=input_pred.primary_rpm,
                    ).root_mean_square_error,
                    "secondary_rpm_rmse": compute_error_metrics(
                        reference=output_ref.value,
                        predicted=output_pred.secondary_rpm,
                    ).root_mean_square_error,
                    "speed_ratio_rmse": compute_error_metrics(
                        reference=ratio_ref.value,
                        predicted=ratio_pred.speed_ratio,
                    ).root_mean_square_error,
                    "primary_force_rmse_n": compute_error_metrics(
                        reference=force_ref.value[1:],
                        predicted=force_pred,
                    ).root_mean_square_error,
                }
            )
        rows.append(row)

    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with (OUTPUT / "convergence.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    (OUTPUT / "convergence.json").write_text(
        json.dumps(
            {
                "cinder_version": cinder.__version__,
                "purpose": "numerical refinement of the unchanged closed-loop Ballew benchmark",
                "cases": rows,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _plot(rows)

    print(f"Artifacts: {OUTPUT}")
    return 0 if all(bool(row["completed"]) for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
