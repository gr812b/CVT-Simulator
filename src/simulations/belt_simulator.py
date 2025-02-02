import numpy as np
import math
from utils.theoretical_models import TheoreticalModels as tm


class BeltSimulator:
    def __init__(self, density: float, cross_sectional_area: float):
        self.density = density
        self.cross_sectional_area = cross_sectional_area

    def calculate_centrifugal_force(
        self, ω: float, shift_distance: float, sheave_angle: float, wrap_angle: float
    ) -> float:
        radius = tm.shift_to_pulley_radius_prim(shift_distance, sheave_angle)

        length = radius * wrap_angle
        mass = self.density * self.cross_sectional_area * length

        return tm.centrifugal_force(mass, ω, radius)

    def radial_force_from_clamping(
        self, clamping_force: float, sheave_angle: float
    ) -> float:
        return 2 * clamping_force * np.tan(sheave_angle / 2)

    def calculate_net_radial_force(
        self,
        ω: float,
        shift_distance: float,
        sheave_angle: float,
        wrap_angle: float,
        clamping_force: float,
    ) -> float:
        centrifugal_force = self.calculate_centrifugal_force(
            ω, shift_distance, sheave_angle, wrap_angle
        )
        radial_force = self.radial_force_from_clamping(clamping_force, sheave_angle)
        distribution_factor = 2 * np.sin(
            wrap_angle / 2
        )  # This comes from the integral based on the force distribution
        return (centrifugal_force + radial_force) * distribution_factor

    def calculate_slack_tension(
        self,
        ω: float,
        shift_distance: float,
        clamping_force: float,
        sheave_angle: float,
        wrap_angle: float,
        μ: float,
    ) -> float:
        θ = abs((wrap_angle - np.pi) / 2)
        denominator = np.cos(θ) * (
            1 + math.exp(μ * wrap_angle)
        )  # Derived from tension, angles and capstan equation
        radial_force = self.calculate_net_radial_force(
            ω, shift_distance, sheave_angle, wrap_angle, clamping_force
        )
        return radial_force / denominator

    def calculate_max_transferable_torque(
        self, tension: float, μ: float, wrap_angle: float, r: float
    ) -> float:
        return tension * r * (np.exp(μ * wrap_angle) - 1)
