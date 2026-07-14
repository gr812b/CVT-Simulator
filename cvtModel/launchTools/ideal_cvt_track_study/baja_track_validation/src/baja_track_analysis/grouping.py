from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .config import PipelineConfig


def suggest_adjacent_grouping(
    individual_features: pd.DataFrame,
    individual_passes: pd.DataFrame,
    config: PipelineConfig,
) -> pd.DataFrame:
    """Audit final grouping decisions against GPS resolvability and recovery.

    This only determines whether the observed speed responses can be separated.
    It never deletes the physical subfeature rows used by the simulator.
    """

    features = individual_features.sort_values("sequence").reset_index(drop=True)
    rows: list[dict[str, object]] = []
    threshold = config.metric.grouping_recovery_fraction_threshold

    for index in range(len(features) - 1):
        current = features.iloc[index]
        following = features.iloc[index + 1]
        current_passes = individual_passes[
            (individual_passes["sequence"] == int(current["sequence"]))
            & individual_passes["aggregate_eligible"]
        ]
        following_passes = individual_passes[
            (individual_passes["sequence"] == int(following["sequence"]))
            & individual_passes["aggregate_eligible"]
        ]
        gap = float(current["distance_to_next_event_m"])
        resolution_values = pd.concat(
            [current_passes["effective_gps_resolution_m"], following_passes["effective_gps_resolution_m"]],
            ignore_index=True,
        ).dropna()
        effective_resolution = float(resolution_values.median()) if len(resolution_values) else math.nan
        recovery_fraction = (
            float(current_passes["recovered_before_next_event"].mean())
            if len(current_passes)
            else math.nan
        )
        overlap = gap < 0
        below_resolution = bool(
            np.isfinite(effective_resolution)
            and gap <= config.metric.grouping_resolution_multiplier * effective_resolution
        )
        no_recovery = bool(np.isfinite(recovery_fraction) and recovery_fraction < threshold)
        candidate_current = _clean_candidate(current.get("candidate_group", ""))
        candidate_following = _clean_candidate(following.get("candidate_group", ""))
        predeclared_candidate = bool(candidate_current and candidate_current == candidate_following)

        reasons = []
        if overlap:
            reasons.append("physical_extents_overlap")
        if below_resolution:
            reasons.append("separation_below_effective_gps_resolution")
        if no_recovery:
            reasons.append("no_recovery_before_next_on_most_valid_laps")
        if predeclared_candidate:
            reasons.append("manual_candidate_cluster")

        physics_reasons = sum((overlap, below_resolution, no_recovery))
        if overlap or (below_resolution and no_recovery):
            recommendation = "GROUP_OBSERVED_RESPONSE"
            confidence = "high" if physics_reasons >= 2 else "medium"
        elif physics_reasons == 1 or predeclared_candidate:
            recommendation = "REVIEW"
            confidence = "medium" if physics_reasons else "low"
        else:
            recommendation = "SEPARATE_SUPPORTED"
            confidence = "medium"

        current_group = str(current.get("final_group_id", ""))
        following_group = str(following.get("final_group_id", ""))
        declared_same = bool(current_group and current_group == following_group)
        if recommendation == "GROUP_OBSERVED_RESPONSE" and not declared_same:
            consistency = "CONFLICT_REVIEW"
        elif recommendation == "SEPARATE_SUPPORTED" and declared_same:
            consistency = "DECLARED_GROUP_WITHOUT_GPS_SUPPORT"
        else:
            consistency = "CONSISTENT"

        rows.append(
            {
                "first_sequence": int(current["sequence"]),
                "first_name": current["name"],
                "second_sequence": int(following["sequence"]),
                "second_name": following["name"],
                "gap_between_physical_extents_m": gap,
                "median_effective_gps_resolution_m": effective_resolution,
                "fraction_recovered_before_second": recovery_fraction,
                "valid_first_feature_passes": int(len(current_passes)),
                "valid_second_feature_passes": int(len(following_passes)),
                "predeclared_candidate_group": candidate_current if predeclared_candidate else "",
                "declared_same_final_group": declared_same,
                "first_final_group_id": current_group,
                "second_final_group_id": following_group,
                "recommendation": recommendation,
                "confidence": confidence,
                "decision_consistency": consistency,
                "reasons": ";".join(reasons),
                "interpretation": "GPS-response grouping only; retain both physical subfeatures in simulation",
            }
        )
    return pd.DataFrame(rows)


def _clean_candidate(value: object) -> str:
    text = str(value).strip()
    return "" if text.casefold() in {"", "n/a", "na", "none", "nan"} else text

