"""Lambda-independent closure rows cached for one frozen dynamics snapshot."""

from __future__ import annotations

from dataclasses import dataclass

from cinder.closure import ClosureEquation

from .shift_constraints import (
    EngagedShiftConstraint,
    build_shift_constraint_equation,
)
from .snapshot import DynamicsSnapshot
from .rows.belt_transport import build_belt_transport_equation
from .rows.primary_axial import build_primary_axial_equation
from .rows.primary_rotation import build_primary_rotation_equation
from .rows.secondary_axial import build_secondary_axial_equation
from .rows.secondary_rotation import build_secondary_rotation_equation


@dataclass(frozen=True, slots=True)
class StateFixedEquationBlock:
    """Five lambda-independent mechanics rows for one engaged constraint.

    In free shift, ``shift_coordinate`` is the primary axial balance and
    determines ``s_ddot``.  At the upper stop, it is replaced by the exact
    kinematic row ``s_ddot = 0``; the omitted primary axial balance is then
    used solely to recover the physical unilateral stop reaction after solve.

    The remaining four rows are unchanged.  In particular, the secondary axial
    balance remains active at the stop because the secondary has no separate
    axial stop reaction.
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
    """Build and cache five state-fixed rows for free shift or upper stop."""

    if not isinstance(shift_constraint, EngagedShiftConstraint):
        raise TypeError("shift_constraint must be an EngagedShiftConstraint.")

    shift_coordinate = (
        build_primary_axial_equation(snapshot=snapshot)
        if shift_constraint is EngagedShiftConstraint.FREE
        else build_shift_constraint_equation(constraint=shift_constraint)
    )

    return StateFixedEquationBlock(
        primary_rotation=build_primary_rotation_equation(snapshot=snapshot),
        belt_transport=build_belt_transport_equation(snapshot=snapshot),
        secondary_rotation=build_secondary_rotation_equation(snapshot=snapshot),
        shift_coordinate=shift_coordinate,
        secondary_axial=build_secondary_axial_equation(snapshot=snapshot),
        shift_constraint=shift_constraint,
    )
