"""Optional convenience builders for common actuator combinations.

These are composition helpers only.  The underlying ``PulleyActuator`` and
force laws are pulley-agnostic and can be installed in either ``PulleySpec``.
"""

from __future__ import annotations

from dataclasses import dataclass

from .forces import (
    AxialSpringForce,
    AxialSpringForceSpec,
    CentrifugalRampForce,
    CentrifugalRampForceSpec,
    FixedPivotFlyweightForce,
    FixedPivotFlyweightForceSpec,
    HelicalTorqueReactionForce,
    HelicalTorqueReactionSpec,
)
from .pulley_actuator import PulleyActuator


@dataclass(frozen=True, slots=True)
class CentrifugalActuatorSpec:
    centrifugal_ramp: CentrifugalRampForceSpec
    axial_spring: AxialSpringForceSpec


def build_centrifugal_actuator(spec: CentrifugalActuatorSpec) -> PulleyActuator:
    return PulleyActuator(
        CentrifugalRampForce(spec.centrifugal_ramp),
        AxialSpringForce(spec.axial_spring),
    )


@dataclass(frozen=True, slots=True)
class FixedPivotCentrifugalActuatorSpec:
    fixed_pivot_flyweight: FixedPivotFlyweightForceSpec
    axial_spring: AxialSpringForceSpec


def build_fixed_pivot_centrifugal_actuator(
    spec: FixedPivotCentrifugalActuatorSpec,
) -> PulleyActuator:
    return PulleyActuator(
        FixedPivotFlyweightForce(spec.fixed_pivot_flyweight),
        AxialSpringForce(spec.axial_spring),
    )


@dataclass(frozen=True, slots=True)
class TorqueReactiveActuatorSpec:
    axial_spring: AxialSpringForceSpec
    helical_reaction: HelicalTorqueReactionSpec


def build_torque_reactive_actuator(spec: TorqueReactiveActuatorSpec) -> PulleyActuator:
    return PulleyActuator(
        AxialSpringForce(spec.axial_spring),
        HelicalTorqueReactionForce(spec=spec.helical_reaction),
    )
