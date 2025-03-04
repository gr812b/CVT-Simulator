import math
from constants.constants import GRAVITY, AIR_DENSITY
from utils.theoretical_models import TheoreticalModels as tm

# TODO: Consider direction, drag should never be applied in the opposite direction of velocity


class LoadSimulator:
    def __init__(
        self,
        car_mass: float,  # kg
        drag_coefficient: float,  # unitless
        frontal_area: float,  # m^2
        wheel_radius: float,  # m
        gearbox_ratio: float,  # unitless
        incline_angle: float,  # radians
    ):
        # Constants
        self.g = GRAVITY  # m/s^2
        self.air_density = AIR_DENSITY  # kg/m^3
        # Car specs
        self.car_mass = car_mass
        self.drag_coefficient = drag_coefficient
        self.frontal_area = frontal_area
        self.incline_angle = incline_angle
        # Gear reduction
        self.wheel_radius = wheel_radius
        self.gearbox_ratio = gearbox_ratio

    def calculate_incline_force(self) -> float:
        """Calculate the incline force due to gravity."""
        return self.car_mass * self.g * math.sin(self.incline_angle)

    def calculate_drag_force(self, velocity: float) -> float:
        """Calculate the drag force on the car."""
        drag_force = tm.air_resistance(
            self.air_density, velocity, self.frontal_area, self.drag_coefficient
        )

        if velocity < 0:
            drag_force *= -1

        return drag_force

    def calculate_total_load_force(self, velocity: float) -> float:
        """Calculate the total load torque on the wheels due to drag and incline."""
        incline_force = self.calculate_incline_force()
        drag_force = self.calculate_drag_force(velocity)
        total_load_force = incline_force + drag_force
        return total_load_force

    def calculate_gearbox_load(self, velocity: float) -> float:
        """Calculate the torque at the gearbox"""
        return (
            self.calculate_total_load_force(velocity)
            * self.wheel_radius
            / self.gearbox_ratio
        )
    
    def calculate_acceleration(self, velocity: float, power: float) -> float:
        """Calculate the acceleration of the car."""
        engine = power / (velocity * self.car_mass)
        air_resistance = self.calculate_drag_force(velocity)/self.car_mass
        gravity = self.g * math.sin(self.incline_angle)
        accel = engine - air_resistance - gravity
        return accel
