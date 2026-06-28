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

    The helix geometry is intentionally not stored here. ``HelixProfile``
    is an independent physical geometry object shared by the local clamping
    force at construction and later by secondary helix dynamics.
    """

    axial_spring: AxialSpringForceSpec
    helix_force: SecondaryHelixForceSpec


def build_torque_reactive_secondary(
    *,
    spec: TorqueReactiveSecondarySpec,
    helix_profile: HelixProfile,
) -> PulleyActuator:
    """
    Build the secondary as a normal ``PulleyActuator``.

    The returned object is only an axial-force aggregator. Movable-sheave
    rotational inertia belongs to resolved inertia and later secondary
    helix dynamics, not to this clamping construction.
    """

    return PulleyActuator(
        AxialSpringForce(spec.axial_spring),
        SecondaryHelixForce(
            spec=spec.helix_force,
            helix_profile=helix_profile,
        ),
    )
