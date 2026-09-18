from __future__ import annotations

# --- results study-local import bootstrap ---
from pathlib import Path as _ResultsPath
import sys as _results_sys

_results_file = _ResultsPath(__file__).resolve()
_results_study_root = next(
    (parent for parent in _results_file.parents if (parent / "study.json").is_file()),
    None,
)
if _results_study_root is None:
    raise RuntimeError(f"Could not locate study root for {_results_file}")
_results_release_root = _results_study_root.parents[1]
for _results_path in (str(_results_study_root), str(_results_release_root)):
    while _results_path in _results_sys.path:
        _results_sys.path.remove(_results_path)
_results_sys.path.insert(0, str(_results_release_root))
_results_sys.path.insert(0, str(_results_study_root))
# --- end results study-local import bootstrap ---


import copy
import sys
import unittest
from pathlib import Path

STUDY_ROOT = Path(__file__).resolve().parents[1]
if str(STUDY_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDY_ROOT))

from experiments.closure_design import (
    ContactStressCase,
    apply_belt_density_scale,
    apply_contact_stress,
    build_contact_stress_cases,
    build_inertia_continuations,
)


def document():
    return {
        "assembly": {
            "inertias": {"belt_density_kg_per_m3": 1100.0},
            "pulleys": {
                "primary": {"components": [{
                    "kind": "fixed_pivot_roller_flyweight",
                    "mass_geometry": {
                        "mass_per_flyweight_kg": 1.0,
                        "first_moment_u_kg_m": 2.0,
                        "first_moment_v_kg_m": 3.0,
                        "second_moment_u_kg_m2": 4.0,
                        "second_moment_v_kg_m2": 5.0,
                        "product_moment_uv_kg_m2": 6.0,
                        "second_moment_z_kg_m2": 7.0,
                    },
                }]},
                "secondary": {"components": [
                    {"kind": "axial_spring", "stiffness_N_per_m": 100.0},
                    {"kind": "helical_torque_reaction", "torsional_stiffness_Nm_per_rad": 20.0},
                ]},
            },
        }
    }


class ClosureDesignTests(unittest.TestCase):
    def test_contact_stress_scales_only_requested_actuation_quantities(self):
        d = document()
        case = ContactStressCase(
            name="x", title="x", primary_flyweight_scale=0.7, secondary_reaction_scale=0.5
        )
        apply_contact_stress(d, case)
        mass = d["assembly"]["pulleys"]["primary"]["components"][0]["mass_geometry"]
        self.assertAlmostEqual(mass["mass_per_flyweight_kg"], 0.7)
        self.assertAlmostEqual(mass["second_moment_z_kg_m2"], 4.9)
        sec = d["assembly"]["pulleys"]["secondary"]["components"]
        self.assertAlmostEqual(sec[0]["stiffness_N_per_m"], 50.0)
        self.assertAlmostEqual(sec[1]["torsional_stiffness_Nm_per_rad"], 10.0)

    def test_density_scale_is_coherent_single_parameter(self):
        d = document()
        apply_belt_density_scale(d, 0.03)
        self.assertAlmostEqual(d["assembly"]["inertias"]["belt_density_kg_per_m3"], 33.0)

    def test_designs_are_sparse_and_include_both_asymmetries(self):
        cases = build_contact_stress_cases()
        self.assertEqual(len(cases), 13)
        self.assertTrue(any(c.primary_flyweight_scale < 1 and c.secondary_reaction_scale == 1 for c in cases))
        self.assertTrue(any(c.secondary_reaction_scale < 1 and c.primary_flyweight_scale == 1 for c in cases))
        self.assertTrue(any(c.secondary_reaction_scale < 1 and c.primary_flyweight_scale < 1 for c in cases))
        inertia = build_inertia_continuations()
        self.assertEqual(len(inertia), 15)
        self.assertEqual({c.scenario for c in inertia}, {"flat", "fast_backshift", "fast_unload"})


if __name__ == "__main__":
    unittest.main()
