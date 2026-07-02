"""State-fixed closure rows cached for one dynamics snapshot."""

from __future__ import annotations

from dataclasses import dataclass

from cinder.closure import ClosureEquation

from .snapshot import DynamicsSnapshot
from .rows.belt_transport import build_belt_transport_equation
from .rows.primary_rotation import build_primary_rotation_equation
from .rows.secondary_rotation import build_secondary_rotation_equation


@dataclass(frozen=True, slots=True)
class StateFixedEquationBlock:
    """The three lambda-independent rows built once per snapshot.

    The primary shaft, secondary shaft, and whole-belt tangential momentum
    equations contain no trial contact utilization. Every remaining row in the
    8x8 system depends on a trial ``(lambda_p, lambda_s)`` pair.
    """

    primary_rotation: ClosureEquation
    belt_transport: ClosureEquation
    secondary_rotation: ClosureEquation

    def __post_init__(self) -> None:
        equations = self.as_tuple()
        names = tuple(equation.name for equation in equations)
        if len(set(names)) != len(names):
            raise ValueError("State-fixed closure equation names must be unique.")

    def as_tuple(self) -> tuple[ClosureEquation, ClosureEquation, ClosureEquation]:
        """Return the lambda-independent rows in assembly order."""

        return (
            self.primary_rotation,
            self.belt_transport,
            self.secondary_rotation,
        )


def build_state_fixed_equations(
    *,
    snapshot: DynamicsSnapshot,
) -> StateFixedEquationBlock:
    """Build and cache the three fully state-fixed closure rows."""

    return StateFixedEquationBlock(
        primary_rotation=build_primary_rotation_equation(snapshot=snapshot),
        belt_transport=build_belt_transport_equation(snapshot=snapshot),
        secondary_rotation=build_secondary_rotation_equation(snapshot=snapshot),
    )
