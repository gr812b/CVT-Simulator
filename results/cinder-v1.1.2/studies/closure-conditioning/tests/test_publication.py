"""Checks for scientific distinctions that would change the published claims.

Run after importing the registered evidence; no simulation is performed.
"""
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np

STUDY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STUDY))
from analysis.evidence import MECHANICS, digest, rows, verify_record, write_json
from analysis.verification import census, expanded_census, verify_map


class PublicationIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.full = STUDY / "artifacts/reviewed/full"
        cls.actual = {r["label"]:r for r in rows(cls.full / "actual_root_state_scan.csv")}

    def test_reduced_start_grid_cannot_be_reported_as_full(self):
        results = rows(self.full / "multistart_results.csv")
        summaries = rows(self.full / "multistart_summary.csv")
        self.assertEqual(sum(r["accepted"] for r in census(results, summaries, self.actual)), 666)
        reduced = [r for r in results if r["start_lambda_p"] <= 0]
        with self.assertRaises(ValueError):
            census(reduced, summaries, self.actual)

    def test_expanded_census_cannot_lose_failed_start(self):
        results = rows(self.full / "expanded_multistart_results.csv")
        summaries = rows(self.full / "expanded_multistart_summary.csv")
        self.assertEqual(sum(r["accepted"] for r in expanded_census(results, summaries, self.actual)), 163)
        self.assertFalse(results[0]["accepted"])
        with self.assertRaises(ValueError):
            expanded_census(results[1:], summaries, self.actual)

    def test_static_box_does_not_imply_compressive_contact(self):
        with np.load(self.full / "states/upper_stop/physical_map.npz") as source:
            data = {k:source[k].copy() for k in source.files}
        s = next(r for r in rows(self.full / "domain_conditioning_summary.csv")
                 if r["state"] == "upper_stop" and r["domain"] == "physical")
        verify_map(data, s)
        ij = np.unravel_index(np.argmax(data["cond_A_scaled"]), data["cond_A_scaled"].shape)
        self.assertTrue(data["static_capacity_admissible"][ij])
        self.assertLess(data["min_belt_tension"][ij], 0)
        self.assertFalse(data["full_static_admissible"][ij])
        data["topology_failure_code"][ij] = 0
        with self.assertRaises(ValueError):
            verify_map(data, s)

    def test_roots_share_loading_but_not_acceleration(self):
        roots = rows(STUDY / "artifacts/reviewed/selected_audit/two_contact_roots.csv")
        self.assertEqual(roots[0]["primary_boundary_torque_Nm"], roots[1]["primary_boundary_torque_Nm"])
        self.assertEqual(roots[0]["secondary_boundary_torque_Nm"], roots[1]["secondary_boundary_torque_Nm"])
        self.assertTrue(all(r["physical"] and r["bilateral_physical"] for r in roots))
        self.assertGreater(abs(roots[0]["shift_acceleration_m_s2"]-roots[1]["shift_acceleration_m_s2"]), 10)
        self.assertLess(max(np.hypot(r["R_p"],r["R_s"]) for r in roots), 1e-6)

    def test_mixed_root_only_constrains_secondary_acceleration(self):
        roots = rows(STUDY / "artifacts/reviewed/selected_audit/one_contact_roots.csv")
        self.assertTrue(all(abs(r["R_s"])<1e-6 and r["R_p"]>0 and r["lambda_p"]==-.55 for r in roots))
        self.assertLess(roots[0]["dR_s_dlambda_s_m_s2"]*roots[1]["dR_s_dlambda_s_m_s2"], 0)
        self.assertGreater(roots[1]["N_s_N"], 1000)
        self.assertLess(roots[1]["min_local_normal_s_N_per_rad"], .01)

    def test_changed_evidence_is_rejected_before_plotting(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p / "data.json").write_text('{}\n')
            write_json(p / "execution_provenance.json", dict(mechanics_commit=MECHANICS,
                input_sha256={}, output_sha256={"data.json":digest(p / "data.json")}))
            verify_record(p)
            (p / "data.json").write_text('{"changed":true}\n')
            with self.assertRaises(ValueError):
                verify_record(p)


if __name__ == "__main__":
    unittest.main()
