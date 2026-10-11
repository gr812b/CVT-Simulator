from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pytest

from cinder.contracts import (
    decode_assembly_document,
    decode_simulation_case_document,
    validate_assembly,
)
from cinder.execution.hybrid.cvt_impact import (
    CVTVelocityTopology,
    kinetic_energy_for_topology,
    project_cvt_velocity_topology,
)
from cinder.model.cvt.actuation import (
    ActuationContribution,
    CentrifugalInertiaForce,
    CentrifugalInertiaMap,
    CentrifugalInertiaSample,
    FixedPivotFlyweightForce,
    FixedPivotFlyweightInertiaMap,
    PulleyActuationContext,
    PulleyActuator,
    PulleyClosureChannels,
    PulleyElementContribution,
    PulleyKineticMode,
)
from cinder.model.cvt.closure import (
    AffineClosureScalar,
    ClosureGains,
    ClosureUnknown,
    ClosureUnknowns,
)
from cinder.model.cvt.contact import ContactTractionUtilization
from cinder.model.cvt.dynamics.equation_context import TrialEquationContext
from cinder.model.cvt.dynamics.equations import build_trial_closure_system
from cinder.model.cvt.dynamics.shift_constraints import EngagedShiftConstraint
from cinder.model.cvt.dynamics.state_fixed_equations import build_state_fixed_equations
from cinder.model.system import MechanicalCVTPlant
from cinder.model.system.ports import CVTShaftBoundaryValues, ShaftBoundaryValue
from cinder.model.system.state import CVTState
from cinder.results import ReportingGrid


@dataclass(frozen=True)
class _PolynomialInertiaMap:
    """A coefficient fixture with no q/I interface or contact interpretation."""

    axial_position_min: float = 0.0
    axial_position_max: float = 0.02

    def evaluate(self, axial_position: float) -> CentrifugalInertiaSample:
        if not self.axial_position_min <= axial_position <= self.axial_position_max:
            raise ValueError("Outside fixture interval.")
        return CentrifugalInertiaSample(
            effective_mass=2.0 - 3.0 * axial_position,
            effective_mass_gradient=-3.0,
            shaft_inertia=0.01 + 0.004 * axial_position,
            shaft_inertia_gradient=0.004,
        )


class _LegacyFixedPivotForce(FixedPivotFlyweightForce):
    """Pre-refactor q/I equations retained only as a regression oracle.

    Source: a2dcdc66a9653960dcb1ea4d73a1aa2575aebf66. Keep the four numerical
    methods independent of the shared evaluator, including the inspected
    terms used by the unchanged contact-roundoff guard.
    """

    def evaluate(self, context):
        s = self.spec.mechanism_map.evaluate(context.axial_position)
        return AffineClosureScalar.constant(
            0.5 * context.shaft_speed**2 * s.shaft_inertia_gradient
            - s.pivot_inertia
            * s.angle_gradient
            * s.angle_curvature
            * context.axial_speed**2
        ) + context.axial_acceleration.scaled(-s.pivot_inertia * s.angle_gradient**2)

    def evaluate_element(self, context):
        s = self.spec.mechanism_map.evaluate(context.axial_position)
        return PulleyElementContribution(
            closing_force=self.evaluate(context),
            shaft_torque=AffineClosureScalar(
                bias=-s.shaft_inertia_gradient
                * context.axial_speed
                * context.shaft_speed,
                gains=ClosureGains.from_by_unknown(
                    {
                        context.closure_channels.shaft_angular_acceleration: -s.shaft_inertia
                    }
                ),
            ),
        )

    def kinetic_modes(self, context):
        s = self.spec.mechanism_map.evaluate(context.axial_position)
        return (
            PulleyKineticMode(s.shaft_inertia, shaft_speed_coefficient=1.0),
            PulleyKineticMode(
                s.pivot_inertia, axial_speed_coefficient=s.angle_gradient
            ),
        )

    def inspect(self, context):
        s = self.spec.mechanism_map.evaluate(context.axial_position)
        return (
            ActuationContribution(
                key="fixed_pivot_flyweight_centrifugal",
                label="Fixed-pivot flyweight centrifugal drive",
                relation=AffineClosureScalar.constant(
                    0.5 * context.shaft_speed**2 * s.shaft_inertia_gradient
                ),
            ),
            ActuationContribution(
                key="fixed_pivot_flyweight_axial_inertia",
                label="Fixed-pivot flyweight reflected axial inertia",
                relation=context.axial_acceleration.scaled(
                    -s.pivot_inertia * s.angle_gradient**2
                ),
            ),
            ActuationContribution(
                key="fixed_pivot_flyweight_motion_ratio_curvature",
                label="Fixed-pivot flyweight motion-ratio curvature",
                relation=AffineClosureScalar.constant(
                    -s.pivot_inertia
                    * s.angle_gradient
                    * s.angle_curvature
                    * context.axial_speed**2
                ),
            ),
        )


