from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

import pandas as pd

from baja_track_analysis.telemetry import attach_optional_telemetry


class TelemetryTests(unittest.TestCase):
    def test_aliases_and_boolean_values_are_attached_by_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gps.csv"
            timestamps = pd.date_range("2026-01-01", periods=3, freq="s")
            raw = pd.DataFrame(
                {
                    "timestamp": timestamps,
                    "throttle_percent": [25, 80, 100],
                    "brake_pressed": ["no", "yes", "no"],
                    "rpm": [3000, 3500, 4000],
                }
            )
            raw.to_csv(path, index=False)
            cleaned = pd.DataFrame({"timestamp": timestamps, "lat": 43.0, "lon": -79.0})

            attached, channels = attach_optional_telemetry(cleaned, path)

            self.assertEqual(channels, ["throttle_pct", "brake_active", "engine_rpm"])
            self.assertEqual(attached["throttle_pct"].tolist(), [25.0, 80.0, 100.0])
            self.assertEqual(attached["brake_active"].tolist(), [0.0, 1.0, 0.0])
            self.assertEqual(attached["engine_rpm"].tolist(), [3000.0, 3500.0, 4000.0])


if __name__ == "__main__":
    unittest.main()
