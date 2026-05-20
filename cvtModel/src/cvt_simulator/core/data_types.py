from dataclasses import dataclass
from typing import Union


## Pulley stuff (ported from models/dataTypes.py)
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
	feedbackTorque: float
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
class BeltWrapBreakdown:
	wrap_angle: float  # Belt wrap angle around pulley [rad]
	axial_belt_force: float  # Axial force contribution from the belt [N]

# Overall
@dataclass
class PulleyForces:
	pulley_breakdown: Union[PrimaryForceBreakdown, SecondaryForceBreakdown]
	belt_wrap: BeltWrapBreakdown
	net: float
	
@dataclass
class CvtDynamicsBreakdown:
    primaryPulleyState: PulleyForces
    secondaryPulleyState: PulleyForces
    friction: float
    acceleration: float
    net: float
		