@pytest.fixture(scope="module")
def baseline():
    path = Path(__file__).resolve().parents[2] / "examples/baja_baseline_assembly.json"
    return decode_assembly_document(json.loads(path.read_text(encoding="utf-8")))


def _with_primary_element(assembly, element):
    primary = replace(
        assembly.pulleys.primary,
        actuator=PulleyActuator(
            element, *assembly.pulleys.primary.actuator.force_laws[1:]
        ),
    )
    return replace(assembly, pulleys=replace(assembly.pulleys, primary=primary))


def _context(*, primary=True, x=0.01, x_dot=0.04, omega=280.0):
    return PulleyActuationContext(
        time=0.3,
        axial_position=x,
        axial_speed=x_dot,
        shaft_speed=omega,
        axial_acceleration=AffineClosureScalar(
            bias=0.012,
            gains=ClosureGains.from_by_unknown(
                {
                    unknown: (-1.0) ** index * (index + 1) / 10.0
                    for index, unknown in enumerate(ClosureUnknown)
                }
            ),
        ),
        closure_channels=(
            PulleyClosureChannels.primary()
            if primary
            else PulleyClosureChannels.secondary()
        ),
    )


def _coefficients(relation):
    return (relation.bias, *relation.gains.as_tuple())


@pytest.mark.parametrize(
    "field,value",
    [
        ("effective_mass", -1.0),
        ("shaft_inertia", -1.0),
        ("effective_mass", float("nan")),
        ("effective_mass_gradient", float("nan")),
        ("shaft_inertia", float("inf")),
        ("shaft_inertia_gradient", -float("inf")),
    ],
)
def test_sample_rejects_nonfinite_values_and_negative_inertias(field, value):
    sample = CentrifugalInertiaSample(2.0, -3.0, 0.01, -0.004)
    with pytest.raises(ValueError, match=field):
        replace(sample, **{field: value})
    assert CentrifugalInertiaSample(0.0, 0.0, 0.0, 0.0).effective_mass == 0.0


@pytest.mark.parametrize("primary", [True, False])
def test_generic_element_preserves_all_acceleration_gains_and_owning_shaft(primary):
    law = CentrifugalInertiaForce(_PolynomialInertiaMap())
    context = _context(primary=primary)
    sample = law.inertia_map.evaluate(context.axial_position)
    actual = law.evaluate_element(context)
    np.testing.assert_allclose(
        actual.closing_force.gains.as_tuple(),
        -sample.effective_mass * np.array(context.axial_acceleration.gains.as_tuple()),
        rtol=1e-14,
        atol=1e-14,
    )
    expected_torque_gains = np.zeros(8)
    expected_torque_gains[context.closure_channels.shaft_angular_acceleration] = (
        -sample.shaft_inertia
    )
    np.testing.assert_array_equal(
        actual.shaft_torque.gains.as_tuple(), expected_torque_gains
    )
    inspected = PulleyActuator(law).inspect(context).total_relation
    np.testing.assert_allclose(
        _coefficients(inspected), _coefficients(actual.closing_force)
    )


@pytest.mark.parametrize("x_dot,omega", [(0.0, 280.0), (0.04, 280.0), (-0.06, -180.0)])
def test_generic_force_and_torque_balance_the_derivative_of_kinetic_energy(
    x_dot, omega
):
    law = CentrifugalInertiaForce(_PolynomialInertiaMap())
    x, x_ddot, alpha = 0.01, 3.5, 12.0
    context = replace(
        _context(x=x, x_dot=x_dot, omega=omega),
        axial_acceleration=AffineClosureScalar(
            gains=ClosureGains(shift_acceleration=1.0)
        ),
    )
    unknowns = ClosureUnknowns(
        shift_acceleration=x_ddot, primary_angular_acceleration=alpha
    )
    contribution = law.evaluate_element(context)
    delivered_power = (
        contribution.closing_force.evaluate(unknowns) * x_dot
        + contribution.shaft_torque.evaluate(unknowns) * omega
    )

    def energy_at(time):
        local = replace(
            context,
            axial_position=x + x_dot * time + 0.5 * x_ddot * time**2,
            axial_speed=x_dot + x_ddot * time,
            shaft_speed=omega + alpha * time,
        )
        return sum(
            0.5
            * mode.inertia
            * mode.local_speed(
                shaft_speed=local.shaft_speed, axial_speed=local.axial_speed
            )
            ** 2
            for mode in law.kinetic_modes(local)
        )

    dt = 1e-6
    derivative = (energy_at(dt) - energy_at(-dt)) / (2.0 * dt)
    assert delivered_power == pytest.approx(-derivative, rel=2e-8, abs=1e-7)
    # Net force alone does not define a unilateral contact for this provider.
    assert PulleyActuator(law).compressive_contact_margins(context, unknowns) == ()


