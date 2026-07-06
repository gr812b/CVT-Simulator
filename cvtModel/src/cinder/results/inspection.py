"""Detailed state inspection reconstructed after integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from cinder.model.boundaries.output import OutputBoundaryEvaluation
from cinder.model.cvt.actuation import ActuatorInspection
from cinder.model.cvt.closure import ClosureUnknowns
from cinder.model.cvt.dynamics.deadzone import DeadzoneEvaluation
from cinder.model.cvt.dynamics.engaged_contact import EngagedContactClosure
from cinder.model.cvt.dynamics.result import TrialClosureResult
from cinder.model.cvt.geometry import RadiusAtShift
from cinder.model.system.state import CVTDynamicState
from cinder.execution.hybrid.cvt_contact import CVTContactEvaluation
from cinder.execution.hybrid.cvt_regime import CVTEngagementState, CVTOperatingRegime

if TYPE_CHECKING:
    from cinder.execution.hybrid.cvt_operating_hybrid import CVTOperatingHybridSystem


@dataclass(frozen=True, slots=True)
class GeometryInspection:
    """Reporting geometry, including the primary-disengaged deadzone case."""

    primary: RadiusAtShift
    secondary: RadiusAtShift
    primary_wrap_angle: float
    secondary_wrap_angle: float

    @property
    def effective_ratio_secondary_over_primary(self) -> float:
        return self.secondary.effective / self.primary.effective


@dataclass(frozen=True, slots=True)
class CVTStateInspection:
    """One rich explanation of a stored state, never constructed in the RHS."""

    time: float
    mode: CVTOperatingRegime
    state: CVTDynamicState
    geometry: GeometryInspection
    engine_torque: float
    output_boundary: OutputBoundaryEvaluation
    primary_actuation: ActuatorInspection
    secondary_actuation: ActuatorInspection | None
    closure_unknowns: ClosureUnknowns | None
    contact: CVTContactEvaluation | None
    deadzone: DeadzoneEvaluation | None
    closure_audit: TrialClosureResult | None


def inspect_cvt_state(
    *,
    system: "CVTOperatingHybridSystem",
    time: float,
    vector,
    mode: CVTOperatingRegime,
    include_closure_audit: bool = False,
) -> CVTStateInspection:
    """Re-evaluate one accepted state for report/audit channels.

    The regular contact solve remains lean.  ``include_closure_audit`` adds one
    full fixed-lambda closure reconstruction at this selected report point; it
    never changes the trajectory solver or its accepted states.
    """

    evaluation = system.inspect(time=time, state=vector, mode=mode)
    state = CVTDynamicState.from_vector(vector)

    if mode.engagement is CVTEngagementState.ENGAGED:
        assert isinstance(evaluation, CVTContactEvaluation)
        snapshot = evaluation.snapshot
        primary_context = system.model.primary_actuation_context(
            state=state, geometry=snapshot.geometry
        )
        secondary_context = system.model.output_actuation_context(
            state=state,
            geometry=snapshot.geometry,
            helical_kinematics=snapshot.secondary_helix,
        )
        audit: TrialClosureResult | None = None
        if include_closure_audit:
            audit_trial = EngagedContactClosure(
                snapshot=snapshot,
                shift_constraint=system._engaged_constraint_for(mode),
            ).evaluate_trial(
                traction_utilization=evaluation.traction_utilization,
                maximum_closure_condition_number=(
                    system.solve_settings.maximum_closure_condition_number
                ),
                capture_diagnostics=True,
            )
            if not isinstance(audit_trial.closure, TrialClosureResult):
                raise RuntimeError(
                    "Diagnostic closure reconstruction did not produce audit data."
                )
            audit = audit_trial.closure
        return CVTStateInspection(
            time=time,
            mode=mode,
            state=state,
            geometry=GeometryInspection(
                primary=snapshot.geometry.primary,
                secondary=snapshot.geometry.secondary,
                primary_wrap_angle=snapshot.geometry.primary_wrap_angle,
                secondary_wrap_angle=snapshot.geometry.secondary_wrap_angle,
            ),
            engine_torque=snapshot.engine_torque,
            output_boundary=snapshot.output_boundary_evaluation,
            primary_actuation=system.model.primary_actuator.inspect(primary_context),
            secondary_actuation=system.model.secondary_actuator.inspect(
                secondary_context
            ),
            closure_unknowns=evaluation.closure_unknowns,
            contact=evaluation,
            deadzone=None,
            closure_audit=audit,
        )

    assert isinstance(evaluation, DeadzoneEvaluation)
    snapshot = evaluation.snapshot
    primary_context = system.model.primary_actuation_context(
        state=state,
        geometry=snapshot.primary_geometry,
    )
    # In deadzone the primary is disconnected; the output actuator remains
    # physically installed but its torque-reaction terms have no derived
    # engaged closure solution.  Report it as unavailable rather than inventing
    # values from zeroed unknowns.
    return CVTStateInspection(
        time=time,
        mode=mode,
        state=state,
        geometry=GeometryInspection(
            primary=snapshot.primary_geometry.primary,
            secondary=snapshot.locked_geometry.secondary,
            primary_wrap_angle=snapshot.locked_geometry.primary_wrap_angle,
            secondary_wrap_angle=snapshot.locked_geometry.secondary_wrap_angle,
        ),
        engine_torque=snapshot.engine_torque,
        output_boundary=snapshot.output_boundary_evaluation,
        primary_actuation=system.model.primary_actuator.inspect(primary_context),
        secondary_actuation=None,
        closure_unknowns=None,
        contact=None,
        deadzone=evaluation,
        closure_audit=None,
    )
