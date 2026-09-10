from __future__ import annotations

from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
COMMERCIAL = HERE.parent / "commercial-case"
if str(COMMERCIAL) not in sys.path:
    sys.path.insert(0, str(COMMERCIAL))

from trajectory_selection import select_demonstration_case


def main() -> int:
    rows = [
        {
            "status": "completed",
            "response_class": "clean_continuous",
            "peak_pi_total": 0.13,
            "minimum_qs_torque_fraction_of_onset": 0.8,
            "ramp_s": 0.10,
            "added_secondary_torque_Nm": -80.0,
            "case_id": "fast_small",
        },
        {
            "status": "completed",
            "response_class": "clean_continuous",
            "peak_pi_total": 0.12,
            "minimum_qs_torque_fraction_of_onset": 0.7,
            "ramp_s": 0.15,
            "added_secondary_torque_Nm": -120.0,
            "case_id": "slow",
        },
        {
            "status": "completed",
            "response_class": "clean_continuous",
            "peak_pi_total": 0.17,
            "minimum_qs_torque_fraction_of_onset": 0.1,
            "ramp_s": 0.20,
            "added_secondary_torque_Nm": -20.0,
            "case_id": "bad_denominator",
        },
        {
            "status": "completed",
            "response_class": "impact_reset",
            "peak_pi_total": 0.15,
            "minimum_qs_torque_fraction_of_onset": 0.9,
            "ramp_s": 0.20,
            "added_secondary_torque_Nm": -20.0,
            "case_id": "reset",
        },
    ]
    chosen = select_demonstration_case(
        rows,
        target_lower=0.10,
        target_upper=0.20,
        minimum_denominator_fraction=0.25,
    )
    assert chosen["selection_status"] == "target_band_reached"
    assert chosen["case_id"] == "slow"  # slowest eligible ramp wins

    fallback = select_demonstration_case(
        [
            {
                "status": "completed",
                "response_class": "clean_continuous",
                "peak_pi_total": 0.06,
                "minimum_qs_torque_fraction_of_onset": 0.8,
                "ramp_s": 0.10,
                "added_secondary_torque_Nm": -80.0,
                "case_id": "low",
            }
        ],
        target_lower=0.10,
        target_upper=0.20,
        minimum_denominator_fraction=0.25,
    )
    assert fallback["selection_status"] == "target_band_unreached_fallback_highest_clean"
    assert fallback["case_id"] == "low"

    print("PASS OTS trajectory selection regression")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
