#!/usr/bin/env python3
"""End-to-end audit for CINDER's physical tracking boundary mechanisms.

This script intentionally tests more than constructor math.  It exercises:

1. direct component evaluation and saturation;
2. public simulation-document validation + decoding;
3. a complete hybrid CINDER run with ``speed_tracking_shaft``;
4. a complete hybrid CINDER run with ``axial_motion_tracking`` mounted on the
   primary pulley;
5. exported report channels, including the actuator contribution itself;
6. hard tracking-quality gates on RMSE, maximum error, and final error.

Run from a repository checkout after installing that checkout's CINDER package,
for example::

    python -m pip install -e cvtModel
    python cvtModel/tools/check_tracking_boundaries.py

A failed invariant raises immediately and returns a non-zero process status.
This is a developer/release audit, not a fitted validation study.
"""

from __future__ import annotations

import argparse
import copy
import json
from dataclasses import dataclass
from math import isclose
import math
from pathlib import Path
from typing import Any

import numpy as np

import cinder
from cinder.contracts import (
    decode_simulation_case_document,
    project_simulation_result,
    validate_simulation_case_document,
)
from cinder.model.boundaries.shaft import (
    ShaftBoundaryContext,
    SpeedTrackingShaftBoundary,
)
from cinder.model.cvt.actuation import (
    AxialMotionTrackingForce,
    AxialMotionTrackingForceSpec,
    PulleyActuationContext,
)
from cinder.model.reference import PiecewiseLinearReference, TimeValuePoint
from cinder.model.system import CVTState

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASE = ROOT / "examples" / "baja_baseline_simulation_case.json"

Json = dict[str, Any]


@dataclass(frozen=True)
class TrackingPlotData:
    label: str
    time: np.ndarray
    target: np.ndarray
    actual: np.ndarray
    effort: np.ndarray
    effort_limit: float
    value_unit: str
    effort_unit: str


def _tracking_metrics(target: np.ndarray, actual: np.ndarray) -> tuple[float, float, float]:
    mask = np.isfinite(target) & np.isfinite(actual)
    _assert(bool(np.any(mask)), "tracking metrics received no finite target/actual samples")
    error = actual[mask] - target[mask]
    rmse = float(np.sqrt(np.mean(error * error)))
    max_abs = float(np.max(np.abs(error)))
    final = float(error[-1])
    return rmse, max_abs, final


def _assert_tracking_quality(
    *,
    label: str,
    rmse: float,
    max_abs_error: float,
    final_error: float,
    rmse_limit: float,
    max_abs_limit: float,
    final_abs_limit: float,
    unit: str,
) -> None:
    _assert(
        rmse <= rmse_limit,
        f"{label}: RMSE {rmse:.6g} {unit} exceeds limit {rmse_limit:.6g} {unit}",
    )
    _assert(
        max_abs_error <= max_abs_limit,
        f"{label}: max tracking error {max_abs_error:.6g} {unit} "
        f"exceeds limit {max_abs_limit:.6g} {unit}",
    )
    _assert(
        abs(final_error) <= final_abs_limit,
        f"{label}: final tracking error {final_error:+.6g} {unit} "
        f"exceeds ±{final_abs_limit:.6g} {unit}",
    )


def _plot_tracking_results(
    runs: tuple[TrackingPlotData, ...],
    *,
    show: bool,
    save_dir: Path | None,
) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise SystemExit(
            "Plotting requested but matplotlib is not installed. "
            "Install it with: python -m pip install matplotlib"
        ) from error

    if save_dir is not None:
        save_dir.mkdir(parents=True, exist_ok=True)

    for run in runs:
        fig, (ax_value, ax_effort) = plt.subplots(2, 1, sharex=True, figsize=(9, 7))
        ax_value.plot(run.time, run.target, label="Target")
        ax_value.plot(run.time, run.actual, label="Actual")
        ax_value.set_ylabel(run.value_unit)
        ax_value.set_title(run.label)
        ax_value.grid(True, alpha=0.25)
        ax_value.legend()

        ax_effort.plot(run.time, run.effort, label="Actuator effort")
        ax_effort.axhline(run.effort_limit, linestyle="--", label="+ limit")
        ax_effort.axhline(-run.effort_limit, linestyle="--", label="- limit")
        ax_effort.set_xlabel("Time [s]")
        ax_effort.set_ylabel(run.effort_unit)
        ax_effort.grid(True, alpha=0.25)
        ax_effort.legend()
        fig.tight_layout()

        if save_dir is not None:
            filename = run.label.lower().replace(" ", "_").replace("/", "_") + ".png"
            path = save_dir / filename
            fig.savefig(path, dpi=160)
            print(f"  saved plot: {path}")

    if show:
        plt.show()
    else:
        plt.close("all")


