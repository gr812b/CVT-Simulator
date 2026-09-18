from __future__ import annotations

# --- results study-local import bootstrap ---
from pathlib import Path as _ResultsPath
import sys as _results_sys

_results_file = _ResultsPath(__file__).resolve()
_results_study_root = next(
    (parent for parent in _results_file.parents if (parent / "study.json").is_file()),
    None,
)
if _results_study_root is None:
    raise RuntimeError(f"Could not locate study root for {_results_file}")
_results_release_root = _results_study_root.parents[1]
for _results_path in (str(_results_study_root), str(_results_release_root)):
    while _results_path in _results_sys.path:
        _results_sys.path.remove(_results_path)
_results_sys.path.insert(0, str(_results_release_root))
_results_sys.path.insert(0, str(_results_study_root))
# --- end results study-local import bootstrap ---


from dataclasses import dataclass

from experiments.run_dynamic_only_liftoff import (
    classify_crossing,
    first_full_crossing,
)


MODE = (
    "CVTOperatingRegime(engagement=ENGAGED, "
    "shift_constraint=CVTShiftConstraint.FREE, "
    "contact_regime=ContactRegime(mode=EngagedContactMode.STICK_STICK))"
)


def row(t: float, full: float, qs: float, power: float) -> dict:
    return {
        "time_s": t,
        "helix_reacted_torque_margin_Nm": full,
        "helix_quasi_static_margin_Nm": qs,
        "helix_dynamic_correction_Nm": full - qs,
        "helix_secondary_internal_power_W": power,
        "lambda_primary": 0.25,
        "lambda_secondary": -0.30,
        "shift_m": 0.010,
        "shift_speed_m_s": -0.02,
        "helix_shift_acceleration_m_s2": -20.0,
        "helix_secondary_angular_acceleration_rad_s2": 50.0,
        "helix_belt_reaction_torque_Nm": 8.0,
        "helix_torsional_spring_torque_Nm": 2.0,
        "helix_shaft_accel_reaction_torque_Nm": -0.1,
        "helix_shift_accel_reaction_torque_Nm": full - qs + 0.1,
        "helix_curvature_reaction_torque_Nm": 0.0,
        "tau_secondary_belt_Nm": 16.0,
        "primary_external_torque_Nm": 15.0,
        "secondary_external_torque_Nm": -10.0,
        "primary_rpm": 3000.0,
        "secondary_rpm": 2000.0,
        "normal_primary_N": 1500.0,
        "normal_secondary_N": 1600.0,
        "cvt_mode": MODE,
    }


@dataclass
class Geometry:
    deadzone_shift: float = 0.002
    max_shift: float = 0.018


@dataclass
class Result:
    transitions: list


@dataclass
class Run:
    result: Result


def test_first_full_crossing_interpolates_companion_values():
    rows = [row(0.05, 2.0, 3.0, 1000.0), row(0.10, -2.0, 2.0, 800.0)]
    crossing = first_full_crossing(rows, onset_s=0.05)
    assert crossing is not None
    assert abs(crossing["crossing_time_s"] - 0.075) < 1.0e-12
    assert abs(crossing["crossing_helix_quasi_static_margin_Nm"] - 2.5) < 1.0e-12
    assert abs(crossing["crossing_helix_secondary_internal_power_W"] - 900.0) < 1.0e-12
    assert crossing["crossing_stick_stick"] is True


def test_clean_classification_requires_forward_power_stick_and_no_transition():
    rows = [row(0.05, 2.0, 3.0, 1000.0), row(0.10, -2.0, 2.0, 800.0)]
    crossing = first_full_crossing(rows, onset_s=0.05)
    flags = classify_crossing(
        crossing,
        run=Run(Result([])),
        onset_s=0.05,
        geometry_spec=Geometry(),
        qs_guard_Nm=0.25,
        friction_guard=0.649,
        interior_guard_percent=2.0,
    )
    assert flags["dynamic_only_at_crossing"] is True
    assert flags["forward_power_at_crossing"] is True
    assert flags["no_prior_hybrid_transition"] is True
    assert flags["interior_at_crossing"] is True
    assert flags["clean_forward_stick_dynamic_only_crossing"] is True


def test_reverse_power_rejects_clean_candidate():
    rows = [row(0.05, 2.0, 3.0, -1000.0), row(0.10, -2.0, 2.0, -800.0)]
    crossing = first_full_crossing(rows, onset_s=0.05)
    flags = classify_crossing(
        crossing,
        run=Run(Result([])),
        onset_s=0.05,
        geometry_spec=Geometry(),
        qs_guard_Nm=0.25,
        friction_guard=0.649,
        interior_guard_percent=2.0,
    )
    assert flags["dynamic_only_at_crossing"] is True
    assert flags["forward_power_at_crossing"] is False
    assert flags["clean_forward_stick_dynamic_only_crossing"] is False
