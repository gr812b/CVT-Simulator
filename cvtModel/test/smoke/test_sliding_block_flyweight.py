"""Physical, document and hybrid acceptance checks for sliding-block weights."""

from dataclasses import replace
from itertools import product
import json
from pathlib import Path

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from cinder.contracts import (
    decode_assembly_document,
    encode_assembly_document,
    validate_assembly,
    validate_assembly_document,
)
from cinder.contracts.document import _decode_force_law
from cinder.contracts.schema import assembly_document_json_schema
from cinder.execution.hybrid.cvt_impact import (
    CVTVelocityTopology,
    project_cvt_velocity_topology,
)
from cinder.execution.hybrid.cvt_operating_hybrid import CVTOperatingHybridSystem
from cinder.execution.hybrid.cvt_regime import CVTOperatingRegime
from cinder.model.cvt.actuation import (
    SlidingBlockFlyweightForce,
    SlidingBlockInertiaMap,
    PulleyActuator,
    PulleyActuationContext,
    PulleyClosureChannels,
    AxialSpringForce,
    AxialSpringForceSpec,
)
from cinder.model.cvt.actuation.sliding_block_geometry import evaluate as exact_evaluate
from cinder.model.cvt.closure import AffineClosureScalar, ClosureGains, ClosureUnknowns
from cinder.model.system import MechanicalCVTPlant
from cinder.model.system.state import CVTState

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def law(name="straight"):
    return _decode_force_law(
        json.loads((EXAMPLES / "sliding_block" / f"{name}.json").read_text())
    )


def context(x=0.0075, omega=280, xd=0.11, xdd=-8, primary=True):
    return PulleyActuationContext(
        time=0.2,
        axial_position=x,
        shaft_speed=omega,
        axial_speed=xd,
        axial_acceleration=AffineClosureScalar(
            bias=xdd - 2, gains=ClosureGains(shift_acceleration=2)
        ),
        closure_channels=(
            PulleyClosureChannels.primary()
            if primary
            else PulleyClosureChannels.secondary()
        ),
    )


def assembly(force=None):
    doc = json.loads((EXAMPLES / "baja_baseline_assembly.json").read_text())
    doc["geometry"]["max_shift_m"] = 0.015
    base = decode_assembly_document(doc)
    primary = replace(
        base.pulleys.primary,
        actuator=PulleyActuator(
            force or law(), *base.pulleys.primary.actuator.force_laws[1:]
        ),
    )
    return replace(base, pulleys=replace(base.pulleys, primary=primary))


def shifted_law(force, origin_shift):
    """Same physical assembly with x_new = x_old - origin_shift."""
    g = force.spec.geometry
    return SlidingBlockFlyweightForce(
        replace(
            force.spec,
            geometry=replace(
                g,
                upper_track=replace(
                    g.upper_track, offset=g.upper_track.offset + origin_shift
                ),
                axial_position_min=g.axial_position_min - origin_shift,
                axial_position_max=g.axial_position_max - origin_shift,
            ),
        )
    )


def particle_oracle(force, x, omega, alpha, xd, xdd):
    # Direct geometric positions only; no inertia-map derivatives or force law.
    offsets = np.array(
        list(
            product(
                (-0.002, 0.002),
                (-np.sqrt(0.000077), np.sqrt(0.000077)),
                (-0.004, 0.004),
            )
        )
    )
    m = replace(force.spec.geometry.mechanism(), total_mass=0.75, gyration_radius=0.009)

    def positions(x, theta):
        p = exact_evaluate(m, x, omega=0)
        c, s = np.cos(theta), np.sin(theta)
        return (offsets + (p.radial, 0, p.axial)) @ np.array(
            [[c, -s, 0], [s, c, 0], [0, 0, 1]]
        ).T

    h = 1e-4
    pos = {
        i: positions(
            x + xd * i * h + 0.5 * xdd * (i * h) ** 2,
            omega * i * h + 0.5 * alpha * (i * h) ** 2,
        )
        for i in (-2, -1, 0, 1, 2)
    }
    vel = (pos[-2] - 8 * pos[-1] + 8 * pos[1] - pos[2]) / (12 * h)
    acc = (-pos[2] + 16 * pos[1] - 30 * pos[0] + 16 * pos[-1] - pos[-2]) / (12 * h * h)
    virtual = (positions(x + 2e-5, 0) - positions(x - 2e-5, 0)) / 4e-5
    return (
        -0.75 / 8 * np.sum(acc * virtual),
        -0.75 / 8 * np.sum(np.cross(pos[0], acc)[:, 2]),
        0.5 * 0.75 / 8 * np.sum(vel**2),
    )


