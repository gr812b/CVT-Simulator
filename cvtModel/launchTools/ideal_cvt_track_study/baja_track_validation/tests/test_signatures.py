from __future__ import annotations

from pathlib import Path
import unittest

from baja_track_analysis.config import PipelineConfig, SignatureConfig
from baja_track_analysis.signatures import classify_signature, run_signature_analysis


class SignatureTests(unittest.TestCase):
    def test_classification_thresholds_are_explicit(self) -> None:
        config = SignatureConfig()
        self.assertEqual(
            classify_signature(
                valid_laps=11,
                track_percentile=80.0,
                slowdown_lap_fraction=0.80,
                config=config,
            ),
            "STRONG",
        )
        self.assertEqual(
            classify_signature(
                valid_laps=11,
                track_percentile=60.0,
                slowdown_lap_fraction=0.40,
                config=config,
            ),
            "MODERATE",
        )
        self.assertEqual(
            classify_signature(
                valid_laps=11,
                track_percentile=30.0,
                slowdown_lap_fraction=0.20,
                config=config,
            ),
            "WEAK",
        )
        self.assertEqual(
            classify_signature(
                valid_laps=5,
                track_percentile=99.0,
                slowdown_lap_fraction=1.0,
                config=config,
            ),
            "INSUFFICIENT_LAPS",
        )

    def test_cleaned_reference_run_reproduces_signature_counts(self) -> None:
        project = Path(__file__).resolve().parents[1]
        result = run_signature_analysis(
            project / "examples/reference_run_gps.csv",
            project / "examples/obstacle_event_definitions_CLEANED.csv",
            config=PipelineConfig.from_toml(project / "examples/config.example.toml"),
        )
        counts = result.signatures["slowdown_signature"].value_counts()
        self.assertEqual(int(counts["STRONG"]), 21)
        self.assertEqual(int(counts["MODERATE"]), 11)
        self.assertEqual(int(counts["WEAK"]), 8)
        self.assertTrue(result.analysis.projected_definitions["anchor_s_m"].is_monotonic_increasing)
        self.assertLess(result.signatures["anchor_projection_error_m"].max(), 12.0)


if __name__ == "__main__":
    unittest.main()
