from __future__ import annotations

import unittest

import pandas as pd

from baja_track_analysis.config import PipelineConfig
from baja_track_analysis.grouping import suggest_adjacent_grouping


class GroupingTests(unittest.TestCase):
    def test_close_unrecovered_pair_is_suggested_as_group(self) -> None:
        features = pd.DataFrame(
            [
                {"sequence": 1, "name": "Bump", "distance_to_next_event_m": 2.0, "candidate_group": "C1", "final_group_id": "E01"},
                {"sequence": 2, "name": "Turn", "distance_to_next_event_m": 20.0, "candidate_group": "C1", "final_group_id": "E02"},
            ]
        )
        passes = pd.DataFrame(
            [
                {"sequence": 1, "aggregate_eligible": True, "effective_gps_resolution_m": 8.0, "recovered_before_next_event": False},
                {"sequence": 2, "aggregate_eligible": True, "effective_gps_resolution_m": 8.0, "recovered_before_next_event": True},
            ]
        )
        result = suggest_adjacent_grouping(features, passes, PipelineConfig()).iloc[0]
        self.assertEqual(result["recommendation"], "GROUP_OBSERVED_RESPONSE")
        self.assertEqual(result["decision_consistency"], "CONFLICT_REVIEW")


if __name__ == "__main__":
    unittest.main()

