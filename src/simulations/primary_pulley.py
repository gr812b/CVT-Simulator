import numpy as np
from utils.theoretical_models import TheoreticalModels as tm
from utils.ramp_representation import CircularSegment, LinearSegment, PiecewiseRamp
from constants.car_specs import MAX_SHIFT, INITIAL_FLYWEIGHT_RADIUS


class PrimaryPulley:
    def __init__(
        self,
        spring_coeff_comp: float,  # N/m
        initial_compression: float,  # m
        flyweight_mass: float,  # kg
        ramp_type: int
        # TODO: Add fields for ramp geometry
    ):
        self.spring_coeff_comp = spring_coeff_comp
        self.initial_compression = initial_compression
        self.flyweight_mass = flyweight_mass
        self.initial_flyweight_radius = INITIAL_FLYWEIGHT_RADIUS
        self.ramp_type = ramp_type
        
        # Initializing ramp
        if self.ramp_type == 1:
            self.ramp = PiecewiseRamp()
            self.ramp.add_segment(LinearSegment(x_start=0, x_end=MAX_SHIFT / 6, slope=-0.5))
            self.ramp.add_segment(
                CircularSegment(
                    x_start=MAX_SHIFT / 6,
                    x_end=MAX_SHIFT,
                    radius=0.005,
                    theta_start=1,
                    theta_end=np.pi / 2 - 0.5,
                )
            )
        elif self.ramp_type == 2:
            self.ramp = PiecewiseRamp()
            self.ramp.add_segment(LinearSegment(x_start=0, x_end=MAX_SHIFT / 6, slope=-0.5))
            self.ramp.add_segment(
                CircularSegment(
                    x_start=MAX_SHIFT / 6,
                    x_end=MAX_SHIFT,
                    radius=0.005,
                    theta_start=1,
                    theta_end=np.pi / 2 - 0.5,
                )
            )

    def calculate_flyweight_force(
        self, shift_distance: float, angular_velocity: float
    ) -> float:
        if shift_distance < 0:
            shift_distance = 0
        if shift_distance > MAX_SHIFT:
            shift_distance = MAX_SHIFT

        flyweight_radius = self.initial_flyweight_radius + self.ramp.height(
            shift_distance
        )
        centrifugal_force = tm.centrifugal_force(
            self.flyweight_mass,
            angular_velocity,
            flyweight_radius,
        )

        angle = np.arctan(self.ramp.slope(shift_distance))

        # print(f"Shift distance: {shift_distance:.2f}, Flyweight radius: {flyweight_radius:.2f}, Angular velocity: {angular_velocity:.2f}, Angle: {angle:.2f}")
        # print(f"Centrifugal force: {centrifugal_force:.2f}, Angle: {np.sin(angle):.5f}")
        return centrifugal_force * np.tan(angle)

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
        # print(f"Centrifugal force: {centrifugal_force:.2f}, Spring force: {spring_force:.2f}")
        return centrifugal_force - spring_force
