from __future__ import annotations

from types import SimpleNamespace

from app.engineering.fixed_pivot_primary.architecture_compare import match_target_shape
from app.engineering.fixed_pivot_primary.models import ArchitectureDesign


def _architecture() -> ArchitectureDesign:
    return ArchitectureDesign(
        pivot_axial_position_m=0.0,
        pivot_radius_m=42.545e-3,
        arm_length_m=31.5214e-3,
        roller_radius_m=6.5e-3,
        required_travel_m=19.05e-3,
        number_of_flyweights=3,
        arm_mass_per_flyweight_kg=13.646e-3,
        ramp_axial_direction=-1,
        roller_side_sign=1,
        max_tip_mass_per_flyweight_kg=0.650,
    )


def _domain(architecture: ArchitectureDesign):
    # Target-shape matching is deliberately independent of the discrete graph.
    # A tiny domain-like object is enough: the continuous inverse only needs the
    # architecture, packaging zones, and history trace resolution.
    return SimpleNamespace(
        architecture=architecture,
        zones=(),
        history_trace_sample_count=65,
    )


def test_falling_target_uses_continuous_inverse_and_matches_closely(monkeypatch) -> None:
    import app.engineering.fixed_pivot_primary.architecture_compare as compare

    # Regression for the visibly bad Phase-3.9 result: a smooth falling request
    # was being matched only against a small sampled path atlas, so the "closest"
    # returned curves were oscillatory and qualitatively wrong.
    target = [
        (0.00, 178.0),
        (0.25, 118.0),
        (0.50, 95.0),
        (0.75, 92.0),
        (1.00, 16.0),
    ]

    monkeypatch.setattr(
        compare,
        "_certified_atlas",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("target matching must not query the sampled path atlas")
        ),
    )

    domain = _domain(_architecture())
    result = match_target_shape(
        domain,
        domain,
        target,
        atlas_path_count=8,  # compatibility argument; must be ignored here
        mass_mix_count=5,
        sample_count=81,
    )

    a = result["architecture_a"]
    b = result["architecture_b"]
    assert a is not None and b is not None
    assert a["continuous_inverse"] is True
    assert b["continuous_inverse"] is True

    # Intentionally loose compared with the near-numerical-noise smoke result.
    # This catches the old atlas-neighbour regression without making harmless
    # solver tuning a test failure.
    assert a["rms_shape_error"] < 0.01
    assert b["rms_shape_error"] < 0.01
    assert a["max_shape_error"] < 0.03
    assert b["max_shape_error"] < 0.03
