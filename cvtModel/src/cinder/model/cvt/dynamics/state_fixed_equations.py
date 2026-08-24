"""Lambda-independent closure rows cached for one frozen dynamics snapshot."""

from __future__ import annotations

from dataclasses import dataclass

from cinder.model.cvt.closure import ClosureEquation

from .shift_constraints import (
    EngagedShiftConstraint,
    build_shift_constraint_equation,
)
from cinder.model.system.evaluator import DynamicsSnapshot
from .rows.belt_transport import build_belt_transport_equation
from .rows.primary_axial import build_primary_axial_equation
from .rows.primary_rotation import build_primary_rotation_equation
from .rows.secondary_axial import build_secondary_axial_equation
from .rows.secondary_rotation import build_secondary_rotation_equation


@dataclass(frozen=True, slots=True)
class StateFixedEquationBlock:
    """Five lambda-independent mechanics rows for one engaged constraint.

    In free shift, ``shift_coordinate`` is the primary axial balance and
    ``secondary_axial`` is the secondary axial balance.  The two physical
    fixed-shift boundaries act on different hardware:

    * at the low-ratio limit the *secondary* movable sheave is against its
      closed stop, so the secondary axial row is replaced by ``s_ddot = 0``
      and the primary axial balance remains physical;
    * at the high-ratio limit the primary shift coordinate is against its
      upper stop, so the primary axial row is replaced by ``s_ddot = 0``.

    The omitted physical axial row is recovered after solve as the matching
    unilateral stop reaction.
    """

    primary_rotation: ClosureEquation
    belt_transport: ClosureEquation
    secondary_rotation: ClosureEquation
    shift_coordinate: ClosureEquation
    secondary_axial: ClosureEquation
    shift_constraint: EngagedShiftConstraint

    def __post_init__(self) -> None:
        if not isinstance(self.shift_constraint, EngagedShiftConstraint):
            raise TypeError("shift_constraint must be an EngagedShiftConstraint.")
        equations = self.as_tuple()
        names = tuple(equation.name for equation in equations)
        if len(set(names)) != len(names):
            raise ValueError("State-fixed closure equation names must be unique.")

    def as_tuple(self) -> tuple[ClosureEquation, ...]:
        """Return the five lambda-independent rows in canonical assembly order."""

        return (
            self.primary_rotation,
            self.belt_transport,
            self.secondary_rotation,
            self.shift_coordinate,
            self.secondary_axial,
        )


def build_state_fixed_equations(
    *,
    snapshot: DynamicsSnapshot,
    shift_constraint: EngagedShiftConstraint = EngagedShiftConstraint.FREE,
) -> StateFixedEquationBlock:
    """Build and cache five state-fixed rows for one engaged shift constraint."""

    if not isinstance(shift_constraint, EngagedShiftConstraint):
        raise TypeError("shift_constraint must be an EngagedShiftConstraint.")

    primary_axial = build_primary_axial_equation(snapshot=snapshot)
    secondary_axial = build_secondary_axial_equation(snapshot=snapshot)

    if shift_constraint is EngagedShiftConstraint.LOW_RATIO_SEAT:
        shift_coordinate = primary_axial
        secondary_axial = build_shift_constraint_equation(constraint=shift_constraint)
    elif shift_constraint is EngagedShiftConstraint.UPPER_STOP:
        shift_coordinate = build_shift_constraint_equation(constraint=shift_constraint)
    else:
        shift_coordinate = primary_axial

    return StateFixedEquationBlock(
        primary_rotation=build_primary_rotation_equation(snapshot=snapshot),
        belt_transport=build_belt_transport_equation(snapshot=snapshot),
        secondary_rotation=build_secondary_rotation_equation(snapshot=snapshot),
        shift_coordinate=shift_coordinate,
        secondary_axial=secondary_axial,
        shift_constraint=shift_constraint,
    )
