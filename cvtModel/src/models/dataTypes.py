from dataclasses import dataclass
from typing import Union

## Pulley stuff
@dataclass
class flyweightForceBreakdown:
    radius: float
    angular_velocity: float
    angle: float

    centrifugal_force: float # radius, mass, angular velocity
    angle_multiplier: float # tan(angle)
    net: float

@dataclass
class springCompForceBreakdown:
    initial_compression: float
    additional_compression: float

    initial_force: float # initial, coeff
    additional_force: float # additional, coeff
    net: float

@dataclass
class SpringTorsForceBreakdown:
    initial_rotation: float # TODO: Remove?
    additional_rotation: float

    initial_force: float
    additional_force: float
    net: float

@dataclass
class HelixForceBreakdown:
    feedbackTorque: float # TODO: See if this will breakdown
    springTorque: SpringTorsForceBreakdown
    angle: float
    radius: float

    angle_multiplier: float # The 2 * np.tan(angle) * radius
    net: float

@dataclass
class PrimaryForceBreakdown:
    flyweightForce: flyweightForceBreakdown
    springForce: springCompForceBreakdown
    net: float

@dataclass
class SecondaryForceBreakdown:
    springCompForce: springCompForceBreakdown
    helix_force: HelixForceBreakdown
    net: float

@dataclass
class BeltCentrifugalForceBreakdown:
    mass: float
    radius: float
    wrap_angle: float
    angular_velocity: float

    net: float
    
@dataclass
class RadialPulleyForceBreakdown:
    pulleyForce: Union[PrimaryForceBreakdown, SecondaryForceBreakdown]
    radialPulleyForce: float # Radial component
    beltCentrifugalForce: BeltCentrifugalForceBreakdown
    net: float

## Engine
@dataclass
class EngineForceBreakdown:
    torque: float
    power: float
    angular_velocity: float

## External load
@dataclass
class ExternalLoadForceBreakdown:
    incline_force: float
    drag_force: float
    net: float

## Car
@dataclass
class CarForceBreakdown:
    external_forces: ExternalLoadForceBreakdown
    engine_forces: EngineForceBreakdown
    acceleration: float
