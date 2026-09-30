"""Regression for localized-prep belt run-count reporting.

The moving-state raw-hash loop must not shadow the expected publication-run set.
The accepted plan has 42 runs while a SHA-256 string has 64 characters; the
old shadowing bug therefore reported 64 despite all 42 runs being checked.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

import numpy as np

from results_health import belt


class BeltRunCountReportingTest(unittest.TestCase):
    def test_count_comes_from_run_plan_not_hash_length(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); inputs = root / "inputs"; inputs.mkdir()
            plan = [
                {"case": f"case{i}", "level": level, "variant": variant}
                for i in range(7) for level in ("first", "tight")
                for variant in ("full", "joint", "density03")
            ]
            self.assertEqual(len(plan), 42)
            expected_names = {"{case}_{level}_{variant}".format(**r) for r in plan}
            (inputs / "run_plan.json").write_text(json.dumps(plan))
            raw_hash = "a" * 64
            audit = {"runs": {name: {} for name in expected_names},
                     "plot_inputs_sha256": "main", "raw_sha256": {"x/y.csv": raw_hash}}
            (inputs / "belt_publication_audit.json").write_text(json.dumps(audit))
            (inputs / "belt_events.json").write_text(json.dumps({name: [] for name in expected_names}))
            provenance = {"raw_sha256": {"x/y.csv": raw_hash}}
            np.savez_compressed(inputs / "belt_moving_state_samples.npz",
                                metadata=np.array(json.dumps(provenance)))
            moving = {"input_sha256": "moving", "provenance": provenance}
            (inputs / "belt_moving_state_audit.json").write_text(json.dumps(moving))
            runtime = root / "runtime.json"; runtime.write_text(json.dumps({"source_sha256": {}}))
            fake_cinder = types.SimpleNamespace(__file__=str(root / "cinder" / "__init__.py"))
            with mock.patch.object(belt, "verify_bundle", return_value=6), \
                 mock.patch.object(belt, "digest", side_effect=lambda p: {"belt_publication.npz":"main", "belt_moving_state_samples.npz":"moving"}.get(Path(p).name, "unused")), \
                 mock.patch.object(belt, "verify_hashes", return_value=0), \
                 mock.patch.object(belt, "belt_run_findings", return_value=[]), \
                 mock.patch.dict(sys.modules, {"cinder": fake_cinder}):
                result = belt.check_publication(inputs, root / "missing_raw", runtime)
            self.assertEqual(result["run_count"], 42)
            self.assertNotEqual(result["run_count"], len(raw_hash))


if __name__ == "__main__":
    unittest.main()
