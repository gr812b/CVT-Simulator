"""The four closure equations fixed for one dynamics snapshot."""

from __future__ import annotations

from dataclasses import dataclass

from cinder.closure import ClosureEquation

from .snapshot import DynamicsSnapshot
from .rows.belt_transport import build_belt_transport_equation
from .rows.global_tangent_wrap import build_global_tangent_wrap_equation
from .rows.primary_rotation import build_primary_rotation_equation
from .rows.secondary_rotation import build_secondary_rotation_equation


@dataclass(frozen=True, slots=True)
class StateFixedEquationBlock:
    """Rows 2--5, built once for every state snapshot.

    These four equations do not depend on ``lambda_p`` or ``lambda_s`` and can
    be reused unchanged across every outer lambda-root trial at the same ODE
    state.
    """

    primary_rotation: ClosureEquation
    belt_transport: ClosureEquation
    secondary_rotation: ClosureEquation
    global_tangent_wrap: ClosureEquation

    def __post_init__(self) -> None:
        equations = self.as_tuple()
        names = tuple(equation.name for equation in equations)
        if len(set(names)) != len(names):
            raise ValueError("State-fixed closure equation names must be unique.")

    def as_tuple(self) -> tuple[ClosureEquation, ClosureEquation, ClosureEquation, ClosureEquation]:
        """Return rows 2--5 in derivation order."""

        return (
            self.primary_rotation,
            self.belt_transport,
            self.secondary_rotation,
            self.global_tangent_wrap,
        )


def build_state_fixed_equations(
    *,
    snapshot: DynamicsSnapshot,
) -> StateFixedEquationBlock:
    """Build and cache the four fully state-fixed six-by-six rows."""

    return StateFixedEquationBlock(
        primary_rotation=build_primary_rotation_equation(snapshot=snapshot),
        belt_transport=build_belt_transport_equation(snapshot=snapshot),
        secondary_rotation=build_secondary_rotation_equation(snapshot=snapshot),
        global_tangent_wrap=build_global_tangent_wrap_equation(snapshot=snapshot),
    )
