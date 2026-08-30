from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
LAUNCH = ROOT / "launchTools"

if str(LAUNCH) not in sys.path:
    sys.path.insert(0, str(LAUNCH))

import run_route_grade_response as route  # noqa: E402


def test_launch_tool_defaults_are_physical_fixed_pivot_only() -> None:
    candidate = route.TuneCandidate()
    constants = route.BajaTrialConstants()

    assert candidate.tip_hardware_mass_per_flyweight_kg == 0.25
    assert candidate.helix_angle_degrees == 20.0
    assert candidate.secondary_torsional_pretension_degrees == 300.0
    assert candidate.secondary_compression_preload_mm == 110.0
    assert candidate.primary_linear_ramp_angle_degrees == 35.0
    assert candidate.primary_circular_ramp_start_angle_degrees == 35.0
    assert candidate.primary_circular_ramp_end_angle_degrees == 20.0

    assert constants.tip_hardware_mass_per_flyweight == 0.25
    assert constants.helix_angle_degrees == 20.0
    assert constants.secondary_spring_initial_compression == 0.11
    assert constants.primary_linear_ramp_angle_degrees == 35.0
    assert constants.primary_circular_ramp_start_angle_degrees == 35.0
    assert constants.primary_circular_ramp_end_angle_degrees == 20.0
    assert constants.final_drive_ratio == 7.556

    assert not hasattr(candidate, "primary_ramp_kind")
    assert not hasattr(constants, "primary_ramp_kind")
    assert not hasattr(constants, "initial_flyweight_radius")


def test_single_launch_preset_matches_default_candidate() -> None:
    presets = sorted(path.name for path in (LAUNCH / "presets").glob("*.json"))
    assert presets == ["fixed_pivot_3200_reference.json"]

    payload = json.loads(route.DEFAULT_FIXED_PIVOT_PRESET.read_text(encoding="utf-8"))
    loaded = route.load_candidate(route.DEFAULT_FIXED_PIVOT_PRESET)
    assert loaded == route.TuneCandidate()

    candidate = payload["candidate"]
    assert "primary_ramp_kind" not in candidate
    assert "flyweight_mass_kg" not in candidate
    assert candidate["tip_hardware_mass_per_flyweight_kg"] == 0.25


def test_direct_default_assembly_installs_fixed_pivot_flyweight() -> None:
    assembly, _engine, _road_load = route.build_components(route.BajaTrialConstants())
    law_names = {
        type(law).__name__ for law in assembly.pulleys.primary.actuator.force_laws
    }
    assert "FixedPivotFlyweightForce" in law_names
    assert "CentrifugalRampForce" not in law_names


def test_active_launch_surface_contains_no_legacy_default_tokens() -> None:
    forbidden = (
        "circular_traction_first_reference",
        "linear_slow_reference",
        "primary_ramp_kind",
        "initial_flyweight_radius",
        "flyweight_mass_kg",
        "CentrifugalRampForce",
        "build_centrifugal_actuator",
    )
    for path in LAUNCH.rglob("*"):
        if not path.is_file() or path.suffix not in {".py", ".md", ".json"}:
            continue
        if "literature" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{path}: legacy token {token!r}"
