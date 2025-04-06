import math
import numpy as np
from utils.conversions import inch_to_meter
from utils.theoretical_models import TheoreticalModels as tm
from utils.ramp_representation import CircularSegment, CubicSpiralZeroK1, LinearSegment, PiecewiseRamp
from constants.car_specs import MAX_SHIFT, INITIAL_FLYWEIGHT_RADIUS


class PrimaryPulley:
    def __init__(
        self,
        spring_coeff_comp: float,  # N/m
        initial_compression: float,  # m
        flyweight_mass: float,  # kg
        ramp_type: int,
    ):
        self.spring_coeff_comp = spring_coeff_comp
        self.initial_compression = initial_compression
        self.flyweight_mass = flyweight_mass
        self.initial_flyweight_radius = INITIAL_FLYWEIGHT_RADIUS
        self.ramp_type = ramp_type

        # Initializing ramp
        if self.ramp_type == 1:
            length = inch_to_meter(1.125)
            curveLength = inch_to_meter(0.025)

            self.ramp = PiecewiseRamp()
            line = LinearSegment(x_start=0, x_end=inch_to_meter(0.125), slope=math.tan(math.radians(-25)))
            circle = CircularSegment(
                x_start=line.x_end + curveLength,
                x_end=length,
                radius=(inch_to_meter(5))**2,
                theta_start=0.971816735418,
                theta_end=1.1984521248,
            )
            cubicCircleLine = CubicSpiralZeroK1(
                x_start=line.x_end,
                x_end=line.x_end + curveLength,
                slope_start=line.slope(line.x_end),
                slope_end=circle.slope(circle.x_start),
                target_curvature=1/inch_to_meter(5),
            )
            self.ramp.add_segment(line)
            self.ramp.add_segment(cubicCircleLine)
            self.ramp.add_segment(circle)
        if self.ramp_type == 2:
            self.ramp = PiecewiseRamp()
            self.ramp.add_segment(
                LinearSegment(x_start=0, x_end=MAX_SHIFT / 6, slope=-0.8)
            )
            self.ramp.add_segment(
                CircularSegment(
                    x_start=MAX_SHIFT / 6,
                    x_end=MAX_SHIFT,
                    radius=0.2,
                    theta_start=1,
                    theta_end=np.pi / 2 - 0.55,
                )
            )
        elif self.ramp_type == 3:
            self.ramp = PiecewiseRamp()
            self.ramp.add_segment(
                LinearSegment(x_start=0, x_end=MAX_SHIFT / 6, slope=-0.5)
            )
            self.ramp.add_segment(
                CircularSegment(
                    x_start=MAX_SHIFT / 6,
                    x_end=MAX_SHIFT,
                    radius=0.01,
                    theta_start=0.9,
                    theta_end=np.pi / 2 - 0.3,
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