def test_generic_boundary_rejects_missing_context_wrong_samples_and_bad_intervals(
    baseline,
):
    law = CentrifugalInertiaForce(_PolynomialInertiaMap())
    with pytest.raises(ValueError, match="axial-acceleration"):
        law.evaluate(replace(_context(), axial_acceleration=None))
    with pytest.raises(ValueError, match="closure_channels"):
        law.evaluate_element(replace(_context(), closure_channels=None))
    with pytest.raises(ValueError, match="Outside fixture interval"):
        law.evaluate(_context(x=0.03))
    for lower, upper in [(0.02, 0.0), (float("nan"), 0.02), (0.0, float("inf"))]:
        with pytest.raises(ValueError, match="finite and ordered"):
            CentrifugalInertiaForce(_PolynomialInertiaMap(lower, upper))
    with pytest.raises(TypeError, match="CentrifugalInertiaMap"):
        CentrifugalInertiaForce(object())
    # Protocol membership does not verify return annotations. An old q/I map
    # must pass through the adapter before the generic evaluator consumes it.
    original = baseline.pulleys.primary.actuator.force_laws[0].spec.mechanism_map
    with pytest.raises(TypeError, match="return CentrifugalInertiaSample"):
        CentrifugalInertiaForce(original).evaluate(_context())


def test_generic_domain_is_checked_by_preflight_and_plant_construction(baseline):
    law = CentrifugalInertiaForce(_PolynomialInertiaMap(axial_position_max=0.01))
    assembly = _with_primary_element(baseline, law)
    codes = {finding.code for finding in validate_assembly(assembly).findings}
    assert "actuation.inertia_map_does_not_cover_local_travel" in codes
    with pytest.raises(ValueError, match="centrifugal inertia map does not cover"):
        MechanicalCVTPlant.from_assembly(assembly)


def test_fixed_pivot_adapter_uses_consistent_derivatives_and_original_endpoint_policy(
    baseline,
):
    law = baseline.pulleys.primary.actuator.force_laws[0]
    provider = law.inertia_map
    original = law.spec.mechanism_map
    assert isinstance(provider, CentrifugalInertiaMap)
    assert isinstance(provider, FixedPivotFlyweightInertiaMap)
    assert provider.flyweight_map is original
    for x in (0.001, 0.0063, 0.0141):
        h = 1e-7
        sample, lower, upper = (provider.evaluate(p) for p in (x, x - h, x + h))
        assert sample.effective_mass_gradient == pytest.approx(
            (upper.effective_mass - lower.effective_mass) / (2 * h), rel=2e-6, abs=1e-7
        )
        assert sample.shaft_inertia_gradient == pytest.approx(
            (upper.shaft_inertia - lower.shaft_inertia) / (2 * h), rel=1e-8, abs=1e-10
        )
    tolerance = original.geometry_spec.coordinate_tolerance
    for endpoint in (original.axial_position_min, original.axial_position_max):
        for x in (endpoint - tolerance / 2, endpoint, endpoint + tolerance / 2):
            assert (
                provider.evaluate(x).shaft_inertia == original.evaluate(x).shaft_inertia
            )
    with pytest.raises(ValueError, match="outside the fixed-pivot"):
        provider.evaluate(original.axial_position_max + 2 * tolerance)


