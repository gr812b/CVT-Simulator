"""Public contracts used by CINDER pulley-actuation components."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Protocol

from cinder.closure import (
    AffineClosureScalar,
    ClosureGains,
    ClosureUnknowns,
)


@dataclass(frozen=True, slots=True)
class PulleyActuationState:
    """
    Known local quantities available before the closure solve.

    ``axial_position`` and ``axial_speed`` use the particular actuator's
    local pulley coordinate x. Positive local axial force tends to close
    and clamp the pulley.

    The final three fields describe that local coordinate in terms of the
    global shift coordinate s:

        x_dot = (dx/ds) s_dot.

    They are required by the secondary helix because its relative rotation
    is theta(x(s)). Defaults retain the simple x = s mapping for existing
    primary laws and direct tests.
    """

    axial_position: float
    axial_speed: float
    shaft_speed: float

    global_shift_speed: float | None = None
    axial_coordinate_slope: float = 1.0
    axial_coordinate_curvature: float = 0.0

    def __post_init__(self) -> None:
        for name, value in (
            ("axial_position", self.axial_position),
            ("axial_speed", self.axial_speed),
            ("shaft_speed", self.shaft_speed),
            ("axial_coordinate_slope", self.axial_coordinate_slope),
            (
                "axial_coordinate_curvature",
                self.axial_coordinate_curvature,
            ),
        ):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite.")

        if (
            self.global_shift_speed is not None
            and not isfinite(self.global_shift_speed)
        ):
            raise ValueError("global_shift_speed must be finite or None.")

    @property
    def resolved_global_shift_speed(self) -> float:
        """
        Return s_dot.

        Existing direct uses that only provide local axial speed remain
        valid for the default x = s coordinate. Core assembly should pass
        the true global shift speed explicitly.
        """

        if self.global_shift_speed is not None:
            return self.global_shift_speed

        if self.axial_coordinate_slope != 0.0:
            return self.axial_speed / self.axial_coordinate_slope

        return 0.0


@dataclass(frozen=True, slots=True)
class PulleyActuationResult:
    """The complete local axial-force relation returned by one actuator."""

    relation: AffineClosureScalar

    @property
    def bias_force(self) -> float:
        """Known local force at the current RHS evaluation point."""

        return self.relation.bias

    @property
    def gains(self) -> ClosureGains:
        """Gain row aligned with CINDER's closure unknowns."""

        return self.relation.gains

    def force(self, unknowns: ClosureUnknowns) -> float:
        """Evaluate the local axial force after solving the closure."""

        return self.relation.evaluate(unknowns)


class AxialForceLaw(Protocol):
    """One composable mechanism contributing local pulley axial force."""

    def evaluate(
        self,
        state: PulleyActuationState,
    ) -> AffineClosureScalar:
        """Return an affine local axial-force contribution."""
