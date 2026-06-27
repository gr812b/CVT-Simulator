from __future__ import annotations

from dataclasses import dataclass

from .forces import (
    AxialSpringForce,
    AxialSpringForceSpec,
    HelixTorqueReactionForce,
    HelixTorqueReactionForceSpec,
    TorsionalSpringForce,
    TorsionalSpringForceSpec,
)
from .pulley_actuator import PulleyActuator


@dataclass(frozen=True, slots=True)
class TorqueReactiveSecondarySpec:
    """
    Concrete torque-reactive secondary composed from reusable force laws.

    The helix torque reaction is required. Axial and torsional springs are
    optional independently, allowing the model to represent the actual
    hardware instead of assuming one fixed secondary construction.
    """

    torque_reaction: HelixTorqueReactionForceSpec
    axial_spring: AxialSpringForceSpec | None = None
    torsional_spring: TorsionalSpringForceSpec | None = None


def build_torque_reactive_secondary(
    spec: TorqueReactiveSecondarySpec,
) -> PulleyActuator:
    """
    Build a torque-reactive secondary.

    The returned torque_gain multiplies tau_s in later matrix assembly.
    Its local x_s is positive toward secondary closure. A secondary axial
    spring is commonly configured with compression_per_axial_position = -1,
    which gives a positive closing force while it remains compressed.
    """

    force_laws = [
        HelixTorqueReactionForce(spec.torque_reaction),
    ]

    if spec.axial_spring is not None:
        force_laws.append(AxialSpringForce(spec.axial_spring))

    if spec.torsional_spring is not None:
        force_laws.append(TorsionalSpringForce(spec.torsional_spring))

    return PulleyActuator(*force_laws)