def test_fixed_pivot_matches_legacy_relations_and_preserves_inspection_labels(baseline):
    law = baseline.pulleys.primary.actuator.force_laws[0]
    legacy = _LegacyFixedPivotForce(law.spec)
    for x in np.linspace(
        law.inertia_map.axial_position_min, law.inertia_map.axial_position_max, 9
    ):
        for primary in (True, False):
            for x_dot, omega in ((0.0, 0.0), (0.08, 300.0), (-0.06, 425.0)):
                context = _context(
                    primary=primary, x=float(x), x_dot=x_dot, omega=omega
                )
                current, old = law.evaluate_element(context), legacy.evaluate_element(
                    context
                )
                np.testing.assert_allclose(
                    _coefficients(current.closing_force),
                    _coefficients(old.closing_force),
                    rtol=2e-14,
                    atol=1e-11,
                )
                np.testing.assert_array_equal(
                    _coefficients(current.shaft_torque), _coefficients(old.shaft_torque)
                )
    assert [(item.key, item.label) for item in law.inspect(_context())] == [
        (
            "fixed_pivot_flyweight_centrifugal",
            "Fixed-pivot flyweight centrifugal drive",
        ),
        (
            "fixed_pivot_flyweight_axial_inertia",
            "Fixed-pivot flyweight reflected axial inertia",
        ),
        (
            "fixed_pivot_flyweight_motion_ratio_curvature",
            "Fixed-pivot flyweight motion-ratio curvature",
        ),
    ]


def test_fixed_pivot_still_rejects_tension_and_keeps_its_roundoff_guard(baseline):
    law = baseline.pulleys.primary.actuator.force_laws[0]
    legacy = _LegacyFixedPivotForce(law.spec)
    context = replace(
        _context(),
        axial_acceleration=AffineClosureScalar(
            gains=ClosureGains(shift_acceleration=1.0)
        ),
    )
    old_force = legacy.evaluate(context)
    zero_acceleration = -old_force.bias / old_force.gains.shift_acceleration
    margins = []
    for delta in (-1.0, 0.0, 1.0):
        unknowns = ClosureUnknowns(shift_acceleration=zero_acceleration + delta)
        margin = law.compressive_contact_margin(context=context, unknowns=unknowns)
        margins.append(margin)
        if delta:
            assert margin == pytest.approx(old_force.evaluate(unknowns), rel=1e-10)
        assert law.has_compressive_contact(context=context, unknowns=unknowns) == (
            delta <= 0
        )
    assert margins[0] > 0.0 and margins[1] == 0.0 and margins[2] < 0.0


def test_fixed_pivot_shared_closure_energy_and_stop_match_legacy_representation(
    baseline,
):
    current = baseline.pulleys.primary.actuator.force_laws[0]
    legacy = _with_primary_element(baseline, _LegacyFixedPivotForce(current.spec))
    plants = [
        MechanicalCVTPlant.from_assembly(assembly) for assembly in (baseline, legacy)
    ]
    limits = baseline.geometry.spec
    boundaries = CVTShaftBoundaryValues(
        primary=ShaftBoundaryValue(external_torque=12.0)
    )
    # Frozen algebraic comparisons; no claim that every trial is a trajectory state.
    for fraction in (0.0, 0.5, 1.0):
        x = limits.deadzone_shift + fraction * (
            limits.max_shift - limits.deadzone_shift
        )
        for constraint in EngagedShiftConstraint:
            state = CVTState(
                245.0,
                90.0,
                7.0,
                x,
                0.025 if constraint is EngagedShiftConstraint.FREE else 0.0,
            )
            solutions = []
            for plant in plants:
                snapshot = plant.snapshot(
                    state=state, shaft_boundaries=boundaries, geometry_side="engaged"
                )
                system = build_trial_closure_system(
                    fixed_equations=build_state_fixed_equations(
                        snapshot=snapshot, shift_constraint=constraint
                    ),
                    trial_context=TrialEquationContext(
                        snapshot=snapshot,
                        traction_utilization=ContactTractionUtilization(0.2, -0.15),
                    ),
                )
                solutions.append(system.solve().unknowns.as_tuple())
            np.testing.assert_allclose(*solutions, rtol=2e-12, atol=1e-9)
    for topology in CVTVelocityTopology:
        state = CVTState(245.0, 90.0, 7.0, limits.deadzone_shift, 0.025)
        energies = [
            kinetic_energy_for_topology(model=p, state=state, topology=topology)
            for p in plants
        ]
        assert energies[0] == pytest.approx(energies[1], rel=2e-14)
    state = CVTState(430.0, 390.0, 7.0, limits.max_shift, 0.004)
    impacts = [
        project_cvt_velocity_topology(
            model=p,
            vector=state.as_vector(),
            shift_position=limits.max_shift,
            from_topology=CVTVelocityTopology.ENGAGED,
            to_topology=CVTVelocityTopology.ENGAGED,
            stop_shift_velocity=True,
        )
        for p in plants
    ]
    np.testing.assert_allclose(
        impacts[0].successor_state, impacts[1].successor_state, rtol=2e-12, atol=1e-11
    )
    assert impacts[0].dissipated_energy == pytest.approx(
        impacts[1].dissipated_energy, rel=2e-12, abs=1e-11
    )


