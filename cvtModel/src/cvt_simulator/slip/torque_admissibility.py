"""Torque admissibility equations.

Implements the no-slip admissibility expressions for the primary and
secondary pulleys using the pulley component constants plus the no-slip
belt acceleration result.
"""
from dataclasses import dataclass

from cvt_simulator.geometry.cvt_geometry import CVT_GEOMETRY
import numpy as np

from cvt_simulator.components.primary_pulley import PrimaryPulley
from cvt_simulator.components.secondary_pulley import SecondaryPulley
from cvt_simulator.constants.car_specs import BELT_CROSS_SECTIONAL_AREA, SHEAVE_ANGLE
from cvt_simulator.constants.constants import (
	RUBBER_ALUMINUM_KINETIC_FRICTION,
	RUBBER_ALUMINUM_STATIC_FRICTION,
	RUBBER_DENSITY,
)
from cvt_simulator.core.system_state import SystemState
from cvt_simulator.slip.no_slip_candidate import NoSlipResult
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm


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
	tau_p_ns: float
	tau_s_ns: float
	v_b_dot_ns: float


class TorqueAdmissibility:
	"""Evaluate no-slip torque admissibility for the CVT."""

	def __init__(
		self,
		primary_pulley: PrimaryPulley,
		secondary_pulley: SecondaryPulley,
	) -> None:
		self.primary_pulley = primary_pulley
		self.secondary_pulley = secondary_pulley
		self.mu_static = RUBBER_ALUMINUM_STATIC_FRICTION
		self.mu_kinetic = RUBBER_ALUMINUM_KINETIC_FRICTION
		self.beta = SHEAVE_ANGLE / 2
		self.cvt = CVT_GEOMETRY

	def get_breakdown(
		self,
		state: SystemState,
		no_slip: NoSlipResult,
	) -> TorqueAdmissibilityResult:
		"""Compute primary and secondary torque admissibility.

		Args:
			state: Current system state.
			no_slip: No-slip candidate result carrying v_b_dot_ns and torques.

		Returns:
			TorqueAdmissibilityResult with explicit term breakdowns.
		"""
		primary_breakdown = self._primary_breakdown(state, no_slip)
		secondary_breakdown = self._secondary_breakdown(state, no_slip)

		return TorqueAdmissibilityResult(
			primary=primary_breakdown,
			secondary=secondary_breakdown,
			tau_p_ns=no_slip.tau_p_ns,
			tau_s_ns=no_slip.tau_s_ns,
			v_b_dot_ns=no_slip.v_b_dot_ns,
		)

	def _primary_breakdown(
		self,
		state: SystemState,
		no_slip: NoSlipResult,
	) -> PrimaryTorqueAdmissibilityBreakdown:
		s = state.s

		wrap_angle = tm.primary_wrap_angle(s)
		effective_radius = tm.primary_effective_radius(s)
		centroid_radius = tm.primary_centroid_radius(s)
		centroid_radius_rate = self.cvt.primary_outer_radius_time_derivative(s, state.s_dot)
		# Use pulley-only clamping force (exclude belt centrifugal contribution)
		axial_clamping_force = self.primary_pulley.calculate_axial_clamping_force(state).pulley_breakdown.net

		belt_centripetal_term = RUBBER_DENSITY * BELT_CROSS_SECTIONAL_AREA * wrap_angle * (
			centroid_radius * no_slip.v_b_dot_ns + centroid_radius_rate * state.v_b
		)

		base_limit = effective_radius * (
			2.0 * self.mu_static * np.tan(self.beta) * axial_clamping_force
			- belt_centripetal_term
		)
		tau_p_stick_upper = base_limit
		tau_p_stick_lower = -base_limit

		return PrimaryTorqueAdmissibilityBreakdown(
			shift_distance=s,
			wrap_angle=wrap_angle,
			effective_radius=effective_radius,
			centroid_radius=centroid_radius,
			centroid_radius_rate=centroid_radius_rate,
			axial_clamping_force=axial_clamping_force,
			belt_centripetal_term=belt_centripetal_term,
			friction_coefficient=self.mu_static,
			sheave_half_angle=self.beta,
			tau_p_stick_limit=base_limit,
			tau_p_stick_upper=tau_p_stick_upper,
			tau_p_stick_lower=tau_p_stick_lower,
		)

	def _secondary_breakdown(
		self,
		state: SystemState,
		no_slip: NoSlipResult,
	) -> SecondaryTorqueAdmissibilityBreakdown:
		s = state.s

		wrap_angle = tm.secondary_wrap_angle(s)
		effective_radius = tm.secondary_effective_radius(s)
		centroid_radius = tm.secondary_centroid_radius(s)
		centroid_radius_rate = self.cvt.secondary_outer_radius_time_derivative(s, state.s_dot)

		helix_rotation = self.secondary_pulley.initial_rotation + self.secondary_pulley.helix_ramp.theta(s)
		helix_rotation_rate = self.secondary_pulley.helix_ramp.dtheta_dx(s)

		spring_torsion_term = self.secondary_pulley.spring_coeff_tors * helix_rotation * helix_rotation_rate
		spring_comp_term = self.secondary_pulley.spring_coeff_comp * (
			self.secondary_pulley.initial_compression + s
		)

		belt_centripetal_term = RUBBER_DENSITY * BELT_CROSS_SECTIONAL_AREA * wrap_angle * (
			centroid_radius * no_slip.v_b_dot_ns + centroid_radius_rate * state.v_b
		)

		common_numerator = (
			self.mu_static * np.tan(self.beta) * spring_torsion_term
			+ 2.0 * self.mu_static * np.tan(self.beta) * spring_comp_term
			- belt_centripetal_term
		)
		numerator = effective_radius * common_numerator

		denominator_upper = 1.0 - effective_radius * self.mu_static * np.tan(self.beta) * helix_rotation_rate
		denominator_lower = 1.0 + effective_radius * self.mu_static * np.tan(self.beta) * helix_rotation_rate

		tau_stick_upper = numerator / denominator_upper
		tau_stick_lower = -numerator / denominator_lower

		return SecondaryTorqueAdmissibilityBreakdown(
			shift_distance=s,
			wrap_angle=wrap_angle,
			effective_radius=effective_radius,
			centroid_radius=centroid_radius,
			centroid_radius_rate=centroid_radius_rate,
			helix_rotation=helix_rotation,
			helix_rotation_rate=helix_rotation_rate,
			spring_torsion_term=spring_torsion_term,
			spring_comp_term=spring_comp_term,
			belt_centripetal_term=belt_centripetal_term,
			friction_coefficient=self.mu_static,
			sheave_half_angle=self.beta,
			denominator_upper=denominator_upper,
			denominator_lower=denominator_lower,
			tau_stick_upper=tau_stick_upper,
			tau_stick_lower=tau_stick_lower,
		)
