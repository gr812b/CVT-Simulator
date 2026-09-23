"""Checks for event/censoring and CSV semantics that could change a paper claim."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis.publication_plots import first_exit, read_rows, minimum


class PublicationSelectionTests(unittest.TestCase):
    def test_no_exit_is_a_lower_bound(self):
        samples = [{"time_s": "0", "sample_location": "segment_start"},
                   {"time_s": ".03", "sample_location": "segment_end"}]
        result = first_exit(samples, [], .03)
        self.assertTrue(result["lower_bound"])
        self.assertEqual(result["dwell_s"], .03)
        samples[-1]["time_s"] = ".02"
        with self.assertRaisesRegex(ValueError, "complete audit window"):
            first_exit(samples, [], .03)

    def test_event_name_does_not_imply_sticking(self):
        samples = [{"time_s": "0", "sample_location": "segment_start"},
                   {"time_s": ".001", "sample_location": "segment_end"},
                   {"time_s": ".001", "sample_location": "segment_start"},
                   {"time_s": ".03", "sample_location": "segment_end"}]
        event = {"time_s": ".001", "successor_exists": True,
                 "fired_event_names": "cvt:primary_restick", "contact_mode": "both_slip",
                 "transition_reason": "kinetic_slip_direction_updated_at_zero_crossing"}
        result = first_exit(samples, [event], .03)
        self.assertFalse(result["lower_bound"])
        self.assertEqual(result["successor_contact"], "both_slip")
        event["time_s"] = ".002"
        with self.assertRaisesRegex(ValueError, "initial segment end"):
            first_exit(samples, [event], .03)

    def test_event_sides_remain_separate_at_equal_time(self):
        rows = [{"time_s": ".001757", "local": "45.60", "total": "374.31"},
                {"time_s": ".001757", "local": ".0482", "total": "410.85"}]
        matched = min(rows, key=lambda r: float(r["local"]))
        self.assertEqual(minimum(rows, "local"), .0482)
        self.assertEqual(float(matched["total"]), 410.85)
        self.assertNotEqual(float(matched["total"]), minimum(rows, "total"))

    def test_csv_false_is_not_truthy_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rows.csv"
            path.write_text("case_id,successor_exists\na,False\nb,True\n")
            rows = read_rows(path)
            self.assertIs(rows[0]["successor_exists"], False)
            self.assertIs(rows[1]["successor_exists"], True)


if __name__ == "__main__":
    unittest.main()