def _reference(*pairs: tuple[float, float]) -> PiecewiseLinearReference:
    return PiecewiseLinearReference(tuple(TimeValuePoint(t, value) for t, value in pairs))


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _column_map(payload: Json) -> dict[str, np.ndarray]:
    table = payload["report_table"]
    return {
        column["key"]: np.asarray(
            [np.nan if value is None else float(value) for value in column["values"]],
            dtype=float,
        )
        for column in table["columns"]
    }


def _run_document(label: str, document: Json) -> tuple[Any, Json]:
    validation = validate_simulation_case_document(document)
    if not validation.is_valid:
        details = "\n".join(
            f"  [{item.severity}] {item.document_path or '/'}: {item.message}"
            for item in validation.findings
        )
        raise AssertionError(f"{label}: public document validation failed:\n{details}")

    decoded = decode_simulation_case_document(document)
    result = decoded.system.run(
        time_span=decoded.time_span,
        initial_state=decoded.initial_state,
        initial_mode=decoded.initial_mode,
        settings=decoded.integrator_settings,
        reporting_settings=decoded.reporting_settings,
    )
    payload = project_simulation_result(result)

    _assert(result.completed, f"{label}: integration did not complete ({result.termination_reason}).")
    _assert(payload["report_table"]["row_count"] >= 2, f"{label}: report table is empty.")
    return decoded, payload


def _configure_short_run(document: Json, *, duration_s: float = 0.8) -> None:
    document["scenario"]["time_span_s"] = [0.0, duration_s]
    document["execution"]["integrator"]["max_step"] = min(
        0.02, float(document["execution"]["integrator"]["max_step"])
    )
    document["execution"]["reporting"]["grid"] = {
        "kind": "uniform_time_step",
        "count": None,
        "step_seconds": 0.01,
    }
    document["execution"]["reporting"]["include_actuation"] = True


def _direct_component_checks() -> None:
    reference = _reference((0.0, 100.0), (1.0, 120.0), (2.0, 120.0))
    state = CVTState(
        primary_angular_speed=90.0,
        secondary_angular_speed=80.0,
        belt_speed=0.0,
        shift_position=0.0,
        shift_speed=0.0,
    )
    boundary = SpeedTrackingShaftBoundary.from_tracking_error_budget(
        speed_reference=reference,
        torque_limit=7.0,
        tracking_error_budget=2.0,
        equivalent_inertia=0.2,
        feedforward_inertia=0.1,
        feedback_authority_fraction=0.8,
    )
    primary = boundary.evaluate(
        ShaftBoundaryContext(time=0.5, cvt=state, shaft="primary")
    )
    secondary = boundary.evaluate(
        ShaftBoundaryContext(time=0.5, cvt=state, shaft="secondary")
    )
    _assert(isclose(primary.external_torque, 7.0), "shaft tracker did not saturate as expected")
    _assert(isclose(secondary.external_torque, 7.0), "shaft tracker is unexpectedly shaft-specific")
    _assert(isclose(primary.equivalent_inertia, 0.2), "shaft tracker lost equivalent inertia")
    _assert(primary.metadata["actuator_saturated"] is True, "saturation metadata is wrong")

    position = _reference((0.0, 0.010), (1.0, 0.020), (2.0, 0.020))
    axial = AxialMotionTrackingForce(
        AxialMotionTrackingForceSpec(
            position_reference=position,
            speed_reference=None,
            position_gain=1000.0,
            speed_gain=100.0,
            force_limit=100.0,
        )
    )
    context = PulleyActuationContext(
        time=0.5,
        axial_position=0.012,
        axial_speed=0.005,
        shaft_speed=0.0,
    )
    relation = axial.evaluate(context)
    expected = 1000.0 * (0.015 - 0.012) + 100.0 * (0.010 - 0.005)
    _assert(
        isclose(relation.bias, expected, rel_tol=0.0, abs_tol=1.0e-12),
        "axial position tracking did not use the position-reference slope for damping",
    )


