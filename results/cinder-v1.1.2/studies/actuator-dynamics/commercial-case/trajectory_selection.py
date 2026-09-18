"""Pure selection logic for the OTS-secondary trajectory demonstration."""

from __future__ import annotations

import math
from typing import Any


def select_demonstration_case(
    rows: list[dict[str, Any]],
    *,
    target_lower: float,
    target_upper: float,
    minimum_denominator_fraction: float,
) -> dict[str, Any]:
    """Select one clean, denominator-robust case by a preregistered rule.

    Preferred result:
      1. clean-continuous;
      2. quasi-static helix torque never falls below the required fraction of
         its onset magnitude;
      3. achieved peak Pi_s,total lies inside [target_lower, target_upper];
      4. among those, choose the *slowest* ramp;
      5. then the smallest |added torque|;
      6. then the point closest to the centre of the target band.

    If the target band is not reached, return the eligible clean case with the
    largest achieved Pi and mark it explicitly as a fallback. The caller may
    still plot it, but must not relabel it as having reached the target band.
    """
    centre = 0.5 * (target_lower + target_upper)
    eligible = []
    for row in rows:
        try:
            pi = float(row["peak_pi_total"])
            floor = float(row["minimum_qs_torque_fraction_of_onset"])
            ramp = float(row["ramp_s"])
            amp = float(row["added_secondary_torque_Nm"])
        except (KeyError, TypeError, ValueError):
            continue
        if (
            row.get("status") == "completed"
            and row.get("response_class") == "clean_continuous"
            and math.isfinite(pi)
            and pi > 0.0
            and math.isfinite(floor)
            and floor >= minimum_denominator_fraction
        ):
            eligible.append(row)

    if not eligible:
        return {
            "selection_status": "no_eligible_clean_case",
            "target_lower": target_lower,
            "target_upper": target_upper,
            "minimum_denominator_fraction": minimum_denominator_fraction,
        }

    in_band = [
        row for row in eligible
        if target_lower <= float(row["peak_pi_total"]) <= target_upper
    ]
    if in_band:
        selected = min(
            in_band,
            key=lambda row: (
                -float(row["ramp_s"]),                  # slowest ramp first
                abs(float(row["added_secondary_torque_Nm"])),
                abs(float(row["peak_pi_total"]) - centre),
            ),
        )
        return {
            **selected,
            "selection_status": "target_band_reached",
            "target_lower": target_lower,
            "target_upper": target_upper,
            "minimum_denominator_fraction": minimum_denominator_fraction,
        }

    selected = max(eligible, key=lambda row: float(row["peak_pi_total"]))
    return {
        **selected,
        "selection_status": "target_band_unreached_fallback_highest_clean",
        "target_lower": target_lower,
        "target_upper": target_upper,
        "minimum_denominator_fraction": minimum_denominator_fraction,
    }
