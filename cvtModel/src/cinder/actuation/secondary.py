"""Construction for the ordinary torque-reactive secondary pulley actuator."""

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
    Local secondary clamping-force parameters.

    The physical helix profile is deliberately not stored here. It is shared
    separately by the caller with later secondary rotational dynamics.
    """

    axial_spring: AxialSpringForceSpec
    helix_force: SecondaryHelixForceSpec


def build_torque_reactive_secondary(
    *,
    spec: TorqueReactiveSecondarySpec,
    helix_profile: HelixProfile,
    movable_sheave_rotational_inertia: float,
) -> PulleyActuator:
    """
    Build a normal PulleyActuator for the secondary.

    ``helix_profile`` is passed in independently instead of being owned by
    ``TorqueReactiveSecondarySpec``. The caller keeps the same profile
    reference for the later secondary rotational row.

    ``movable_sheave_rotational_inertia`` is the resolved I_M and remains
    the single physical source used by the local helix force law.
    """

    return PulleyActuator(
        AxialSpringForce(spec.axial_spring),
        SecondaryHelixForce(
            spec=spec.helix_force,
            helix_profile=helix_profile,
            movable_sheave_rotational_inertia=(
                movable_sheave_rotational_inertia
            ),
        ),
    )
