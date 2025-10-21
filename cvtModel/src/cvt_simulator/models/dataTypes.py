from dataclasses import dataclass
from typing import Union


## Pulley stuff
@dataclass
class flyweightForceBreakdown:
    radius: float
    angular_velocity: float
    angle: float

    centrifugal_force: float  # radius, mass, angular velocity
    angle_multiplier: float  # tan(angle)
    net: float


@dataclass
class springCompForceBreakdown:
    compression: float
    net: float


@dataclass
class SpringTorsForceBreakdown:
    rotation: float
    net: float


@dataclass
class HelixForceBreakdown:
    feedbackTorque: float  # TODO: See if this will breakdown
    springTorque: SpringTorsForceBreakdown
    angle: float
    radius: float

    angle_multiplier: float  # The 2 * np.tan(angle) * radius
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
    beltCentrifugalForce: BeltCentrifugalForceBreakdown
    radialPulleyForce: float  # Radial component
    net: float


@dataclass
class CvtSystemForceBreakdown:
    primaryRadialForce: RadialPulleyForceBreakdown
    secondaryRadialForce: RadialPulleyForceBreakdown
    friction: float
    acceleration: float
    cvt_ratio: float
    net: float


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
    acceleration: float


## Engine
@dataclass
class EngineForceBreakdown:
    torque: float
    power: float
    angular_velocity: float
    angular_acceleration: float


# Slip shenanigans
@dataclass
class SlipBreakdown:
    t_c: float
    t_max: float
    cvt_ratio_derivative: float


## System-level breakdown (single source of truth)
@dataclass
class SystemBreakdown:
    """
    Single source of truth for the entire system state.

    Solves the circular dependency problem by:
    1. Calculating all components in the correct dependency order
    2. Providing a single place to access any component's breakdown
    3. Eliminating duplication while maintaining clean interfaces

    Usage:
        system = system_model.get_breakdown(state)
        slip_data = system.slip
        engine_data = system.engine
        car_data = system.car
        cvt_data = system.cvt
    """

    slip: SlipBreakdown
    engine: EngineForceBreakdown
    car: CarForceBreakdown
    cvt: CvtSystemForceBreakdown
