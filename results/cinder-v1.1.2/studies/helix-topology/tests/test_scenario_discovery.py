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


import json
from pathlib import Path
import sys

STUDY_ROOT = Path(__file__).resolve().parents[1]
if str(STUDY_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDY_ROOT))

from experiments.run_scenario_discovery import (  # noqa: E402
    build_cases,
    legacy_hill_specs,
    minimum_margin_decomposition,
)


def _cfg():
    study = json.loads((STUDY_ROOT / "study.json").read_text(encoding="utf-8"))
    return study["experiments"]["scenario_discovery"]


def test_full_discovery_matrix_covers_all_four_families():
    cases = build_cases(_cfg(), quick=False)
    counts = {}
    for case in cases:
        counts[case.family] = counts.get(case.family, 0) + 1
    assert counts == {
        "hill_entry": 12,
        "downhill_engine_braking": 24,
        "bench_backdrive": 18,
        "bench_resisting_load": 12,
    }
    assert len(cases) == 66


def test_quick_matrix_is_one_case_per_family():
    cases = build_cases(_cfg(), quick=True)
    assert len(cases) == 4
    assert {case.family for case in cases} == {
        "hill_entry",
        "downhill_engine_braking",
        "bench_backdrive",
        "bench_resisting_load",
    }


def test_bench_cases_treat_boundary_swap_as_transient_start():
    cases = build_cases(_cfg(), quick=False)
    bench = [case for case in cases if case.family.startswith("bench_")]
    assert bench
    assert {case.onset_s for case in bench} == {0.0}


def test_minimum_margin_decomposition_identifies_dynamic_driver():
    rows = [
        {
            "time_s": 0.1,
            "helix_reacted_torque_margin_Nm": 2.0,
            "helix_belt_reaction_torque_Nm": -1.0,
            "helix_torsional_spring_torque_Nm": 5.0,
            "helix_shaft_accel_reaction_torque_Nm": -1.0,
            "helix_shift_accel_reaction_torque_Nm": -1.0,
            "helix_curvature_reaction_torque_Nm": 0.0,
        },
        {
            "time_s": 0.2,
            "helix_reacted_torque_margin_Nm": -4.0,
            "helix_belt_reaction_torque_Nm": 1.0,
            "helix_torsional_spring_torque_Nm": 4.0,
            "helix_shaft_accel_reaction_torque_Nm": -8.0,
            "helix_shift_accel_reaction_torque_Nm": -1.0,
            "helix_curvature_reaction_torque_Nm": 0.0,
            "helix_secondary_closure_torque_Nm": 2.0,
            "helix_secondary_internal_power_W": -10.0,
            "shift_speed_m_s": 0.01,
        },
    ]
    result = minimum_margin_decomposition(rows)
    assert result["minimum_margin_time_s"] == 0.2
    assert result["minimum_margin_dominant_negative_term"] == "shaft_acceleration"
    assert result["minimum_margin_dynamic_sum_Nm"] == -9.0


def test_custom_torque_boundaries_have_expected_smoothstep_semantics(monkeypatch):
    import types
    from dataclasses import dataclass, field
    from types import SimpleNamespace

    @dataclass
    class FakeShaftBoundaryValue:
        external_torque: float
        equivalent_inertia: float
        metadata: dict = field(default_factory=dict)

    cinder = types.ModuleType("cinder")
    model = types.ModuleType("cinder.model")
    system = types.ModuleType("cinder.model.system")
    system.ShaftBoundaryValue = FakeShaftBoundaryValue
    monkeypatch.setitem(sys.modules, "cinder", cinder)
    monkeypatch.setitem(sys.modules, "cinder.model", model)
    monkeypatch.setitem(sys.modules, "cinder.model.system", system)

    from infrastructure.study_support import BlendToTorqueBoundary, PrescribedTorqueBoundary

    class Base:
        def evaluate(self, context):
            return FakeShaftBoundaryValue(10.0, 2.0, {"base": True})

    ctx = SimpleNamespace(time=0.5)
    blended = BlendToTorqueBoundary(
        Base(), onset_s=0.0, ramp_s=1.0, target_torque_Nm=-10.0
    ).evaluate(ctx)
    assert abs(blended.external_torque) < 1.0e-12
    assert blended.equivalent_inertia == 2.0
    assert blended.metadata["base"] is True

    prescribed = PrescribedTorqueBoundary(
        equivalent_inertia=3.0,
        onset_s=0.0,
        ramp_s=1.0,
        initial_torque_Nm=0.0,
        target_torque_Nm=100.0,
    ).evaluate(ctx)
    assert prescribed.external_torque == 50.0
    assert prescribed.equivalent_inertia == 3.0


def test_full_run_adds_exact_legacy_hill_and_harder_natural_replay():
    specs = legacy_hill_specs(_cfg(), quick=False)
    assert [item["case_id"] for item in specs] == [
        "E4_L01_legacy_ablation_hill",
        "E4_L02_natural_45deg_hill",
    ]
    assert specs[0]["kind"] == "tagged_route_default"
    assert specs[0]["analysis_start_s"] == 10.0
    assert specs[0]["analysis_end_s"] == 22.0
    assert specs[1]["kind"] == "natural_hard_hill"
    assert specs[1]["flat_runup_s"] == 10.0
    assert specs[1]["target_grade_deg"] == 45.0


def test_quick_mode_skips_long_legacy_hill_replays():
    assert legacy_hill_specs(_cfg(), quick=True) == []
