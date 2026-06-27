from __future__ import annotations

from dataclasses import dataclass

from .forces import (
    AxialSpringForce,
    AxialSpringForceSpec,
    CentrifugalRampForce,
    CentrifugalRampForceSpec,
    HelixTorqueReactionForce,
    HelixTorqueReactionForceSpec,
    TorsionalSpringForce,
    TorsionalSpringForceSpec,
)
from .pulley_actuator import PulleyActuator


@dataclass(frozen=True, slots=True)
class CentrifugalPrimarySpec:
    """
    Concrete centrifugal primary composed from reusable force laws.

    Standard configuration:
        centrifugal ramp + axial return spring.

    Optional helix terms allow a torque-reactive or torsion-spring primary
    without changing the actuator or closure structure.
    """

    centrifugal_ramp: CentrifugalRampForceSpec
    axial_spring: AxialSpringForceSpec
    torsional_spring: TorsionalSpringForceSpec | None = None
    torque_reaction: HelixTorqueReactionForceSpec | None = None


def build_centrifugal_primary(
    spec: CentrifugalPrimarySpec,
) -> PulleyActuator:
    """
    Build a conventional centrifugal primary.

    Under the local convention x_p = s, positive output force closes the
    primary. Its axial spring is normally configured with
    compression_per_axial_position = +1, so it produces opening force.
    """

    force_laws = [
        CentrifugalRampForce(spec.centrifugal_ramp),
        AxialSpringForce(spec.axial_spring),
    ]

    if spec.torsional_spring is not None:
        force_laws.append(TorsionalSpringForce(spec.torsional_spring))

    if spec.torque_reaction is not None:
        force_laws.append(
            HelixTorqueReactionForce(spec.torque_reaction)
        )

    return PulleyActuator(*force_laws)