def _shaft_tracking_full_run(baseline: Json) -> TrackingPlotData:
    document = copy.deepcopy(baseline)
    _configure_short_run(document, duration_s=0.8)

    omega0 = float(document["scenario"]["initial_cvt_state"]["primary_angular_speed_rad_per_s"])
    target = omega0 + 45.0
    torque_limit = 30.0
    # Deliberately omit both an explicit gain and an error budget here. The
    # public decoder must resolve the normal automatic best-effort tuning from
    # the uploaded speed trace and actuator authority.
    document["shaft_boundaries"]["primary"] = {
        "kind": "speed_tracking_shaft",
        "speed_reference": {
            "points": [
                {"time_s": 0.0, "value": omega0},
                {"time_s": 0.35, "value": target},
                {"time_s": 0.8, "value": target},
            ]
        },
        "torque_limit_Nm": torque_limit,
        "equivalent_inertia_kg_m2": 0.05,
    }

    decoded, payload = _run_document("shaft speed tracker", document)
    _assert(
        isinstance(decoded.system.primary_boundary, SpeedTrackingShaftBoundary),
        "speed_tracking_shaft did not decode to SpeedTrackingShaftBoundary",
    )

    columns = _column_map(payload)
    torque = columns["boundary.primary_external_torque"]
    omega = columns["state.primary_angular_speed"]
    finite_torque = torque[np.isfinite(torque)]
    finite_omega = omega[np.isfinite(omega)]
    _assert(finite_torque.size > 0, "shaft run exported no finite primary boundary torque")
    _assert(finite_omega.size > 1, "shaft run exported no usable primary speed history")
    _assert(
        float(np.max(np.abs(finite_torque))) <= torque_limit + 1.0e-9,
        "shaft tracker exceeded its configured torque limit",
    )
    _assert(
        float(np.max(np.abs(finite_torque))) > 1.0e-6,
        "shaft tracker never applied actuator torque during the full run",
    )
    _assert(
        float(finite_omega[-1]) > float(finite_omega[0]) + 1.0,
        "primary speed did not move in the commanded direction during the full run",
    )

    time = columns["time_s"]
    target_speed = np.asarray(
        [decoded.system.primary_boundary.speed_reference.value_at(float(t)) for t in time],
        dtype=float,
    )
    rmse, max_error, final_error = _tracking_metrics(target_speed, omega)
    _assert_tracking_quality(
        label="shaft speed tracker",
        rmse=rmse,
        max_abs_error=max_error,
        final_error=final_error,
        rmse_limit=2.0,
        max_abs_limit=4.0,
        final_abs_limit=1.5,
        unit="rad/s",
    )
    print(
        "  shaft full run: PASS "
        f"(omega {finite_omega[0]:.3f} -> {finite_omega[-1]:.3f} rad/s, "
        f"max |tau_act|={np.max(np.abs(finite_torque)):.3f} N m, "
        f"RMSE={rmse:.3f} rad/s, max error={max_error:.3f} rad/s, "
        f"final error={final_error:+.3f} rad/s, "
        f"K_omega={decoded.system.primary_boundary.proportional_gain:.3f} N m s/rad, "
        f"error budget={decoded.system.primary_boundary.tracking_error_budget:.3f} rad/s)"
    )
    return TrackingPlotData(
        label="Shaft speed tracking",
        time=time,
        target=target_speed,
        actual=omega,
        effort=torque,
        effort_limit=torque_limit,
        value_unit="Angular speed [rad/s]",
        effort_unit="Torque [N m]",
    )


