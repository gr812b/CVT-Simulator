import numpy as np
import math
from utils.theoretical_models import TheoreticalModels as tm
from constants.car_specs import SHEAVE_ANGLE, BELT_CROSS_SECTIONAL_AREA, BELT_HEIGHT
from constants.constants import (
    RUBBER_DENSITY,
    RUBBER_ALUMINUM_STATIC_FRICTION,
    RUBBER_ALUMINUM_KINETIC_FRICTION,
)


class BeltSimulator:
    def __init__(
        self,
        primary: bool,
    ):
        self.primary = primary
        self.μ_static = RUBBER_ALUMINUM_STATIC_FRICTION
        self.μ_kinetic = RUBBER_ALUMINUM_KINETIC_FRICTION

    def calculate_centrifugal_force(
        self, ω: float, shift_distance: float, wrap_angle: float
    ) -> float:
        if self.primary:
            radius = tm.outer_prim_radius(shift_distance) - BELT_HEIGHT / 2
        else:
            radius = tm.outer_sec_radius(shift_distance) - BELT_HEIGHT / 2

        length = radius * wrap_angle
        mass = RUBBER_DENSITY * BELT_CROSS_SECTIONAL_AREA * length

        # print(f"Primary: {self.primary}, Length: {length}, Wrap angle: {wrap_angle}, Radius: {radius}, Mass: {mass}, Total Mass:")

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
