"""Lambda-independent closure rows cached for one frozen dynamics snapshot."""

from __future__ import annotations

from dataclasses import dataclass

from cinder.closure import ClosureEquation

from .snapshot import DynamicsSnapshot
from .rows.belt_transport import build_belt_transport_equation
from .rows.primary_axial import build_primary_axial_equation
from .rows.primary_rotation import build_primary_rotation_equation
from .rows.secondary_axial import build_secondary_axial_equation
from .rows.secondary_rotation import build_secondary_rotation_equation


@dataclass(frozen=True, slots=True)
class StateFixedEquationBlock:
    """The five lambda-independent mechanics rows built once per snapshot.

    The shaft, belt-transport, and two individual pulley axial balances contain
    no trial contact utilization. Only the two integrated traction rows and the
    tension-loop compatibility row need rebuilding for each lambda trial.
    """

    primary_rotation: ClosureEquation
    belt_transport: ClosureEquation
    secondary_rotation: ClosureEquation
    primary_axial: ClosureEquation
    secondary_axial: ClosureEquation

    def __post_init__(self) -> None:
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
            self.primary_axial,
            self.secondary_axial,
        )


def build_state_fixed_equations(
    *,
    snapshot: DynamicsSnapshot,
) -> StateFixedEquationBlock:
    """Build and cache the five fully state-fixed closure rows."""

    return StateFixedEquationBlock(
        primary_rotation=build_primary_rotation_equation(snapshot=snapshot),
        belt_transport=build_belt_transport_equation(snapshot=snapshot),
        secondary_rotation=build_secondary_rotation_equation(snapshot=snapshot),
        primary_axial=build_primary_axial_equation(snapshot=snapshot),
        secondary_axial=build_secondary_axial_equation(snapshot=snapshot),
    )
