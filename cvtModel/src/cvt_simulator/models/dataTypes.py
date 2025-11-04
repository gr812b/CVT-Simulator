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

# All possible pulley breakdown types
PulleyBreakdowns = Union[PrimaryForceBreakdown, SecondaryForceBreakdown]

@dataclass
class PulleyForces:
    """
    Core outputs that every pulley must provide.
    
    These three values are sufficient to drive the CVT simulation regardless
    of the internal mechanism (flyweights, helix, PID, etc.).
    """
    clamping_force: float  # Axial force pushing pulley halves together [N]
    radial_force: float    # Total radial force on belt [N]
    max_torque: float      # Maximum transferable torque before slip [N⋅m]


@dataclass
class PulleyState:
    """
    Complete pulley state including forces and geometric properties.
    
    Combines the core forces with geometric data needed for system-level
    calculations (slip model, shift dynamics, etc.).
    """
    forces: PulleyForces
    
    # Geometric properties at current shift position
    wrap_angle: float           # Belt wrap angle around pulley [rad]
    radius: float              # Effective pitch radius [m]
    angular_velocity: float    # Pulley angular velocity [rad/s]
    
    # Force components (for analysis/debugging)
    radial_from_clamping: float      # Radial force contribution from clamping [N]
    radial_from_centrifugal: float   # Radial force from belt centrifugal effect [N]
    
    # Implementation-specific breakdown (Union of all concrete breakdown types)
    breakdown: PulleyBreakdowns

@dataclass
class CvtSystemForceBreakdown:
    primaryPulleyState: PulleyState
    secondaryPulleyState: PulleyState
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
    t_c_before_clamp: float
    t_max_prim: float
    t_max_sec: float
    cvt_ratio_derivative: float
    is_slipping: bool


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
