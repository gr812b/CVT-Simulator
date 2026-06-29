"""Construction of the ordinary torque-reactive secondary pulley actuator."""

from __future__ import annotations

from dataclasses import dataclass

from cinder.profiles.helix import HelixProfile

from .forces import (
    AxialSpringForce,
    AxialSpringForceSpec,
    SecondaryHelixForce,
    SecondaryHelixForceSpec,
)
from .pulley_actuator import PulleyActuator


@dataclass(frozen=True, slots=True)
class TorqueReactiveSecondarySpec:
    """
    Secondary clamping-force parameters.

    The helix geometry is intentionally not stored here. ``HelixProfile`` is
    independent physical geometry shared by the local clamping force and later
    secondary rotational-row assembly. The movable sheave inertia is part of
    ``SecondaryHelixForceSpec`` because it affects the actual torque reaching
    the helix before that torque is converted to clamp force.
    """

    axial_spring: AxialSpringForceSpec
    helix_force: SecondaryHelixForceSpec


def build_torque_reactive_secondary(
    *,
    spec: TorqueReactiveSecondarySpec,
    helix_profile: HelixProfile,
) -> PulleyActuator:
    """
    Build the secondary as one normal ``PulleyActuator``.

    The returned actuator sums direct axial-spring force and the
    inertia-inclusive torque-reactive helix force. It has no special secondary
    wrapper or result type.
    """

    return PulleyActuator(
        AxialSpringForce(spec.axial_spring),
        SecondaryHelixForce(
            spec=spec.helix_force,
            helix_profile=helix_profile,
        ),
    )
