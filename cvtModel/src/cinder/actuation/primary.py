"""Convenience construction for CINDER's conventional centrifugal primary."""

from __future__ import annotations

from dataclasses import dataclass

from .forces import (
    AxialSpringForce,
    AxialSpringForceSpec,
    CentrifugalRampForce,
    CentrifugalRampForceSpec,
)
from .pulley_actuator import PulleyActuator


@dataclass(frozen=True, slots=True)
class CentrifugalPrimarySpec:
    """The standard primary: flyweight ramp plus opening return spring."""

    centrifugal_ramp: CentrifugalRampForceSpec
    axial_spring: AxialSpringForceSpec


def build_centrifugal_primary(
    spec: CentrifugalPrimarySpec,
) -> PulleyActuator:
    """Build a primary with closing flyweight force and return-spring force."""

    return PulleyActuator(
        CentrifugalRampForce(spec.centrifugal_ramp),
        AxialSpringForce(spec.axial_spring),
    )
