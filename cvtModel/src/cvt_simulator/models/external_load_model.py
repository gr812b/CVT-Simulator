import math
from cvt_simulator.constants.constants import GRAVITY, AIR_DENSITY
from cvt_simulator.constants.car_specs import (
    FRONTAL_AREA,
    DRAG_COEFFICIENT,
    WHEEL_RADIUS,
    GEARBOX_RATIO,
)
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm
from cvt_simulator.models.dataTypes import ExternalLoadForceBreakdown


class LoadModel:
    def __init__(
        self,
        car_mass: float,  # kg
        incline_angle: float,  # radians
    ):
        # Constants
        self.g = GRAVITY  # m/s^2
        self.air_density = AIR_DENSITY  # kg/m^3
        # Car specs
        self.car_mass = car_mass
        self.drag_coefficient = DRAG_COEFFICIENT
        self.frontal_area = FRONTAL_AREA
        self.incline_angle = incline_angle
        # Gear reduction
        self.wheel_radius = WHEEL_RADIUS
        self.gearbox_ratio = GEARBOX_RATIO

    def get_breakdown(self, velocity: float) -> ExternalLoadForceBreakdown:
        """Calculate the total load torque on the wheels due to drag and incline."""
        incline_force = self._calculate_incline_force()
        drag_force = self._calculate_drag_force(velocity)
        total_load_force = incline_force + drag_force

        return ExternalLoadForceBreakdown(
            incline_force=incline_force, drag_force=drag_force, net=total_load_force
        )

    def _calculate_incline_force(self) -> float:
        """Calculate the incline force due to gravity."""
        return self.car_mass * self.g * math.sin(self.incline_angle)

    def _calculate_drag_force(self, velocity: float) -> float:
        """Calculate the drag force on the car."""
        drag_force = tm.air_resistance(
            self.air_density, velocity, self.frontal_area, self.drag_coefficient
        )

        if velocity < 0:
            drag_force *= -1

        return drag_force

    # TODO: Why does this exist
    def calculate_gearbox_load(self, velocity: float) -> float:
        """Calculate the torque at the gearbox"""
        return (
            self.calculate_total_load_force(velocity)
            * self.wheel_radius
            / self.gearbox_ratio
        )