@pytest.mark.parametrize("name", ["straight", "curved-cup", "both-curved"])
@pytest.mark.parametrize(
    "omega,alpha,xd,xdd", [(280, 130, 0.11, -8), (-210, -85, -0.07, 5), (0, 0, 0.12, 4)]
)
@pytest.mark.parametrize("primary", [True, False])
def test_cartesian_material_balance_at_actual_boundary(
    name, omega, alpha, xd, xdd, primary
):
    force = law(name)
    ctx = context(omega=omega, xd=xd, xdd=xdd, primary=primary)
    solved = ClosureUnknowns(
        shift_acceleration=1,
        primary_angular_acceleration=alpha,
        secondary_angular_acceleration=alpha,
    )
    loads = force.evaluate_element(ctx)
    f, t, e = particle_oracle(force, ctx.axial_position, omega, alpha, xd, xdd)
    assert loads.closing_force.evaluate(solved) == pytest.approx(f, rel=2e-4, abs=3e-3)
    assert loads.shaft_torque.evaluate(solved) == pytest.approx(t, rel=2e-4, abs=3e-5)
    sample = force.inertia_map.evaluate(ctx.axial_position)
    assert (
        0.5 * sample.effective_mass * xd**2 + 0.5 * sample.shaft_inertia * omega**2
        == pytest.approx(e, rel=2e-5, abs=1e-7)
    )
    reactions = force.contact_reactions(ctx, solved)
    assert -reactions.upper_normal * force.inertia_map.pose(
        ctx.axial_position
    ).upper.normal[1] == pytest.approx(f, rel=2e-4, abs=3e-3)


@pytest.mark.parametrize("name", ["straight", "curved-cup", "both-curved"])
def test_derivatives_and_interpolation_need_no_runtime_geometry_solve(
    name, monkeypatch
):
    force = law(name)
    from cinder.model.cvt.actuation import sliding_block

    monkeypatch.setattr(
        sliding_block,
        "brentq",
        lambda *a, **kw: pytest.fail("geometry solve in runtime"),
    )
    for x in np.linspace(0.000113, 0.014877, 17):
        p = force.inertia_map.pose(x)
        low, high = (force.inertia_map.evaluate(x + d) for d in (-1e-7, 1e-7))
        mid = force.inertia_map.evaluate(x)
        assert mid.effective_mass_gradient == pytest.approx(
            (high.effective_mass - low.effective_mass) / 2e-7, rel=5e-5, abs=1e-7
        )
        assert mid.shaft_inertia_gradient == pytest.approx(
            (high.shaft_inertia - low.shaft_inertia) / 2e-7, rel=1e-7
        )
        g = force.spec.geometry
        assert p.datum_axial + g.lower_face.value(p.lower.u) == pytest.approx(
            g.lower_track.value(p.lower.radial), abs=3e-10
        )
        assert p.datum_axial + g.upper_face.value(p.upper.u) == pytest.approx(
            g.upper_track.value(p.upper.radial) + x, abs=3e-10
        )
        force.inertia_map.reactions(x, omega=300, alpha=20, xdot=0.04, xddot=-2)
    for x in (-1e-10, 0.0150000001, float("nan")):
        with pytest.raises(ValueError, match="interval"):
            force.inertia_map.evaluate(x)


