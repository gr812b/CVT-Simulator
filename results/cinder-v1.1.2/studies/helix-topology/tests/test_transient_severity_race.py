from __future__ import annotations

from experiments.run_transient_severity_race import (
    contact_is_stick_stick,
    event_order,
    first_contact_exit,
    pretraction_rows,
)


STICK_FREE = (
    "CVTOperatingRegime(engagement=ENGAGED, shift_constraint=CVTShiftConstraint.FREE, "
    "contact_regime=ContactRegime(mode=EngagedContactMode.STICK_STICK))"
)
STICK_STOP = (
    "CVTOperatingRegime(engagement=ENGAGED, shift_constraint=CVTShiftConstraint.UPPER_STOP, "
    "contact_regime=ContactRegime(mode=EngagedContactMode.STICK_STICK))"
)
BOTH_SLIP = (
    "CVTOperatingRegime(engagement=ENGAGED, shift_constraint=CVTShiftConstraint.FREE, "
    "contact_regime=ContactRegime(mode=EngagedContactMode.BOTH_SLIP))"
)


def row(t: float, mode: str) -> dict:
    return {
        "time_s": t,
        "cvt_mode": mode,
        "lambda_primary": 0.2,
        "lambda_secondary": -0.25,
        "helix_reacted_torque_margin_Nm": 2.0,
        "helix_quasi_static_margin_Nm": 3.0,
    }


def test_shift_constraint_change_does_not_count_as_traction_exit():
    rows = [row(0.05, STICK_FREE), row(0.06, STICK_STOP), row(0.07, STICK_STOP)]
    assert contact_is_stick_stick(STICK_STOP)
    assert first_contact_exit(rows, onset_s=0.05) is None


def test_first_contact_exit_detects_first_slip_sample():
    rows = [row(0.05, STICK_FREE), row(0.06, STICK_FREE), row(0.07, BOTH_SLIP)]
    out = first_contact_exit(rows, onset_s=0.05)
    assert out is not None
    assert abs(out["traction_exit_time_s"] - 0.07) < 1.0e-12
    assert "stick_stick" in out["traction_exit_mode_before"].lower()
    assert "both_slip" in out["traction_exit_mode_after"].lower()


def test_event_order_labels_helix_before_traction():
    h = {"crossing_time_s": 0.1000}
    t = {"traction_exit_time_s": 0.1010}
    label, delta = event_order(
        helix_crossing=h,
        traction_exit=t,
        simultaneous_tolerance_s=0.0002,
    )
    assert label == "helix_first"
    assert delta is not None and delta < 0.0


def test_event_order_labels_close_events_unresolved():
    h = {"crossing_time_s": 0.1000}
    t = {"traction_exit_time_s": 0.1001}
    label, _ = event_order(
        helix_crossing=h,
        traction_exit=t,
        simultaneous_tolerance_s=0.0002,
    )
    assert label == "simultaneous_or_unresolved"


def test_pretraction_rows_stop_before_first_nonstick_sample():
    rows = [row(0.05, STICK_FREE), row(0.06, STICK_FREE), row(0.07, BOTH_SLIP)]
    exit_row = first_contact_exit(rows, onset_s=0.05)
    selected = pretraction_rows(rows, onset_s=0.05, traction_exit=exit_row)
    assert [r["time_s"] for r in selected] == [0.05, 0.06]
