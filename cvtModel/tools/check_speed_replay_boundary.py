#!/usr/bin/env python3
"""Hard developer audit for CINDER's shaft-speed replay boundary.

The production replay boundary remains a one-line external-torque law.  This
tool supplies the numerical conditions under which that stiff penalty boundary
has been verified:

    K = 400 N m s/rad
    LSODA rtol = 1e-4
    LSODA atol = 1e-7
    max_step = 0.05 s

The secondary helix is converted *inside this audit only* to the project's
zero-clearance bilateral/slotted topology so the test exercises shaft replay
instead of the known selected-flank helix limitation.
"""

from __future__ import annotations

import argparse
import copy
import json
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np

import cinder
from cinder.contracts import (
    decode_simulation_case_document,
    project_simulation_result,
    validate_simulation_case_document,
)
from cinder.model.boundaries.shaft import SpeedReplayShaftBoundary
from cinder.model.cvt.actuation import HelicalTorqueReactionForce, PulleyActuator


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASE = ROOT / "examples" / "baja_baseline_simulation_case.json"
DEFAULT_GAIN = SpeedReplayShaftBoundary.DEFAULT_TRACKING_GAIN_NM_S_PER_RAD
Json = dict[str, Any]


class BilateralHelicalTorqueReactionForce(HelicalTorqueReactionForce):
    """Production signed helix law with zero-clearance opposite-flank support."""

    compressive_contact_margin = None
    has_compressive_contact = None


@dataclass(frozen=True)
class Metrics:
    gain: float
    rmse: float
    max_abs_error: float
    final_error: float
    max_abs_torque: float
    elapsed_s: float
    time: np.ndarray
    target: np.ndarray
    actual: np.ndarray
    torque: np.ndarray


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _use_slotted_secondary_helix(decoded) -> None:
    plant = decoded.plant
    laws = []
    changed = 0

    for law in plant.secondary_actuator.force_laws:
        if isinstance(law, BilateralHelicalTorqueReactionForce):
            laws.append(law)
        elif isinstance(law, HelicalTorqueReactionForce):
            laws.append(BilateralHelicalTorqueReactionForce(spec=law.spec))
            changed += 1
        else:
            laws.append(law)

    _assert(
        changed == 1,
        f"expected exactly one secondary helix law to convert; got {changed}",
    )
    object.__setattr__(plant, "secondary_actuator", PulleyActuator(*laws))


def _hard_reference(omega0: float) -> list[dict[str, float]]:
    return [
        {"time_s": 0.00, "value": omega0},
        {"time_s": 0.55, "value": 330.0},
        {"time_s": 1.00, "value": 330.0},
        {"time_s": 1.35, "value": 260.0},
        {"time_s": 1.75, "value": 260.0},
        {"time_s": 2.20, "value": 355.0},
        {"time_s": 3.00, "value": 355.0},
    ]


def _configure_document(baseline: Json, *, gain: float) -> Json:
    document = copy.deepcopy(baseline)
    omega0 = float(
        document["scenario"]["initial_cvt_state"][
            "primary_angular_speed_rad_per_s"
        ]
    )

    document["scenario"]["time_span_s"] = [0.0, 3.0]
    document["shaft_boundaries"]["primary"] = {
        "kind": "speed_replay_shaft",
        "speed_reference": {"points": _hard_reference(omega0)},
        "tracking_gain_Nm_s_per_rad": float(gain),
    }

    integrator = document["execution"]["integrator"]
    integrator["relative_tolerance"] = 1.0e-4
    integrator["absolute_tolerance"] = 1.0e-7
    # The solver-isolation audit showed that tightening tolerances was enough;
    # the ordinary 50 ms ceiling did not need to be reduced.
    integrator["max_step"] = 0.05

    document["execution"]["reporting"]["grid"] = {
        "kind": "uniform_time_step",
        "count": None,
        "step_seconds": 0.002,
    }
    return document


def _columns(payload: Json) -> dict[str, np.ndarray]:
    return {
        column["key"]: np.asarray(
            [
                np.nan if value is None else float(value)
                for value in column["values"]
            ],
            dtype=float,
        )
        for column in payload["report_table"]["columns"]
    }


def _run_case(baseline: Json, *, gain: float) -> Metrics:
    document = _configure_document(baseline, gain=gain)

    validation = validate_simulation_case_document(document)
    if not validation.is_valid:
        details = "\n".join(
            f"  [{finding.severity}] "
            f"{finding.document_path or '/'}: {finding.message}"
            for finding in validation.findings
        )
        raise AssertionError(f"public document validation failed:\n{details}")

    decoded = decode_simulation_case_document(document)
    boundary = decoded.system.primary_boundary
    _assert(
        isinstance(boundary, SpeedReplayShaftBoundary),
        "speed_replay_shaft decoded to the wrong boundary type",
    )

    _use_slotted_secondary_helix(decoded)
    initial_mode = decoded.system.classify_initial_mode(decoded.initial_state)

    started = perf_counter()
    result = decoded.system.run(
        time_span=decoded.time_span,
        initial_state=decoded.initial_state,
        initial_mode=initial_mode,
        settings=decoded.integrator_settings,
        reporting_settings=decoded.reporting_settings,
    )
    elapsed = perf_counter() - started

    _assert(result.completed, f"integration did not complete: {result.termination_reason}")

    columns = _columns(project_simulation_result(result))
    time = columns["time_s"]
    actual = columns["state.primary_angular_speed"]
    torque = columns["boundary.primary_external_torque"]
    target = np.asarray(
        [boundary.speed_reference.value_at(float(value)) for value in time],
        dtype=float,
    )

    mask = np.isfinite(target) & np.isfinite(actual)
    _assert(bool(np.any(mask)), "no finite replay samples")
    error = actual[mask] - target[mask]

    finite_torque = torque[np.isfinite(torque)]
    _assert(finite_torque.size > 0, "no finite replay torque samples")
    _assert(float(np.min(actual[mask])) >= 0.0, "positive replay drove shaft negative")

    return Metrics(
        gain=float(gain),
        rmse=float(np.sqrt(np.mean(error * error))),
        max_abs_error=float(np.max(np.abs(error))),
        final_error=float(error[-1]),
        max_abs_torque=float(np.max(np.abs(finite_torque))),
        elapsed_s=float(elapsed),
        time=time,
        target=target,
        actual=actual,
        torque=torque,
    )