def test_total_mass_count_com_and_complete_guide_torque():
    spec = law().spec
    base = SlidingBlockInertiaMap(spec)
    more = SlidingBlockInertiaMap(replace(spec, mass=replace(spec.mass, count=7)))
    heavy = SlidingBlockInertiaMap(
        replace(spec, mass=replace(spec.mass, total_mass=1.5))
    )
    x = 0.0075
    assert more.evaluate(x) == base.evaluate(x)
    for name in (
        "effective_mass",
        "effective_mass_gradient",
        "shaft_inertia",
        "shaft_inertia_gradient",
    ):
        assert getattr(heavy.evaluate(x), name) == pytest.approx(
            2 * getattr(base.evaluate(x), name)
        )
    shifted = SlidingBlockInertiaMap(
        replace(spec, mass=replace(spec.mass, com_offset=(0.001, 0, 0.002)))
    )
    assert shifted.pose(x).datum_radial == base.pose(x).datum_radial
    assert shifted.pose(x).lower == base.pose(x).lower
    assert shifted.pose(x).radial == pytest.approx(base.pose(x).radial + 0.001)
    moments = []
    for correlation in (-1, 1):
        tensor = np.array(spec.mass.centroidal_inertia_per_mass)
        tensor[0, 2] = tensor[2, 0] = correlation * 8e-6
        mapped = SlidingBlockInertiaMap(
            replace(spec, mass=replace(spec.mass, centroidal_inertia_per_mass=tensor))
        )
        assert mapped.evaluate(x) == base.evaluate(x)
        reactions = mapped.reactions(x, omega=350, alpha=130, xdot=0.1, xddot=0)
        moments.append(reactions.guide_moment[1])
        assert reactions.guide_moment[0] == pytest.approx(
            0.75 * 130 * correlation * 8e-6
        )
        assert reactions.guide_moment[2] == pytest.approx(0.75 * 0.000081 * 130)
        assert reactions.guide_tangential == pytest.approx(
            0.75 * (0.057 * 130 + 2 * 350 * 0.4 * 0.1)
        )
    assert moments == pytest.approx([51.05953125 - 0.735, 51.05953125 + 0.735])


@pytest.mark.parametrize(
    "changes",
    [
        {"total_mass": float("nan")},
        {"count": True},
        {"count": 1.2},
        {"com_offset": (0, 0.001, 0)},
        {"centroidal_inertia_per_mass": ((1, 0, 0), (0, 1, 0), (0, 0, 3))},
        {"centroidal_inertia_per_mass": ((1, 1, 0), (0, 1, 0), (0, 0, 1))},
        {"centroidal_inertia_per_mass": ((1, 0, 0), (0, -1, 0), (0, 0, 1))},
    ],
)
def test_invalid_mass_data_are_rejected(changes):
    with pytest.raises(ValueError):
        replace(law().spec.mass, **changes)


def test_ambiguous_branch_missing_support_end_policy_and_guide_are_rejected():
    spec = law().spec
    with pytest.raises(ValueError, match="End contacts"):
        SlidingBlockInertiaMap(
            replace(spec, geometry=replace(spec.geometry, allow_end_contacts=False))
        )
    with pytest.raises(ValueError, match="unique"):
        SlidingBlockInertiaMap(
            replace(
                spec,
                geometry=replace(spec.geometry, upper_track=spec.geometry.lower_track),
            )
        )
    with pytest.raises(ValueError, match="footprint"):
        replace(
            spec.geometry, upper_track=replace(spec.geometry.upper_track, right=0.059)
        )
    with pytest.raises(ValueError, match="guide"):
        replace(spec, guide="unspecified")
    curved = law("both-curved").spec
    wider = SlidingBlockInertiaMap(
        replace(curved, geometry=replace(curved.geometry, radial_max=0.069))
    )
    original = SlidingBlockInertiaMap(curved)
    for x in np.linspace(0, 0.015, 13):
        a, b = wider.evaluate(x), original.evaluate(x)
        np.testing.assert_allclose(
            tuple(getattr(a, k) for k in a.__dataclass_fields__),
            tuple(getattr(b, k) for k in b.__dataclass_fields__),
            rtol=1e-9,
            atol=1e-10,
        )


@pytest.mark.parametrize("name", ["straight", "curved-cup", "both-curved"])
def test_public_document_round_trip_preflight_and_schema(name):
    obj = assembly(law(name))
    document = encode_assembly_document(obj)
    restored = decode_assembly_document(json.loads(json.dumps(document)))
    assert encode_assembly_document(restored) == document
    validation = validate_assembly(restored)
    assert validation.is_valid
    assert any(
        f.code == "actuation.sliding_block_ideal_guide" for f in validation.findings
    )
    import jsonschema

    jsonschema.validate(document, assembly_document_json_schema())


