"""Selection tests: signed quantities, physical masks and enumeration."""
import importlib.util
from pathlib import Path
import sys
import unittest

STUDY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STUDY))
from analysis.reader_evidence import CASE_GROUPS, STICKING, extremum, numbers


class ReaderEvidenceTests(unittest.TestCase):
    def row(self, **kw):
        return {"case_id": "test", "time_s": "0", "sample_location": "segment_start", **kw}

    def test_each_selected_case_exactly_once(self):
        cases = [c for group in CASE_GROUPS.values() for c in group]
        self.assertEqual(len(cases), 18)
        self.assertEqual(len(cases), len(set(cases)))
        self.assertNotIn("boundary_upper_stop_arrival", cases)

    def test_sticking_drift_excludes_sliding_and_deadzone(self):
        rr = [self.row(engagement="engaged", contact_mode="primary_slip_secondary_stick",
                       primary_vrel_m_s="30", secondary_vrel_m_s="-0.00013"),
              self.row(engagement="deadzone", contact_mode="", primary_vrel_m_s="nan", secondary_vrel_m_s="nan")]
        got = extremum(numbers(rr, ["vrel_m_s"], interfaces=STICKING))
        self.assertEqual(got["value"], -0.00013)
        self.assertEqual(got["applicable_values"], 1)

    def test_negative_roundoff_is_not_zeroed(self):
        rr = [self.row(margin="0.2"), self.row(margin="-8.88e-16")]
        self.assertEqual(extremum(numbers(rr, ["margin"]), "min")["value"], -8.88e-16)

    def test_exact_outgoing_extremum_is_kept(self):
        rr = [self.row(value="2.82e-11"), self.row(value="3.50e-11", sample_location="post_transition_exact")]
        self.assertEqual(extremum(numbers(rr, ["value"]))["sample_location"], "post_transition_exact")

    def test_missing_applicable_quantity_fails(self):
        with self.assertRaises(ValueError):
            list(numbers([self.row(value="nan")], ["value"]))


if __name__ == "__main__":
    unittest.main()
