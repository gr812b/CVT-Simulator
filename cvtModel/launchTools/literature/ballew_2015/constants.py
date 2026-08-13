"""Published constants for the Ballew (2015) transient CVT benchmark."""

from __future__ import annotations

from dataclasses import dataclass
from math import radians, tan


INCH_TO_METRE = 0.0254


@dataclass(frozen=True, slots=True)
class BallewPublishedParameters:
    """Values transcribed directly from Ballew Tables A1/B1 and Chapter 4/5."""

    # Table A1: system constants.
    sheave_half_angle_deg: float = 15.0
    center_distance_m: float = 0.2421
    input_radius_max_m: float = 0.0838
    input_radius_min_m: float = 0.0159
    output_radius_max_m: float = 0.0838
    output_radius_min_m: float = 0.0159
    input_pulley_and_engine_inertia_kg_m2: float = 0.008
    output_pulley_inertia_kg_m2: float = 0.002
    output_pulley_and_atv_inertia_kg_m2: float = 1.275
    belt_length_m: float = 0.8636
    # Transcribed exactly as printed. It is not used as CINDER section width;
    # the value is incompatible with Ballew's own Figure 39 belt section.
    # See reconstruction A4.
    belt_width_m: float = 0.152
    belt_mass_kg: float = 1.0
    static_friction_coefficient: float = 0.55
    kinetic_friction_coefficient: float = 0.40
    stuck_relative_velocity_threshold_m_per_s: float = 0.02
    transmission_ratio: float = 8.93
    atv_mass_kg: float = 226.0
    frontal_area_m2: float = 1.39
    tire_radius_m: float = 0.317
    aerodynamic_drag_coefficient: float = 1.0
    rolling_resistance_coefficient: float = 0.048

    # Chapter 5 / Table B1: simulated vehicle-acceleration initial conditions/inputs.
    simulation_duration_s: float = 5.0
    initial_ratio: float = 2.2
    initial_input_rpm: float = 2500.0
    initial_output_rpm: float = 1136.0
    engine_torque_nm: float = 18.0
    output_axial_force_n: float = 2000.0

    # Chapter 4 provenance. All material tests were performed on this belt.
    material_test_belt: str = "Gates G-Force 26C3596"

    # Figure 39 (printed p. 54 / PDF p. 64): the minimum trapezoidal section
    # Ballew uses for his bending-inertia calculation. The dashed neutral-axis
    # / cord line is 0.25 in above the bottom of a 0.30 in-high section, hence
    # 0.05 in inward from the outer/top surface. Reconstruction A4 uses this as
    # CINDER's equivalent smooth load-carrying core, not as the literal cogged
    # belt envelope.
    figure39_core_height_m: float = 0.30 * INCH_TO_METRE
    figure39_core_outer_width_m: float = 1.18 * INCH_TO_METRE
    figure39_core_inner_width_m: float = 1.05 * INCH_TO_METRE
    figure39_cord_depth_from_outer_m: float = 0.05 * INCH_TO_METRE

    # Reference-model details retained for provenance, not CINDER inputs.
    node_count: int = 50
    reference_time_step_s: float = 1.0e-5
    initial_node_spacing_m: float = 0.0173
    node_mass_kg: float = 0.02
    longitudinal_stiffness_n_per_m: float = 54_690_000.0
    longitudinal_damping_n_s_per_m: float = 14.7905
    angular_stiffness_nm_per_rad: float = 10.4215
    angular_damping_nm_s_per_rad: float = 0.02
    axial_stiffness_n_per_m: float = 604_520.0
    feed_forward_gain: float = 1.2
    proportional_gain: float = 5.0
    integral_gain: float = 75.0


PUBLISHED = BallewPublishedParameters()


# Reconstruction A10: Ballew's published mu values multiply each node's axial
# sheave-compression reaction F_Z directly (his Eqs. 29-31). CINDER's reduced
# traction relation instead uses F_t = lambda N with N = 2 F_clamp tan(beta)
# for the algebraic zero-sheave-mass clamp row. Since Ballew's search enforces
# sum(F_Z) = F_clamp, preserving the same gross tangential capacity requires
# lambda = mu / (2 tan(beta)). These are translation-layer traction limits, not
# reinterpreted material Coulomb coefficients. See RECONSTRUCTION.md A10.
def _ballew_mu_to_cinder_lambda(mu: float) -> float:
    return mu / (2.0 * tan(radians(PUBLISHED.sheave_half_angle_deg)))


CINDER_STATIC_TRACTION_LAMBDA_LIMIT = _ballew_mu_to_cinder_lambda(
    PUBLISHED.static_friction_coefficient
)
CINDER_KINETIC_TRACTION_LAMBDA_MAGNITUDE = _ballew_mu_to_cinder_lambda(
    PUBLISHED.kinetic_friction_coefficient
)

# Reconstruction A11: the thesis publishes PI gains and a dimensionless
# feed-forward gain but not the controller equation. The source-native closed-
# loop reconstruction uses the simplest dimensionally consistent interpretation:
# feed-forward primary clamp = K_ff * fixed secondary clamp. This is deliberately
# isolated here and documented as an inference, not source fact or fitted value.
RECONSTRUCTED_CONTROLLER_FEED_FORWARD_FORCE_N = (
    PUBLISHED.feed_forward_gain * PUBLISHED.output_axial_force_n
)

# Reconstruction A2: Ballew does not report air density. See RECONSTRUCTION.md.
RECONSTRUCTED_AIR_DENSITY_KG_PER_M3 = 1.225

# Reconstruction A2: road-load constants not reported by Ballew.
# See RECONSTRUCTION.md.
RECONSTRUCTED_GRAVITY_M_PER_S2 = 9.80665
RECONSTRUCTED_ROLLING_SPEED_REGULARIZATION_M_PER_S = 0.01

# Reconstruction A1/A9: preserve Ballew's published total output pulley + ATV
# inertia while using the reported transmission ratio for the simulated vehicle
# boundary. The output torque itself is not prescribed; it comes from road load.
# See RECONSTRUCTION.md.
REFLECTED_ATV_TRANSLATION_INERTIA_KG_M2 = PUBLISHED.atv_mass_kg * (
    PUBLISHED.tire_radius_m / PUBLISHED.transmission_ratio
) ** 2
DIRECT_SECONDARY_BOUNDARY_INERTIA_KG_M2 = (
    PUBLISHED.output_pulley_and_atv_inertia_kg_m2
    - PUBLISHED.output_pulley_inertia_kg_m2
    - REFLECTED_ATV_TRANSLATION_INERTIA_KG_M2
)
