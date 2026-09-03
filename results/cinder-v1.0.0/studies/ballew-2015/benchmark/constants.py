"""Frozen source and reconstruction constants for the Ballew (2015) benchmark."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import cos, radians

INCH_TO_METRE = 0.0254


@dataclass(frozen=True, slots=True)
class BallewPublishedParameters:
    """Values transcribed from Ballew Tables A1/B1 and Chapters 4/5."""

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

    simulation_duration_s: float = 5.0
    initial_ratio: float = 2.2
    initial_input_rpm: float = 2500.0
    initial_output_rpm: float = 1136.0
    engine_torque_nm: float = 18.0
    output_axial_force_n: float = 2000.0

    material_test_belt: str = "Gates G-Force 26C3596"

    figure39_core_height_m: float = 0.30 * INCH_TO_METRE
    figure39_core_outer_width_m: float = 1.18 * INCH_TO_METRE
    figure39_core_inner_width_m: float = 1.05 * INCH_TO_METRE
    figure39_cord_depth_from_outer_m: float = 0.05 * INCH_TO_METRE

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


def _ballew_mu_to_cinder_lambda(mu: float) -> float:
    """A10: preserve Ballew gross tangential capacity in CINDER 1.0.0.

    Ballew's nodal friction uses ``F_t = mu F_Z`` and his axial search enforces
    ``sum(F_Z) = F_clamp``. CINDER 1.0.0 instead defines ``N`` as the physical
    integrated normal load over both sheave faces. With symmetric face sharing,
    its zero-sheave-mass axial row is

        F_clamp - N cos(beta) / 2 = 0,

    so ``N = 2 F_clamp / cos(beta)``. Since CINDER traction is ``Q = lambda N``,
    preserving Ballew's gross capacity ``Q_max = mu F_clamp`` requires

        lambda = mu cos(beta) / 2.

    This is a force-normalization bridge, not a fitted friction coefficient.
    """

    return 0.5 * mu * cos(radians(PUBLISHED.sheave_half_angle_deg))


CINDER_STATIC_TRACTION_LAMBDA_LIMIT = _ballew_mu_to_cinder_lambda(
    PUBLISHED.static_friction_coefficient
)
CINDER_KINETIC_TRACTION_LAMBDA_MAGNITUDE = _ballew_mu_to_cinder_lambda(
    PUBLISHED.kinetic_friction_coefficient
)

# A11: simplest dimensionally consistent interpretation of Ballew's Kff.
RECONSTRUCTED_CONTROLLER_FEED_FORWARD_FORCE_N = (
    PUBLISHED.feed_forward_gain * PUBLISHED.output_axial_force_n
)

# A2: source does not report these environmental constants.
RECONSTRUCTED_AIR_DENSITY_KG_PER_M3 = 1.225
RECONSTRUCTED_GRAVITY_M_PER_S2 = 9.80665
RECONSTRUCTED_ROLLING_SPEED_REGULARIZATION_M_PER_S = 0.01

# A1/A9: preserve Ballew's stated total output pulley + ATV inertia.
REFLECTED_ATV_TRANSLATION_INERTIA_KG_M2 = PUBLISHED.atv_mass_kg * (
    PUBLISHED.tire_radius_m / PUBLISHED.transmission_ratio
) ** 2
DIRECT_SECONDARY_BOUNDARY_INERTIA_KG_M2 = (
    PUBLISHED.output_pulley_and_atv_inertia_kg_m2
    - PUBLISHED.output_pulley_inertia_kg_m2
    - REFLECTED_ATV_TRANSLATION_INERTIA_KG_M2
)


def resolved_parameter_document() -> dict[str, object]:
    """Return the JSON-safe frozen parameter set used by the study."""

    return {
        "published": asdict(PUBLISHED),
        "reconstruction": {
            "cinder_static_traction_lambda_limit": CINDER_STATIC_TRACTION_LAMBDA_LIMIT,
            "cinder_kinetic_traction_lambda_magnitude": CINDER_KINETIC_TRACTION_LAMBDA_MAGNITUDE,
            "controller_feed_forward_force_N": RECONSTRUCTED_CONTROLLER_FEED_FORWARD_FORCE_N,
            "air_density_kg_per_m3": RECONSTRUCTED_AIR_DENSITY_KG_PER_M3,
            "gravity_m_per_s2": RECONSTRUCTED_GRAVITY_M_PER_S2,
            "rolling_speed_regularization_m_per_s": (
                RECONSTRUCTED_ROLLING_SPEED_REGULARIZATION_M_PER_S
            ),
            "reflected_atv_translation_inertia_kg_m2": (
                REFLECTED_ATV_TRANSLATION_INERTIA_KG_M2
            ),
            "direct_secondary_boundary_inertia_kg_m2": (
                DIRECT_SECONDARY_BOUNDARY_INERTIA_KG_M2
            ),
        },
    }
