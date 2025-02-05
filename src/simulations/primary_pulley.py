import numpy as np
from utils.theoretical_models import TheoreticalModels as tm
from utils.ramp_representation import LinearSegment, CircularSegment, PiecewiseRamp


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
        # Initializing ramp
        self.ramp = PiecewiseRamp()
        self.ramp.add_segment(LinearSegment(x_start=0, x_end=0.01, slope=-0.75))
        self.ramp.add_segment(
            CircularSegment(x_start=0.01, x_end=0.05, radius=0.25, theta_fraction=0.95)
        )

    def calculate_flyweight_force(
        self, shift_distance: float, angular_velocity: float
    ) -> float:
        centrifugal_force = tm.centrifugal_force(
            self.flyweight_mass,
            angular_velocity,
            self.initial_flyweight_radius,  # TODO: Add some distance here
        )
        if shift_distance < 0:
            shift_distance = 0
        if shift_distance > 0.05:
            shift_distance = 0.05
        angle = np.arctan(np.abs(self.ramp.slope(shift_distance)))
        return centrifugal_force * np.sin(angle)  # TODO: Calculate ramp angle

    def calculate_spring_comp_force(self, compression: float) -> float:
        return tm.hookes_law_comp(
            self.spring_coeff_comp,
            self.initial_compression + compression,
        )

    def calculate_net_force(
        self, shift_distance: float, angular_velocity: float
    ) -> float:
        centrifugal_force = self.calculate_flyweight_force(
            shift_distance, angular_velocity
        )
        spring_force = self.calculate_spring_comp_force(shift_distance)
        return centrifugal_force - spring_force
