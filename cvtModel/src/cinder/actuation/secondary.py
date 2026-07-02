"""Construction of the ordinary torque-reactive secondary pulley actuator."""

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
    """
    Secondary clamping-force parameters.

    Helix geometry is intentionally not stored here. ``CVTDynamicsModel`` owns
    the one physical ``HelixProfile``, evaluates it once per snapshot, and
    supplies that evaluated kinematics object to the secondary helix force.
    The authoritative movable-sheave inertia belongs to ``SecondaryInertia``.
    ``CVTDynamicsModel.snapshot()`` passes that one value into the helix force
    state so the helix relation and secondary rotational row stay synchronized.
    ``SecondaryHelixForceSpec`` may retain a legacy consistency value, but it
    is not the source used by a full dynamics snapshot.
    """

    axial_spring: AxialSpringForceSpec
    helix_force: SecondaryHelixForceSpec


def build_torque_reactive_secondary(
    *,
    spec: TorqueReactiveSecondarySpec,
) -> PulleyActuator:
    """
    Build the secondary as one normal ``PulleyActuator``.

    The returned actuator sums direct axial-spring force and the
    inertia-inclusive torque-reactive helix force. It has no helix geometry of
    its own; snapshot construction supplies the one shared helix evaluation to
    the force law at runtime.
    """

    return PulleyActuator(
        AxialSpringForce(spec.axial_spring),
        SecondaryHelixForce(spec=spec.helix_force),
    )