@pytest.mark.parametrize("name", ["straight", "curved-cup", "both-curved"])
@pytest.mark.parametrize("origin_shift", [-0.005, 0.005, 0.015, 0.02])
def test_changing_axial_origin_preserves_physics(name, origin_shift):
    original = law(name)
    shifted = shifted_law(original, origin_shift)
    for x in (0.0, 0.003113, 0.014879, 0.015):
        new_x = x - origin_shift
        sample, moved = original.inertia_map.evaluate(x), shifted.inertia_map.evaluate(
            new_x
        )
        for key in (
            "effective_mass",
            "effective_mass_gradient",
            "shaft_inertia",
            "shaft_inertia_gradient",
        ):
            assert getattr(moved, key) == pytest.approx(getattr(sample, key), abs=2e-7)
        r = original.inertia_map.reactions(x, omega=280, alpha=130, xdot=0.11, xddot=-8)
        s = shifted.inertia_map.reactions(
            new_x, omega=280, alpha=130, xdot=0.11, xddot=-8
        )
        assert (s.lower_normal, s.upper_normal, *s.guide_moment) == pytest.approx(
            (r.lower_normal, r.upper_normal, *r.guide_moment), rel=1e-9, abs=1e-6
        )
        exact = exact_evaluate(shifted.spec.geometry.mechanism(), new_x, omega=280)
        assert exact.radial == pytest.approx(
            shifted.inertia_map.pose(new_x).radial, abs=3e-9
        )


def test_sliding_block_mounted_on_real_secondary_travel():
    import jsonschema
    from cinder.model.cvt.contact import ContactRegime, SlipDirection

    base = assembly()
    force = shifted_law(law(), 0.015)
    secondary = replace(
        base.pulleys.secondary, actuator=PulleyActuator(force), helical_coupling=None
    )
    obj = replace(base, pulleys=replace(base.pulleys, secondary=secondary))
    document = encode_assembly_document(obj)
    jsonschema.validate(document, assembly_document_json_schema())
    restored = decode_assembly_document(document)
    assert validate_assembly(restored).is_valid
    plant = MechanicalCVTPlant.from_assembly(restored)
    system = CVTOperatingHybridSystem(plant)
    for shift in (0.005, 0.01, 0.015):
        state = CVTState(350, 170, 8, shift, 0.03)
        geometry = plant.geometry.evaluate(shift)
        ctx = plant.secondary_actuation_context(time=0, state=state, geometry=geometry)
        assert ctx.axial_position < 0
        assert ctx.axial_speed < 0
        assert ctx.axial_acceleration.gains.shift_acceleration < 0
        assert len(plant.secondary_actuator.inspect(ctx).contributions) == 3
        mode = CVTOperatingRegime.engaged_free(
            contact_regime=ContactRegime.both_slip(
                primary_direction=SlipDirection.BELT_LEADS_PULLEY,
                secondary_direction=SlipDirection.PULLEY_LEADS_BELT,
            )
        )
        result = system.evaluate_runtime(time=0, state=state.as_vector(), mode=mode)
        assert np.all(np.isfinite(result.state_derivative.as_vector()))


@pytest.mark.parametrize("name", ["straight", "curved-cup", "both-curved"])
@pytest.mark.parametrize("mass_scale", [0.001, 1, 1000])
def test_zero_moving_track_load_uses_numerical_resolution_not_a_force_deadband(
    name, mass_scale
):
    spec = law(name).spec
    force = SlidingBlockFlyweightForce(
        replace(
            spec, mass=replace(spec.mass, total_mass=spec.mass.total_mass * mass_scale)
        )
    )
    for x in (0.001113, 0.002113, 0.007531):
        for xd in (0, 0.11):
            sample = force.inertia_map.evaluate(x)
            xdd = (
                0.5 * sample.shaft_inertia_gradient * 80**2
                - 0.5 * sample.effective_mass_gradient * xd**2
            ) / sample.effective_mass
            margins = []
            for delta in (-0.001, 0, 0.001):
                ctx = context(x=x, omega=80, xd=xd, xdd=xdd + delta)
                solved = ClosureUnknowns(shift_acceleration=1)
                reactions = force.contact_reactions(ctx, solved)
                margin = force.compressive_contact_margins(ctx, solved)[1][1]
                margins.append(margin)
                if delta == 0:
                    assert abs(reactions.upper_normal) <= reactions.normal_tolerances[1]
                    assert reactions.compressive
                else:
                    assert margin == reactions.upper_normal
            assert margins[0] > 0 and margins[1] == 0 and margins[2] < 0


