from __future__ import annotations

import unittest

import pandas as pd

from baja_track_analysis.simulation import compare_event_predictions, compare_lap_profile


class SimulationComparisonTests(unittest.TestCase):
    def test_event_comparison_errors(self) -> None:
        observed = pd.DataFrame(
            [
                {
                    "case_id": "E1__lap_001", "analysis_group_id": "E1", "entry_speed_kmh": 30.0,
                    "event_min_speed_kmh": 20.0, "end_speed_kmh": 24.0, "event_time_s": 2.0,
                    "recovery_distance_m": 10.0, "specific_ke_change_to_min_j_per_kg": 30.0,
                    "specific_ke_change_to_end_j_per_kg": 20.0,
                },
                {
                    "case_id": "E1__lap_002", "analysis_group_id": "E1", "entry_speed_kmh": 32.0,
                    "event_min_speed_kmh": 22.0, "end_speed_kmh": 25.0, "event_time_s": 2.2,
                    "recovery_distance_m": 12.0, "specific_ke_change_to_min_j_per_kg": 32.0,
                    "specific_ke_change_to_end_j_per_kg": 21.0,
                },
            ]
        )
        predictions = pd.DataFrame(
            [
                {"case_id": "E1__lap_001", "predicted_min_speed_kmh": 21.0, "predicted_end_speed_kmh": 25.0, "predicted_event_time_s": 2.1, "predicted_recovery_distance_m": 11.0},
                {"case_id": "E1__lap_002", "predicted_min_speed_kmh": 23.0, "predicted_end_speed_kmh": 26.0, "predicted_event_time_s": 2.3, "predicted_recovery_distance_m": 13.0},
            ]
        )
        cases, summary = compare_event_predictions(observed, predictions)
        self.assertTrue((cases["min_speed_kmh_error"] == 1.0).all())
        all_min = summary[(summary["analysis_group_id"] == "ALL") & (summary["metric"] == "min_speed_kmh")].iloc[0]
        self.assertAlmostEqual(all_min["bias"], 1.0)

    def test_lap_profile_comparison(self) -> None:
        observed = pd.DataFrame(
            {
                "s_m": [0.0, 10.0, 20.0],
                "median_speed_kmh": [20.0, 30.0, 20.0],
                "p25_speed_kmh": [18.0, 28.0, 18.0],
                "p75_speed_kmh": [22.0, 32.0, 22.0],
            }
        )
        predicted = pd.DataFrame({"s_m": [0.0, 10.0, 20.0], "predicted_speed_kmh": [21.0, 31.0, 21.0]})
        _, summary = compare_lap_profile(observed, predicted)
        self.assertAlmostEqual(summary.iloc[0]["speed_mae_kmh"], 1.0)
        self.assertAlmostEqual(summary.iloc[0]["fraction_within_observed_iqr"], 1.0)


if __name__ == "__main__":
    unittest.main()

