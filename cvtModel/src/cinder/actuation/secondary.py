"""Convenience construction for CINDER's torque-reactive secondary."""

from __future__ import annotations

from dataclasses import dataclass

from .forces import (
    AxialSpringForce,
    AxialSpringForceSpec,
    SecondaryHelixForce,
    SecondaryHelixForceSpec,
)
from .pulley_actuator import PulleyActuator


@dataclass(frozen=True, slots=True)
class TorqueReactiveSecondarySpec:
    """The standard secondary: direct spring plus one physical helix assembly."""

    axial_spring: AxialSpringForceSpec
    helix: SecondaryHelixForceSpec


def build_torque_reactive_secondary(
    spec: TorqueReactiveSecondarySpec,
) -> PulleyActuator:
    """Build the local-secondary actuator from its two physical mechanisms."""

    return PulleyActuator(
        AxialSpringForce(spec.axial_spring),
        SecondaryHelixForce(spec.helix),
    )