@pytest.mark.parametrize(
    "name,x", [("straight", 0.001), ("curved-cup", 0.0015), ("both-curved", 0.002)]
)
def test_coupled_zero_contact_load_and_resolved_tension(name, x):
    force = law(name)
    base = assembly(force)
    omega = 80
    sample = force.inertia_map.evaluate(x)
    xdd = 0.5 * sample.shaft_inertia_gradient * omega**2 / sample.effective_mass
    host_mass = base.inertias.primary.moving_sheave_mass
    for extra_acceleration in (0, 0.001):
        # A compressed closing spring accelerates the real positive-mass sheave.
        # Its load makes the mechanism's moving-track reaction exactly zero,
        # or slightly tensile. No massless host or detached contact is assumed.
        stiffness = (
            host_mass * xdd + (host_mass + sample.effective_mass) * extra_acceleration
        ) / (0.03 - x)
        spring = AxialSpringForce(AxialSpringForceSpec(stiffness, 0.03, -1))
        primary = replace(base.pulleys.primary, actuator=PulleyActuator(force, spring))
        obj = replace(base, pulleys=replace(base.pulleys, primary=primary))
        assert validate_assembly(obj).is_valid
        system = CVTOperatingHybridSystem(MechanicalCVTPlant.from_assembly(obj))
        state = CVTState(omega, 0, 0, x, 0)
        if extra_acceleration:
            with pytest.raises(RuntimeError, match="moving_track"):
                system.evaluate_runtime(
                    time=0,
                    state=state.as_vector(),
                    mode=CVTOperatingRegime.deadzone_free(),
                )
        else:
            result = system.evaluate_runtime(
                time=0, state=state.as_vector(), mode=CVTOperatingRegime.deadzone_free()
            )
            assert result.state_derivative.as_vector()[4] == pytest.approx(xdd)


@pytest.mark.parametrize("name", ["straight", "curved-cup", "both-curved"])
def test_zero_fixed_track_reaction_and_resolved_tension(name):
    force = law(name)
    x, xd, omega = 0.002113, 0.11, 80
    p = force.inertia_map.pose(x)
    # The upper-track frame has virtual velocity (r', z'-1). At zero lower
    # reaction its inertial force does no work along this allowed motion.
    xdd = (
        p.r_prime * p.radial * omega**2
        - (p.r_prime * p.r_second + (p.z_prime - 1) * p.z_second) * xd**2
    ) / (p.r_prime**2 + (p.z_prime - 1) * p.z_prime)
    margins = []
    for delta in (-0.001, 0, 0.001):
        ctx = context(x=x, omega=omega, xd=xd, xdd=xdd + delta)
        solved = ClosureUnknowns(shift_acceleration=1)
        reactions = force.contact_reactions(ctx, solved)
        margins.append(force.compressive_contact_margins(ctx, solved)[0][1])
        if delta == 0:
            assert reactions.upper_normal > 0
            assert reactions.compressive
    assert margins[0] < 0 and margins[1] == 0 and margins[2] > 0


def test_one_distributed_sliding_block_group_per_pulley_in_python_and_documents():
    import jsonschema

    force = law()
    heavier = SlidingBlockFlyweightForce(
        replace(force.spec, mass=replace(force.spec.mass, total_mass=1.5))
    )
    with pytest.raises(ValueError, match="one sliding-block group.*total_mass"):
        PulleyActuator(force, heavier)
    obj = assembly(heavier)
    assert len(obj.pulleys.primary.actuator.inspect(context()).contributions) == 4
    document = encode_assembly_document(obj)
    document["pulleys"]["primary"]["components"].append(
        document["pulleys"]["primary"]["components"][0]
    )
    with pytest.raises(ValueError, match="one sliding-block group"):
        decode_assembly_document(document)
    report = validate_assembly_document(document)
    assert not report.is_valid
    assert "total_mass" in report.errors[0].message
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(document, assembly_document_json_schema())


@pytest.mark.parametrize("circle_sign", [0, 2, True, 1.0])
def test_inactive_profile_sign_also_obeys_saved_document_contract(circle_sign):
    with pytest.raises(ValueError, match="circle_sign"):
        replace(law().spec.geometry.lower_track, circle_sign=circle_sign)


def test_named_running_contact_margins_and_liftoff():
    actuator = PulleyActuator(law("both-curved"))
    margins = actuator.compressive_contact_margins(
        context(omega=25, xdd=200), ClosureUnknowns(shift_acceleration=1)
    )
    assert (
        len(margins) == 2
        and "fixed_track" in margins[0][0]
        and "moving_track" in margins[1][0]
    )
    assert margins[1][1] < 0


