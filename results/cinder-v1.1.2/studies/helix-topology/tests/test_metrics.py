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


from pathlib import Path
import sys
import unittest

STUDY_ROOT = Path(__file__).resolve().parents[1]
if str(STUDY_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDY_ROOT))

from infrastructure.metrics import (  # noqa: E402
    contact_topology_metrics,
    deduplicate_by_time,
    integrate_abs_value_where_driver_negative,
    integrate_negative_part,
)


class HelixTopologyMetricTests(unittest.TestCase):
    def test_negative_triangle(self):
        result = integrate_negative_part([0.0, 1.0, 2.0], [1.0, -1.0, 1.0])
        self.assertAlmostEqual(result.duration_s, 1.0)
        self.assertAlmostEqual(result.impulse, 0.5)
        self.assertAlmostEqual(result.first_entry_time_s, 0.5)
        self.assertEqual(result.crossing_count, 2)

    def test_entirely_negative(self):
        result = integrate_negative_part([0.0, 2.0], [-2.0, -4.0])
        self.assertAlmostEqual(result.duration_s, 2.0)
        self.assertAlmostEqual(result.impulse, 6.0)
        self.assertEqual(result.first_entry_time_s, 0.0)
        self.assertEqual(result.crossing_count, 0)

    def test_force_impulse_is_conditioned_on_torque_margin(self):
        value = integrate_abs_value_where_driver_negative(
            [0.0, 1.0, 2.0],
            [1.0, -1.0, 1.0],
            [10.0, 20.0, 30.0],
        )
        # Negative driver from 0.5 to 1.5.  Interpolated |force| endpoints are
        # 15 and 25 N, giving 20 N s over one second.
        self.assertAlmostEqual(value, 20.0)

    def test_duplicate_event_time_keeps_post_event_row(self):
        rows = [
            {"time_s": 0.0, "value": "a"},
            {"time_s": 1.0, "value": "pre"},
            {"time_s": 1.0, "value": "post"},
            {"time_s": 2.0, "value": "b"},
        ]
        unique = deduplicate_by_time(rows)
        self.assertEqual([row["value"] for row in unique], ["a", "post", "b"])

    def test_unresolved_gap_is_not_bridged(self):
        rows = [
            {"time_s": 0.0, "helix_reacted_torque_margin_Nm": 1.0, "helix_full_reaction_force_N": 10.0},
            {"time_s": 1.0, "helix_reacted_torque_margin_Nm": -1.0, "helix_full_reaction_force_N": -10.0},
            {"time_s": 2.0, "helix_reacted_torque_margin_Nm": float("nan"), "helix_full_reaction_force_N": float("nan")},
            {"time_s": 3.0, "helix_reacted_torque_margin_Nm": -1.0, "helix_full_reaction_force_N": -10.0},
            {"time_s": 4.0, "helix_reacted_torque_margin_Nm": 1.0, "helix_full_reaction_force_N": 10.0},
        ]
        metrics = contact_topology_metrics(rows, case_start_s=0.0, case_end_s=4.0)
        self.assertAlmostEqual(metrics["resolved_margin_span_s"], 2.0)
        self.assertAlmostEqual(metrics["opposite_flank_duration_s"], 1.0)
        self.assertAlmostEqual(metrics["D_opp_engaged"], 0.5)

    def test_case_metrics(self):
        rows = [
            {"time_s": 0.0, "helix_reacted_torque_margin_Nm": 2.0, "helix_full_reaction_force_N": 20.0},
            {"time_s": 1.0, "helix_reacted_torque_margin_Nm": -2.0, "helix_full_reaction_force_N": -20.0},
            {"time_s": 2.0, "helix_reacted_torque_margin_Nm": 2.0, "helix_full_reaction_force_N": 20.0},
        ]
        metrics = contact_topology_metrics(rows, case_start_s=0.0, case_end_s=4.0)
        self.assertAlmostEqual(metrics["opposite_flank_duration_s"], 1.0)
        self.assertAlmostEqual(metrics["D_opp_case"], 0.25)
        self.assertAlmostEqual(metrics["D_opp_engaged"], 0.5)
        self.assertAlmostEqual(metrics["I_opp_tau_Nm_s"], 1.0)
        self.assertEqual(metrics["zero_crossing_count"], 2)


if __name__ == "__main__":
    unittest.main()


def test_sign_partition_detects_dynamic_only_interval():
    from infrastructure.metrics import integrate_sign_partition

    result = integrate_sign_partition(
        [0.0, 1.0, 2.0],
        [1.0, -1.0, 1.0],
        [2.0, 1.0, 2.0],
    )
    assert abs(result.full_negative_qs_positive_s - 1.0) < 1.0e-12
    assert result.both_negative_s == 0.0
    assert abs(result.first_full_negative_qs_positive_time_s - 0.5) < 1.0e-12


def test_first_negative_entry_interpolates_companion():
    from infrastructure.metrics import first_negative_entry_with_companion

    time_s, companion = first_negative_entry_with_companion(
        [0.0, 1.0],
        [2.0, -2.0],
        [4.0, 2.0],
    )
    assert abs(time_s - 0.5) < 1.0e-12
    assert abs(companion - 3.0) < 1.0e-12
