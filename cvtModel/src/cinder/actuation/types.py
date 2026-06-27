from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PulleyActuationState:
    """
    Known local state of one pulley actuator.

    axial_position:
        Local movable-sheave coordinate [m]. Positive always means that this
        pulley closes and increases clamping.

    axial_speed:
        Time derivative of axial_position [m/s].

    shaft_speed:
        Pulley angular speed [rad/s].
    """

    axial_position: float
    axial_speed: float
    shaft_speed: float

    def __post_init__(self) -> None:
        _require_finite(
            axial_position=self.axial_position,
            axial_speed=self.axial_speed,
            shaft_speed=self.shaft_speed,
        )


@dataclass(frozen=True, slots=True)
class PulleyActuationResult:
    """
    Local axial-force relation:

        axial_force = bias_force + torque_gain * pulley_torque

    ``bias_force`` and the evaluated ``axial_force`` are signed in the local
    pulley coordinate. Positive means the mechanism tends to close and clamp
    that pulley; negative means it tends to open it.

    ``torque_gain`` is the coefficient of the pulley torque that will be
    selected by the eventual closure assembly:
      - primary actuator: torque_gain multiplies tau_p;
      - secondary actuator: torque_gain multiplies tau_s.
    """

    bias_force: float
    torque_gain: float

    def __post_init__(self) -> None:
        _require_finite(
            bias_force=self.bias_force,
            torque_gain=self.torque_gain,
        )

    def force_at_torque(self, pulley_torque: float) -> float:
        """Evaluate the relation after a pulley torque is known."""

        _require_finite(pulley_torque=pulley_torque)

        return self.bias_force + self.torque_gain * pulley_torque


class AxialForceLaw(Protocol):
    """One mechanism contributing a local axial-force relation."""

    def force_relation(
        self,
        state: PulleyActuationState,
    ) -> PulleyActuationResult:
        ...


def _require_finite(**values: float) -> None:
    for name, value in values.items():
        if not isfinite(value):
            raise ValueError(f"{name} must be finite.")