def _print(metrics: Metrics) -> None:
    print(
        f"  K={metrics.gain:7.1f}: "
        f"RMSE={metrics.rmse:.4f} rad/s, "
        f"max={metrics.max_abs_error:.4f}, "
        f"final={metrics.final_error:+.4f}, "
        f"max|tau|={metrics.max_abs_torque:.1f} N m, "
        f"wall={metrics.elapsed_s:.2f} s"
    )


def _default_gate(metrics: Metrics) -> None:
    _assert(metrics.rmse <= 0.10, "default replay RMSE exceeds 0.10 rad/s")
    _assert(metrics.max_abs_error <= 0.25, "default replay max error exceeds 0.25 rad/s")
    _assert(abs(metrics.final_error) <= 0.15, "default replay final error exceeds 0.15 rad/s")


def _save_plots(metrics: Metrics, output_dir: Path, *, show: bool) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise SystemExit(
            "Plotting requested but matplotlib is not installed. "
            "Install it with: python -m pip install matplotlib"
        ) from error

    output_dir.mkdir(parents=True, exist_ok=True)

    figure = plt.figure(figsize=(9, 5))
    axis = figure.add_subplot(111)
    axis.plot(metrics.time, metrics.target, label="Target")
    axis.plot(metrics.time, metrics.actual, label="Actual")
    axis.set_title(f"Shaft speed replay, K={metrics.gain:g} N m s/rad")
    axis.set_xlabel("Time [s]")
    axis.set_ylabel("Angular speed [rad/s]")
    axis.grid(True, alpha=0.25)
    axis.legend()
    figure.tight_layout()
    figure.savefig(output_dir / "speed_replay_tracking.png", dpi=180)
    if show:
        plt.show()
    else:
        plt.close(figure)

    figure = plt.figure(figsize=(9, 5))
    axis = figure.add_subplot(111)
    axis.plot(metrics.time, metrics.actual - metrics.target)
    axis.axhline(0.0, linestyle="--")
    axis.set_title("Shaft speed replay error")
    axis.set_xlabel("Time [s]")
    axis.set_ylabel("Actual - target [rad/s]")
    axis.grid(True, alpha=0.25)
    figure.tight_layout()
    figure.savefig(output_dir / "speed_replay_error.png", dpi=180)
    if show:
        plt.show()
    else:
        plt.close(figure)

    figure = plt.figure(figsize=(9, 5))
    axis = figure.add_subplot(111)
    axis.plot(metrics.time, metrics.torque)
    axis.set_title("Numerical shaft replay torque")
    axis.set_xlabel("Time [s]")
    axis.set_ylabel("External replay torque [N m]")
    axis.grid(True, alpha=0.25)
    figure.tight_layout()
    figure.savefig(output_dir / "speed_replay_torque.png", dpi=180)
    if show:
        plt.show()
    else:
        plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", type=Path, default=DEFAULT_CASE)
    parser.add_argument("--gain", type=float, default=DEFAULT_GAIN)
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="Also rerun K=100, 200, 400 and 800 under the verified replay settings.",
    )
    parser.add_argument(
        "--plot",
        action="store_true",
        help="Save plots for the main run.",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Display plots interactively as well as saving them.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("speed_replay_audit"),
    )
    args = parser.parse_args()

    baseline_path = args.case.resolve()
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

    print(f"CINDER {cinder.__version__}")
    print(f"Baseline: {baseline_path}")
    print("Helix fixture: zero-clearance bilateral/slotted secondary helix")
    print("Replay integrator guidance: LSODA rtol=1e-4, atol=1e-7, max_step=0.05 s")
    print("Hard multistage primary-shaft replay...")

    metrics = _run_case(baseline, gain=float(args.gain))
    _print(metrics)

    if float(args.gain) == DEFAULT_GAIN:
        _default_gate(metrics)
        print("  default replay quality gate: PASS")

    if args.sweep:
        print("Gain convergence sweep:")
        for gain in (100.0, 200.0, 400.0, 800.0):
            _print(_run_case(baseline, gain=gain))

    if args.plot or args.show:
        output_dir = args.output_dir.resolve()
        _save_plots(metrics, output_dir, show=args.show)
        print(f"  plots: {output_dir}")

    print("Speed-replay boundary audit: PASS")


if __name__ == "__main__":
    main()
