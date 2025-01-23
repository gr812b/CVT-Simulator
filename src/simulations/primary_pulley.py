import numpy as np
from utils.theoretical_models import TheoreticalModels as tm


class PrimaryPulley:
    def __init__(
        self,
        spring_coeff_comp: float,  # N/m
        initial_compression: float,  # m
        flyweight_mass: float,  # kg
        initial_flyweight_radius: float,  # m
        # TODO: Add fields for ramp geometry
    ):
        self.spring_coeff_comp = spring_coeff_comp
        self.initial_compression = initial_compression
        self.flyweight_mass = flyweight_mass
        self.initial_flyweight_radius = initial_flyweight_radius

    def calculate_flyweight_force(
        self, shift_distance: float, angular_velocity: float
    ) -> float:
        centrifugal_force = tm.centrifugal_force(
            self.flyweight_mass,
            angular_velocity,
            self.initial_flyweight_radius + shift_distance,
        )
        return centrifugal_force * np.tan(np.pi / 6)  # TODO: Calculate ramp angle

    def calculate_spring_comp_force(self, shift_distance: float) -> float:
        return tm.hookes_law_comp(
            self.spring_coeff_comp,
            self.initial_compression + shift_distance,
        )

    def calculate_force(self, shift_distance: float, angular_velocity: float) -> float:
        return self.calculate_flyweight_force(
            shift_distance, angular_velocity
        ) - self.calculate_spring_comp_force(shift_distance)
