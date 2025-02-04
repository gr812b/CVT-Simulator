import numpy as np
import math
from utils.theoretical_models import TheoreticalModels as tm
from constants.car_specs import (
    BELT_WIDTH,
    INNER_PRIMARY_PULLEY_RADIUS,
    INNER_SECONDARY_PULLEY_RADIUS,
    SHEAVE_ANGLE,
    BELT_CROSS_SECTIONAL_AREA,
)
from constants.constants import RUBBER_DENSITY


class BeltSimulator:
    def __init__(
        self,
        μ_static: float,
        μ_kinetic: float,
        primary: bool,
    ):
        self.μ_static = μ_static
        self.μ_kinetic = μ_kinetic
        self.primary = primary

    def calculate_centrifugal_force(
        self, ω: float, shift_distance: float, wrap_angle: float
    ) -> float:
        if self.primary:
            radius = tm.current_primary_radius(
                shift_distance, SHEAVE_ANGLE, INNER_PRIMARY_PULLEY_RADIUS
            )
        else:
            radius = tm.current_secondary_radius(
                shift_distance, SHEAVE_ANGLE, BELT_WIDTH, INNER_SECONDARY_PULLEY_RADIUS
            )

        length = radius * wrap_angle
        mass = RUBBER_DENSITY * BELT_CROSS_SECTIONAL_AREA * length

        return tm.centrifugal_force(mass, ω, radius)

    def radial_force_from_clamping(self, clamping_force: float) -> float:
        return 2 * clamping_force * np.tan(SHEAVE_ANGLE / 2)

    def calculate_net_radial_force(
        self,
        centrifugal_force: float,
        radial_force: float,
        wrap_angle: float,
    ) -> float:
        # factor comes from the integral based on the force distribution
        return (centrifugal_force + radial_force) * 2 * np.sin(wrap_angle / 2)

    def calculate_radial_force(
        self, ω: float, shift_distance: float, wrap_angle: float, clamping_force: float
    ) -> float:
        centrifugal_force = self.calculate_centrifugal_force(
            ω, shift_distance, wrap_angle
        )
        radial_force = self.radial_force_from_clamping(clamping_force)
        # print(f"Centrifugal force: {centrifugal_force}, Radial force: {radial_force}, yea: {np.sin(wrap_angle / 2)}")
        return self.calculate_net_radial_force(
            centrifugal_force, radial_force, wrap_angle
        )

    def calculate_slack_tension(
        self,
        radial_force: float,
        wrap_angle: float,
        μ: float,
    ) -> float:
        θ = abs((wrap_angle - np.pi) / 2)
        denominator = np.cos(θ) * (
            1 + math.exp(μ * wrap_angle)
        )  # Derived from tension, angles and capstan equation
        return radial_force / denominator

    def calculate_max_transferable_torque(
        self, tension: float, μ: float, wrap_angle: float, radius: float
    ) -> float:
        return tension * radius * (np.exp(μ * wrap_angle) - 1)