def _axial_tracking_full_run(baseline: Json) -> TrackingPlotData:
    document = copy.deepcopy(baseline)
    _configure_short_run(document, duration_s=0.8)

    force_limit = 2500.0
    initial_shift = float(
        document["scenario"]["initial_cvt_state"]["shift_position_m"]
    )
    target_shift = 0.008

    # Treat this mechanism as a numerical motion servo. Choose Kx from a
    # static-error budget and reserve some actuator authority for transients.
    desired_static_error_m = 0.0005
    authority_fraction_for_static_load = 0.80
    position_gain = (
        authority_fraction_for_static_load
        * force_limit
        / desired_static_error_m
    )

    # Use the primary movable-sheave mass as a local second-order estimate for
    # damping. The full CVT has additional configuration-dependent inertia and
    # loads, so the full-run tracking assertions below remain authoritative.
    moving_mass = float(
        document["assembly"]["inertias"]["primary"]["moving_sheave_mass_kg"]
    )
    damping_ratio = 0.90
    speed_gain = 2.0 * damping_ratio * math.sqrt(moving_mass * position_gain)

    tracker = {
        "kind": "axial_motion_tracking",
        "position_reference": {
            "points": [
                {"time_s": 0.0, "value": initial_shift},
                {"time_s": 0.45, "value": target_shift},
                {"time_s": 0.8, "value": target_shift},
            ]
        },
        "speed_reference": None,
        "position_gain_N_per_m": position_gain,
        "speed_gain_N_s_per_m": speed_gain,
        "force_limit_N": force_limit,
    }
    document["assembly"]["pulleys"]["primary"]["components"].append(tracker)

    decoded, payload = _run_document("axial motion tracker", document)
    primary_force_laws = decoded.assembly.pulleys.primary.actuator.force_laws
    _assert(
        any(isinstance(item, AxialMotionTrackingForce) for item in primary_force_laws),
        "axial_motion_tracking did not decode into the primary actuator",
    )

    columns = _column_map(payload)
    signal_key = "actuation.primary.axial_motion_tracking"
    _assert(signal_key in columns, f"full run did not export {signal_key}")
    force = columns[signal_key]
    shift = columns["state.shift_position"]
    finite_force = force[np.isfinite(force)]
    finite_shift = shift[np.isfinite(shift)]
    _assert(finite_force.size > 0, "axial run exported no finite tracking force")
    _assert(finite_shift.size > 1, "axial run exported no usable shift history")
    _assert(
        float(np.max(np.abs(finite_force))) <= force_limit + 1.0e-7,
        "axial tracker exceeded its configured force limit",
    )
    _assert(
        float(np.max(np.abs(finite_force))) > 10.0,
        "axial tracker contribution was effectively zero during the full run",
    )
    _assert(
        float(np.max(finite_shift)) > float(finite_shift[0]) + 1.0e-5,
        "primary shift coordinate never responded during the axial-tracking run",
    )

    time = columns["time_s"]
    tracker_object = next(
        item for item in primary_force_laws if isinstance(item, AxialMotionTrackingForce)
    )
    reference = tracker_object.spec.position_reference
    _assert(reference is not None, "axial audit unexpectedly has no position reference")
    target_position = np.asarray(
        [reference.value_at(float(t)) for t in time],
        dtype=float,
    )
    rmse, max_error, final_error = _tracking_metrics(target_position, shift)
    _assert_tracking_quality(
        label="axial motion tracker",
        rmse=1e3 * rmse,
        max_abs_error=1e3 * max_error,
        final_error=1e3 * final_error,
        rmse_limit=0.75,
        max_abs_limit=2.0,
        final_abs_limit=0.60,
        unit="mm",
    )
    print(
        "  axial full run: PASS "
        f"(shift max={np.max(finite_shift):.6f} m, "
        f"max |F_act|={np.max(np.abs(finite_force)):.3f} N, "
        f"RMSE={1e3 * rmse:.3f} mm, max error={1e3 * max_error:.3f} mm, "
        f"final error={1e3 * final_error:+.3f} mm, "
        f"Kx={position_gain:.0f} N/m, Kv={speed_gain:.0f} N s/m)"
    )
    return TrackingPlotData(
        label="Axial motion tracking",
        time=time,
        target=1e3 * target_position,
        actual=1e3 * shift,
        effort=force,
        effort_limit=force_limit,
        value_unit="Primary shift [mm]",
        effort_unit="Force [N]",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case",
        type=Path,
        default=DEFAULT_CASE,
        help="Baseline public CINDER simulation-case document to modify for the audit.",
    )
    parser.add_argument(
        "--plot",
        action="store_true",
        help="Open target-vs-actual tracking plots after the audit. Requires matplotlib.",
    )
    parser.add_argument(
        "--save-plots",
        type=Path,
        default=None,
        metavar="DIR",
        help="Save tracking plots as PNG files in DIR. Requires matplotlib.",
    )
    args = parser.parse_args()

    baseline_path = args.case.resolve()
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

    print(f"CINDER {cinder.__version__}")
    print(f"Baseline: {baseline_path}")
    print("Direct component checks...")
    _direct_component_checks()
    print("  direct component checks: PASS")
    print("Full speed-tracking shaft run...")
    shaft_plot = _shaft_tracking_full_run(baseline)
    print("Full axial-motion tracking run...")
    axial_plot = _axial_tracking_full_run(baseline)
    print("Tracking-boundary audit: PASS")

    if args.plot or args.save_plots is not None:
        _plot_tracking_results(
            (shaft_plot, axial_plot),
            show=args.plot,
            save_dir=args.save_plots.resolve() if args.save_plots is not None else None,
        )


if __name__ == "__main__":
    main()