def test_full_launch_trajectory_matches_legacy_fixed_pivot_representation():
    """Compare independent integrations through launch, upshift, and upper stop."""

    path = (
        Path(__file__).resolve().parents[2]
        / "examples/baja_baseline_simulation_case.json"
    )
    case = decode_simulation_case_document(json.loads(path.read_text(encoding="utf-8")))
    current = case.assembly.pulleys.primary.actuator.force_laws[0]
    legacy_assembly = _with_primary_element(
        case.assembly, _LegacyFixedPivotForce(current.spec)
    )
    legacy_system = replace(
        case.system,
        cvt=replace(
            case.system.cvt,
            model=MechanicalCVTPlant.from_assembly(legacy_assembly),
        ),
    )
    assert legacy_system.classify_initial_mode(case.initial_state) == case.initial_mode
    settings = replace(
        case.integrator_settings,
        relative_tolerance=1e-7,
        absolute_tolerance=1e-10,
        max_step=0.02,
        retain_dense_output=True,
    )
    reporting = replace(
        case.reporting_settings,
        grid=ReportingGrid.uniform_time_step(0.02),
    )
    new, old = (
        system.run(
            time_span=(0.0, 10.0),
            initial_state=case.initial_state.copy(),
            initial_mode=case.initial_mode,
            settings=settings,
            reporting_settings=reporting,
        )
        for system in (case.system, legacy_system)
    )
    for result in (new, old):
        assert result.completed
        assert result.termination_reason == "final_time_reached"
        assert result.trace.final_time == 10.0
        # Require the case to exercise the transitions that motivated this test.
        events = {
            name
            for transition in result.transitions
            for name in transition.fired_event_names
        }
        assert {
            "cvt:lower_stop_release",
            "cvt:engagement_reached",
            "cvt:low_ratio_seat_reached",
            "cvt:primary_restick",
            "cvt:low_ratio_seat_release",
            "cvt:upper_stop_reached",
        } <= events

    # These equivalence tolerances are much tighter than the integration
    # tolerances. They admit accumulated floating-point roundoff, not a change
    # of trajectory at the solver's requested accuracy.
    rtol, atol = 2e-12, 1e-12
    np.testing.assert_allclose(new.final_state, old.final_state, rtol=rtol, atol=atol)
    assert len(new.transitions) == len(old.transitions)
    for a, b in zip(new.transitions, old.transitions, strict=True):
        assert a.previous_mode == b.previous_mode
        assert a.fired_event_names == b.fired_event_names
        assert a.transition.next_mode == b.transition.next_mode
        assert a.transition.reason == b.transition.reason
        assert a.time == pytest.approx(b.time, rel=0.0, abs=atol)
        np.testing.assert_allclose(
            a.post_transition_state, b.post_transition_state, rtol=rtol, atol=atol
        )

    # Preserve pre-event states and post-event resets separately. Compare all
    # five CVT states and the host state, both on the native adaptive mesh and
    # a common 5 ms grid; never interpolate across a hybrid reset.
    grid = np.linspace(0.0, 10.0, 2001)
    assert len(new.trace.segments) == len(old.trace.segments)
    for a, b in zip(new.trace.segments, old.trace.segments, strict=True):
        assert a.mode == b.mode
        np.testing.assert_allclose(a.time, b.time, rtol=0.0, atol=atol)
        np.testing.assert_allclose(a.state, b.state, rtol=rtol, atol=atol)
        start, end = max(a.start_time, b.start_time), min(a.end_time, b.end_time)
        assert start <= end
        times = np.unique(np.r_[start, grid[(grid >= start) & (grid <= end)], end])
        np.testing.assert_allclose(
            a.dense_state_at(times), b.dense_state_at(times), rtol=rtol, atol=atol
        )

    # Exercise the public run/report path as well as the raw integration.
    assert len(new.segments) == len(old.segments)
    for a, b in zip(new.segments, old.segments, strict=True):
        assert a.mode == b.mode
        np.testing.assert_allclose(a.time, b.time, rtol=0.0, atol=atol)
        assert a.signals.keys() == b.signals.keys()
        for key in a.signals:
            np.testing.assert_allclose(
                a.signal(key).values,
                b.signal(key).values,
                rtol=rtol,
                atol=atol,
                equal_nan=True,
                err_msg=key,
            )
