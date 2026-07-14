from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

import pandas as pd

from baja_track_analysis.definitions import DefinitionValidationError, load_definition_csv


FORM_COLUMNS = [
    "sequence", "name", "analysis_role", "kind", "anchor_latitude", "anchor_longitude",
    "anchor_s_m_reference", "anchor_projection_error_m_reference", "corrected_anchor_latitude",
    "corrected_anchor_longitude", "extent_method", "event_start_latitude", "event_start_longitude",
    "event_end_latitude", "event_end_longitude", "candidate_group", "candidate_members",
    "final_group_id", "grouping_notes", "required_action", "annotator_notes",
]


def row(sequence: int, name: str, kind: str = "point") -> dict[str, object]:
    interval = kind == "interval"
    return {
        "sequence": sequence,
        "name": name,
        "analysis_role": "track_event",
        "kind": kind,
        "anchor_latitude": 43.0 + sequence * 0.0001,
        "anchor_longitude": -79.0,
        "anchor_s_m_reference": sequence * 10,
        "anchor_projection_error_m_reference": 1,
        "corrected_anchor_latitude": "N/A",
        "corrected_anchor_longitude": "N/A",
        "extent_method": "GPS_START_END_REQUIRED" if interval else "AUTO_POINT_WINDOW",
        "event_start_latitude": 43.0 + sequence * 0.0001 - 0.00002 if interval else "N/A",
        "event_start_longitude": -79.0 if interval else "N/A",
        "event_end_latitude": 43.0 + sequence * 0.0001 + 0.00002 if interval else "N/A",
        "event_end_longitude": -79.0 if interval else "N/A",
        "candidate_group": "N/A",
        "candidate_members": "N/A",
        "final_group_id": f"E{sequence:02d}",
        "grouping_notes": "SEPARATE",
        "required_action": "NONE",
        "annotator_notes": "",
    }


class DefinitionTests(unittest.TestCase):
    def write(self, rows: list[dict[str, object]], directory: str) -> Path:
        path = Path(directory) / "definitions.csv"
        pd.DataFrame(rows, columns=FORM_COLUMNS).to_csv(path, index=False)
        return path

    def test_strict_mode_rejects_fill(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = [row(1, "Gate"), row(2, "Ruts", "interval")]
            data[1]["event_start_latitude"] = "FILL"
            path = self.write(data, directory)
            with self.assertRaises(DefinitionValidationError):
                load_definition_csv(path)

    def test_allow_incomplete_records_warning_and_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = [row(1, "Gate"), row(2, "Ruts", "interval")]
            for field in ("event_start_latitude", "event_start_longitude", "event_end_latitude", "event_end_longitude"):
                data[1][field] = "FILL"
            path = self.write(data, directory)
            definitions, issues = load_definition_csv(path, allow_incomplete=True)
            self.assertTrue(definitions.loc[1, "compound_group"] == "SEPARATE")
            self.assertIn("unresolved_interval_extent", issues["code"].tolist())

    def test_repeated_group_id_becomes_compound_group(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = [row(1, "Gate"), row(2, "Bump"), row(3, "Turn", "turn_apex")]
            data[1]["final_group_id"] = "G02"
            data[2]["final_group_id"] = "G02"
            path = self.write(data, directory)
            definitions, _ = load_definition_csv(path)
            self.assertEqual(definitions.loc[1, "compound_group"], "G02")
            self.assertEqual(definitions.loc[2, "compound_group"], "G02")

    def test_invalid_optional_coordinate_is_not_silently_treated_as_na(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = [row(1, "Gate")]
            data[0]["corrected_anchor_latitude"] = "not-a-coordinate"
            path = self.write(data, directory)
            with self.assertRaises(DefinitionValidationError):
                load_definition_csv(path)


if __name__ == "__main__":
    unittest.main()
