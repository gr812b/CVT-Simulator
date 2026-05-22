from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Union

from cvt_simulator.geometry.cvt_geometry import CVTGeometryResult



# -------------------------------------------------
# Pulley stuff
# -------------------------------------------------

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

# -------------------------------------------------
# Torque stuff
# -------------------------------------------------

@dataclass
class ExternalLoadForceBreakdown:
	rolling_resistance_force: float
	incline_force: float
	drag_force: float
	net_force_at_car: float
	rolling_resistance_torque_at_secondary: float
	incline_torque_at_secondary: float
	drag_torque_at_secondary: float
	net_torque_at_secondary: float


@dataclass
class EngineTorqueBreakdown:
  engine_torque: float
  engine_speed: float
  engine_power: float

@dataclass
class DrivetrainAccelerationBreakdown:
	ω_p_dot: float
	ω_s_dot: float
	v_b_dot: float
	# Engine and load breakdowns included for traceability
	engine_breakdown: EngineTorqueBreakdown
	external_load_breakdown: ExternalLoadForceBreakdown
	# Contact torques that produced these accelerations
	tau_p: float
	tau_s: float

# -------------------------------------------------
# Slip stuff
# -------------------------------------------------


class SlipBranch(Enum):
	NO_SLIP = auto()
	PRIMARY_SLIP = auto()
	SECONDARY_SLIP = auto()
	BOTH_SLIP = auto()


@dataclass
class NoSlipBreakdown:
	r_p: float
	r_s: float
	r_p_dot: float
	r_s_dot: float
	tau_engine_over_r_p: float
	tau_load_over_r_s: float
	primary_inertia_term: float
	secondary_inertia_term: float
	numerator: float
	denominator: float


@dataclass
class NoSlipResult:
	v_b_dot_ns: float
	tau_p_ns: float
	tau_s_ns: float
	breakdown: NoSlipBreakdown


@dataclass
class SlipMetricsResult:
	primary_relative_speed: float
	secondary_relative_speed: float
	primary_slip_direction: float
	secondary_slip_direction: float
	primary_admissible: bool
	secondary_admissible: bool
	admissibility: TorqueAdmissibilityResult
	no_slip: NoSlipResult


@dataclass
class BranchTorqueResult:
	branch: SlipBranch
	tau_p: float
	tau_s: float


@dataclass
class ContactTorqueResult:
	tau_p: float
	tau_s: float
	branch: SlipBranch
	slip_metrics: SlipMetricsResult
	branch_result: BranchTorqueResult



@dataclass
class PrimaryTorqueAdmissibilityBreakdown:
	shift_distance: float
	wrap_angle: float
	effective_radius: float
	centroid_radius: float
	centroid_radius_rate: float
	axial_clamping_force: float
	belt_centripetal_term: float
	friction_coefficient: float
	sheave_half_angle: float
	tau_p_stick_limit: float
	tau_p_stick_upper: float
	tau_p_stick_lower: float


@dataclass
class SecondaryTorqueAdmissibilityBreakdown:
	shift_distance: float
	wrap_angle: float
	effective_radius: float
	centroid_radius: float
	centroid_radius_rate: float
	helix_rotation: float
	helix_rotation_rate: float
	spring_torsion_term: float
	spring_comp_term: float
	belt_centripetal_term: float
	friction_coefficient: float
	sheave_half_angle: float
	denominator_upper: float
	denominator_lower: float
	tau_stick_upper: float
	tau_stick_lower: float


@dataclass
class TorqueAdmissibilityResult:
	primary: PrimaryTorqueAdmissibilityBreakdown
	secondary: SecondaryTorqueAdmissibilityBreakdown
	primary_tau_p_stick_upper: float
	primary_tau_p_stick_lower: float
	secondary_tau_stick_upper: float
	secondary_tau_stick_lower: float


# -------------------------------------------------
# Overall
# -------------------------------------------------

@dataclass
class ContactDynamicsBreakdown:
    contact: ContactTorqueResult
    drivetrain: DrivetrainAccelerationBreakdown
    shift: CvtDynamicsBreakdown
    geometry: CVTGeometryResult

