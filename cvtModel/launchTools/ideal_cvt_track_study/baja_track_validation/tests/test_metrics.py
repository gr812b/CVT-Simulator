from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from baja_track_analysis.config import PipelineConfig
from baja_track_analysis.gps_core import Centreline, LocalFrame
from baja_track_analysis.metrics import add_event_geometry, extract_event_passes


class MetricTests(unittest.TestCase):
    def test_ordered_entry_min_end_and_specific_ke(self) -> None:
        centreline = Centreline(
            x=np.array([0.0, 100.0, 0.0]),
            y=np.array([0.0, 0.0, 0.0]),
            s_nodes_m=np.array([0.0, 100.0, 200.0]),
            frame=LocalFrame(43.0, -79.0),
        )
        s = np.arange(0.0, 200.0, 2.0)
        speed = np.full_like(s, 36.0)
        speed[(s >= 45) & (s <= 55)] = np.linspace(32.0, 18.0, ((s >= 45) & (s <= 55)).sum())
        speed[(s > 55) & (s <= 75)] = np.linspace(18.0, 36.0, ((s > 55) & (s <= 75)).sum())
        profile = pd.DataFrame({"s_m": s, "speed_kmh": speed, "elapsed_s": s / 8.0})
        matched = pd.DataFrame(
            {
                "lap_id": 1,
                "s_m": np.arange(0.0, 200.0, 5.0),
                "map_error_m": 1.0,
                "speed_analysis_kmh": 36.0,
                "throttle_pct": np.where(
                    (np.arange(0.0, 200.0, 5.0) >= 45)
                    & (np.arange(0.0, 200.0, 5.0) <= 55),
                    90.0,
                    50.0,
                ),
                "brake_active": 0.0,
                "engine_rpm": 3600.0,
                "cvt_ratio": 2.5,
                "wheel_speed_kmh": 42.0,
            }
        )
        laps = pd.DataFrame({"lap_id": [1], "analysis_valid": [True]})
        feature = pd.DataFrame(
            [{
                "sequence": 1,
                "name": "Test obstacle",
                "analysis_role": "track_event",
                "final_group_id": "E01",
                "anchor_s_m": 50.0,
                "feature_start_rel_m": -5.0,
                "feature_end_rel_m": 5.0,
                "source_members": "Test obstacle",
            }]
        )
        feature = add_event_geometry(feature, centreline.length_m)
        result = extract_event_passes(
            matched,
            laps,
            feature,
            {1: profile},
            centreline,
            PipelineConfig(),
            1.0,
        ).iloc[0]
        self.assertGreater(result["entry_speed_kmh"], result["event_min_speed_kmh"])
        self.assertGreater(result["specific_ke_change_to_min_j_per_kg"], 0.0)
        expected = 0.5 * ((result["entry_speed_kmh"] / 3.6) ** 2 - (result["event_min_speed_kmh"] / 3.6) ** 2)
        self.assertAlmostEqual(result["specific_ke_change_to_min_j_per_kg"], expected)
        self.assertGreater(result["event_time_s"], 0.0)
        self.assertEqual(result["full_throttle_fraction_event"], 1.0)
        self.assertEqual(result["positive_driver_demand_fraction_event"], 1.0)
        self.assertEqual(result["entry_engine_rpm"], 3600.0)
        self.assertEqual(result["event_cvt_ratio_median"], 2.5)
        self.assertGreater(result["event_wheel_slip_proxy_median"], 0.0)
        self.assertNotIn("driver_demand_unknown", result["quality_flags"])


if __name__ == "__main__":
    unittest.main()
