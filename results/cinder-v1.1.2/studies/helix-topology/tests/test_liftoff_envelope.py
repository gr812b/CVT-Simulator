from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / "experiments"
for path in (ROOT, EXPERIMENTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import run_liftoff_envelope as e5


def _row(brake, full, qs, *, reference=True):
    return {
        "status": "completed",
        "primary_brake_magnitude_Nm": float(brake),
        "primary_target_torque_Nm": -float(brake),
        "minimum_full_margin_Nm": float(full),
        "minimum_qs_margin_Nm": float(qs),
        "within_reference_brake_magnitude": bool(reference),
        "case_id": f"b{brake}",
    }


def test_first_sign_bracket_is_local_and_ordered_by_brake_magnitude():
    rows = [
        _row(40.0, -1.0, 2.0, reference=False),
        _row(20.0, 2.0, 3.0),
        _row(30.0, 0.5, 2.5, reference=False),
    ]
    brackets = e5._first_sign_brackets(rows, "minimum_full_margin_Nm")
    assert len(brackets) == 1
    left, right = brackets[0]
    assert left["primary_brake_magnitude_Nm"] == 30.0
    assert right["primary_brake_magnitude_Nm"] == 40.0


def test_dynamic_ramp_seed_prefers_reference_scale_when_close():
    rows = [
        _row(28.0, 1.5, 2.0, reference=True),
        _row(36.0, 0.1, 0.5, reference=False),
    ]
    selected = e5._select_dynamic_ramp_seed(rows, near_qs_upper_Nm=5.0)
    assert selected is not None
    assert selected["primary_brake_magnitude_Nm"] == 28.0


def test_vehicle_case_id_preserves_fractional_bisection_torque():
    a = e5.VehiclePoint("s50", -30.0, -38.5, 0.25, "bisect_full_dynamic")
    b = e5.VehiclePoint("s50", -30.0, -38.75, 0.25, "bisect_full_dynamic")
    assert a.case_id != b.case_id