def test_stop_impulse_counterexample_and_accepted_geometry():
    from cinder.model.cvt.contact import ContactRegime, SlipDirection

    bad = law()
    impulse = bad.inertia_map.impulses(0.015, delta_xdot=-0.1, delta_omega=0)
    assert (impulse.lower_normal, impulse.upper_normal) == pytest.approx(
        (-0.00848528137423857, 0.043266615305567875), abs=1e-10
    )
    g = bad.spec.geometry
    track = replace(g.upper_track, slope=-0.5, offset=0.01325)
    good = SlidingBlockFlyweightForce(
        replace(bad.spec, geometry=replace(g, upper_track=track, radial_max=0.067))
    )
    for force, valid in ((bad, False), (good, True)):
        plant = MechanicalCVTPlant.from_assembly(assembly(force))
        state = CVTState(350, 170, 8, 0.015, 0.1)
        projection = project_cvt_velocity_topology(
            model=plant,
            vector=state.as_vector(),
            shift_position=0.015,
            from_topology=CVTVelocityTopology.ENGAGED,
            to_topology=CVTVelocityTopology.ENGAGED,
            stop_shift_velocity=True,
        )
        assert projection.post_kinetic_energy <= projection.pre_kinetic_energy
        assert projection.successor_state[4] == pytest.approx(0, abs=1e-12)
        assert len(projection.mechanism_impulse_margins) == 2
        if valid:
            projection.require_admissible_mechanism_impulses()
        else:
            with pytest.raises(RuntimeError, match="tensile impulse"):
                projection.require_admissible_mechanism_impulses()
        system = CVTOperatingHybridSystem(plant)
        mode = CVTOperatingRegime.engaged_free(
            contact_regime=ContactRegime.both_slip(
                primary_direction=SlipDirection.BELT_LEADS_PULLEY,
                secondary_direction=SlipDirection.PULLEY_LEADS_BELT,
            )
        )
        if valid:
            transition = system.transition(
                0, state.as_vector(), mode, ("upper_stop_reached",)
            )
            assert transition.reason == "upper_stop_reached_perfectly_inelastic_impact"
            assert transition.successor_state[4] == pytest.approx(0, abs=1e-12)
        else:
            with pytest.raises(RuntimeError, match="tensile impulse"):
                system.transition(0, state.as_vector(), mode, ("upper_stop_reached",))


def test_selected_hybrid_reset_cannot_bypass_impulse_guard(monkeypatch):
    from cinder.execution.hybrid import cvt_operating_hybrid as module
    from cinder.execution.hybrid.hybrid import HybridTransition

    system = CVTOperatingHybridSystem(MechanicalCVTPlant.from_assembly(assembly()))
    state = CVTState(350, 0, 0, 0.001, 0.1)
    mode = CVTOperatingRegime.deadzone_free()
    reset = state.as_vector().copy()
    reset[4] = 0
    monkeypatch.setattr(
        module,
        "resolve_cvt_operating_transition",
        lambda **kwargs: HybridTransition(
            next_mode=mode, reason="test reset", successor_state=reset
        ),
    )
    with pytest.raises(RuntimeError, match="tensile impulse"):
        system.transition(0, state.as_vector(), mode, ("test",))


@pytest.mark.parametrize("name", ["straight", "multiple-contact"])
def test_coupled_smooth_motion_preserves_primary_angular_momentum(name):
    plant = MechanicalCVTPlant.from_assembly(assembly(law(name)))
    system = CVTOperatingHybridSystem(plant)
    initial = CVTState(100, 0, 0, 0.001, 0.005)
    mode = CVTOperatingRegime.deadzone_free()
    result = solve_ivp(
        lambda t, y: system.evaluate_runtime(
            time=t, state=y, mode=mode
        ).state_derivative.as_vector(),
        (0, 0.0005),
        initial.as_vector(),
        rtol=1e-8,
        atol=1e-11,
        max_step=1e-4,
    )
    assert result.success
    assert 0 < result.y[3, -1] < plant.geometry.spec.deadzone_shift
    force = plant.primary_actuator.force_laws[0]
    momentum = []
    for y in result.y.T:
        j = (
            plant.inertias.primary.fixed_rotating_hardware_inertia
            + force.inertia_map.evaluate(y[3]).shaft_inertia
        )
        momentum.append(j * y[0])
    np.testing.assert_allclose(momentum, momentum[0], rtol=2e-8, atol=1e-10)
    assert abs(result.y[3, -1] - initial.shift_position) > 1e-7
    assert abs(result.y[0, -1] - initial.primary_angular_speed) > 1e-5
