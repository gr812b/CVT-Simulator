"""Focused scientific regression checks; run from the study directory."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis.evidence import gross_rms, digest, write_json, verify_record
from analysis.verification import passes, formal_module, audit, STUDY


class IntegrityTests(unittest.TestCase):
    def test_changed_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "sample.csv"
            data.write_text("time,value\n0,1\n")
            write_json(root / "execution_provenance.json", {
                "input_sha256": {}, "output_sha256": {"sample.csv": digest(data)},
                "mechanics_commit": "7637a38b4fb9ec21dfb953c1c80a27ec5f389654",
            })
            verify_record(root)
            data.write_text("time,value\n0,2\n")
            with self.assertRaisesRegex(ValueError, "Changed evidence"):
                verify_record(root)

    def test_count_does_not_establish_signature(self):
        formal = formal_module()
        a = [{"fired_event_names": "contact", "next_mode": "stick", "has_successor_state": True}]
        b = copy.deepcopy(a)
        b[0]["next_mode"] = "slip"
        self.assertEqual(len(a), len(b))
        self.assertNotEqual(formal.signature(a), formal.signature(b))
        b = copy.deepcopy(a)
        b[0]["has_successor_state"] = False
        self.assertNotEqual(formal.signature(a), formal.signature(b))

    def test_small_rms_cannot_hide_failed_maximum(self):
        guard = dict(trajectory_rms_normalized=1e-4, trajectory_max_abs_normalized=1e-3,
                     maximum_event_time_error_s=1e-3, regime_mismatch_fraction=1e-3)
        row = {k: v/100 for k, v in guard.items()}
        row.update(run_status="completed", transition_signature_match=True)
        self.assertTrue(passes(row, guard))
        row["trajectory_max_abs_normalized"] = .00101
        self.assertFalse(passes(row, guard))

    def test_exact_duration_keeps_microsecond_interval(self):
        f = formal_module()
        ref = [dict(start_time_s=0., end_time_s=.5, mode="a"),
               dict(start_time_s=.5, end_time_s=1., mode="b")]
        cand = [dict(start_time_s=0., end_time_s=.500001, mode="a"),
                dict(start_time_s=.500001, end_time_s=1., mode="b")]
        self.assertAlmostEqual(f.exact_regime_mismatch_fraction(cand, ref), 1e-6, places=14)

    def test_gross_diagnostic_excludes_shift_speed(self):
        row = {"raw_time_"+k+"_rms_normalized": 2e-4 for k in (
            "primary_omega_rad_s", "secondary_omega_rad_s", "belt_speed_m_s", "shift_m")}
        row["raw_time_shift_speed_m_s_rms_normalized"] = 1e6
        self.assertEqual(gross_rms(row), 2e-4)

    def test_native_endpoint_and_zero_duration_audit(self):
        values, _, _, _, caches = audit(STUDY / "artifacts")
        self.assertEqual(caches["reference"]["velocity_jump_count"], 13)
        self.assertEqual(sum(r["has_successor_state"] for r in caches["reference"]["events"]), 16)
        selected = caches["selected"]["segments"]
        self.assertTrue(any(r["start_time_s"] == r["end_time_s"] for r in selected))
        self.assertEqual(len(caches["selected"]["events"]), 12)


if __name__ == "__main__":
    unittest.main()
