import numpy as np
import math
from utils.theoretical_models import TheoreticalModels as tm
from constants.car_specs import (
  BELT_WIDTH
)


class BeltSimulator:
    def __init__(
        self,
        density: float,
        cross_sectional_area: float,
        μ_static: float,
        μ_kinetic: float,
        primary: bool,
    ):
        self.density = density
        self.cross_sectional_area = cross_sectional_area
        self.μ_static = μ_static
        self.μ_kinetic = μ_kinetic
        self.primary = primary


    def calculate_centrifugal_force(
        self, ω: float, shift_distance: float, sheave_angle: float, wrap_angle: float
    ) -> float:
        if self.primary:
          radius = tm.shift_to_pulley_radius_prim(shift_distance, sheave_angle)
          print("primary radius: ", radius)
        else:
          radius = tm.shift_to_pulley_radius_sec(shift_distance, sheave_angle, BELT_WIDTH)
          print("secondary radius: ", radius)

        

        length = radius * wrap_angle
        mass = self.density * self.cross_sectional_area * length

        return tm.centrifugal_force(mass, ω, radius)

    def radial_force_from_clamping(
        self, clamping_force: float, sheave_angle: float
    ) -> float:
        return 2 * clamping_force * np.tan(sheave_angle / 2)

    def calculate_net_radial_force(
        self,
        centrifugal_force: float,
        radial_force: float,
        wrap_angle: float,
    ) -> float:
        # factor comes from the integral based on the force distribution
        return (centrifugal_force + radial_force) * 2 * np.sin(wrap_angle / 2)
    
    def calculate_radial_force(
        self,
        ω: float,
        shift_distance: float,
        sheave_angle: float,
        wrap_angle: float,
        clamping_force: float
    ) -> float:
        centrifugal_force = self.calculate_centrifugal_force(ω, shift_distance, sheave_angle, wrap_angle)
        radial_force = self.radial_force_from_clamping(clamping_force, sheave_angle)
        # print(f"Centrifugal force: {centrifugal_force}, Radial force: {radial_force}")
        return self.calculate_net_radial_force(centrifugal_force, radial_force, wrap_angle)

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
