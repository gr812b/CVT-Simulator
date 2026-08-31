"""Detailed CVT state inspection reconstructed after integration.

Inspection is boundary-aware but remains separate from the RHS path. A composed
host can pass the shaft boundary values corresponding to a sampled full state;
plain CVT-only callers may omit them and receive the zero-boundary inspection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from cinder.model.cvt.actuation import ActuatorInspection
from cinder.model.cvt.closure import ClosureUnknowns
from cinder.model.cvt.dynamics.deadzone import DeadzoneEvaluation
from cinder.model.cvt.dynamics.engaged_contact import EngagedContactClosure
from cinder.model.cvt.dynamics.result import TrialClosureResult
from cinder.model.cvt.geometry import RadiusAtShift
from cinder.model.system.ports import CVTShaftBoundaryValues, ShaftBoundaryValue
from cinder.model.system.state import CVTState
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
class ShaftBoundaryInspection:
    """Primary/secondary shaft boundary values aligned with one sampled state.

    Values are stored as symmetric primary/secondary shaft-port data.
    """

    primary: ShaftBoundaryValue
    secondary: ShaftBoundaryValue

    @property
    def primary_external_torque(self) -> float:
        return self.primary.external_torque

    @property
    def secondary_external_torque(self) -> float:
        return self.secondary.external_torque

    @property
    def secondary_equivalent_inertia(self) -> float:
        return self.secondary.equivalent_inertia

    @property
    def road_load(self):
        return self.secondary.metadata.get("road_load")

    @property
    def vehicle_distance(self):
        if "vehicle_distance" in self.secondary.metadata:
            return self.secondary.metadata["vehicle_distance"]
        return self.secondary.metadata.get("vehicle_position")


@dataclass(frozen=True, slots=True)
class CVTStateInspection:
    """One rich explanation of a stored state, never constructed in the RHS."""

    time: float
    mode: CVTOperatingRegime
    state: CVTState
    geometry: GeometryInspection
    shaft_boundaries: ShaftBoundaryInspection
    primary_actuation: ActuatorInspection
    secondary_actuation: ActuatorInspection | None
    closure_unknowns: ClosureUnknowns | None
    contact: CVTContactEvaluation | None
    deadzone: DeadzoneEvaluation | None
    closure_audit: TrialClosureResult | None

    @property
    def primary_external_torque(self) -> float:
        return self.shaft_boundaries.primary_external_torque

    @property
    def secondary_external_torque(self) -> float:
        return self.shaft_boundaries.secondary_external_torque


def inspect_cvt_state(
    *,
    system: "CVTOperatingHybridSystem",
    time: float,
    vector,
    mode: CVTOperatingRegime,
    shaft_boundaries: CVTShaftBoundaryValues | None = None,
    include_closure_audit: bool = False,
) -> CVTStateInspection:
    """Re-evaluate one accepted state for report/audit channels."""

    if shaft_boundaries is None:
        shaft_boundaries = CVTShaftBoundaryValues.zero()
    evaluation = system.inspect(
        time=time,
        state=vector,
        mode=mode,
        shaft_boundaries=shaft_boundaries,
    )
    state = CVTState.from_vector(vector)
    shaft_inspection = ShaftBoundaryInspection(
        primary=shaft_boundaries.primary,
        secondary=shaft_boundaries.secondary,
    )

    if mode.engagement is CVTEngagementState.ENGAGED:
        assert isinstance(evaluation, CVTContactEvaluation)
        snapshot = evaluation.snapshot
        primary_context = system.model.primary_actuation_context(
            time=time, state=state, geometry=snapshot.geometry
        )
        secondary_context = system.model.secondary_actuation_context(
            time=time,
            state=state,
            geometry=snapshot.geometry,
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
            shaft_boundaries=shaft_inspection,
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
        time=time,
        state=state,
        geometry=snapshot.primary_geometry,
    )
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
        shaft_boundaries=shaft_inspection,
        primary_actuation=system.model.primary_actuator.inspect(primary_context),
        secondary_actuation=None,
        closure_unknowns=None,
        contact=None,
        deadzone=evaluation,
        closure_audit=None,
    )
