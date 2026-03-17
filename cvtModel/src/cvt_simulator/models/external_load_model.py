import math
from cvt_simulator.constants.constants import GRAVITY, AIR_DENSITY
from cvt_simulator.constants.car_specs import (
    FRONTAL_AREA,
    DRAG_COEFFICIENT,
    WHEEL_RADIUS,
    GEARBOX_RATIO,
    ROLLING_RESISTANCE_COEFFICIENT,
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
        self.rolling_resistance_coefficient = ROLLING_RESISTANCE_COEFFICIENT
        self.frontal_area = FRONTAL_AREA
        self.incline_angle = incline_angle
        # Gear reduction
        self.wheel_radius = WHEEL_RADIUS
        self.gearbox_ratio = GEARBOX_RATIO

    def get_breakdown(self, velocity: float) -> ExternalLoadForceBreakdown:
        """
        Calculate the total load force on the wheels using:
        η_load(t) = (r_w/G) * [C_rr*m*g*cos(α)*sgn(v) + m*g*sin(α) + (1/2)*ρ*c_d*A_f*v²*sgn(v)]
        """
        rolling_resistance_force = self._calculate_rolling_resistance_force(velocity)
        incline_force = self._calculate_incline_force()
        drag_force = self._calculate_drag_force(velocity)
        
        # Sum all forces (they act in different directions based on sign)
        total_force_inside_bracket = rolling_resistance_force + incline_force + drag_force
        
        # Apply the (r_w / G) scaling factor
        total_load_force = (self.wheel_radius / self.gearbox_ratio) * total_force_inside_bracket

        return ExternalLoadForceBreakdown(
            rolling_resistance_force=rolling_resistance_force,
            incline_force=incline_force,
            drag_force=drag_force,
            net=total_load_force,
        )

    def _calculate_rolling_resistance_force(self, velocity: float) -> float:
        """
        Calculate rolling resistance force: C_rr*m*g*cos(α)*sgn(v)
        Opposes motion, so direction determined by sign of velocity.
        """
        rolling_force_magnitude = tm.rolling_resistance(
            self.rolling_resistance_coefficient, self.car_mass, self.g, self.incline_angle
        )
        # Apply sign to ensure it opposes motion direction
        return -rolling_force_magnitude * tm.sgn(velocity)

    def _calculate_incline_force(self) -> float:
        """Calculate the incline force due to gravity: m*g*sin(α)"""
        return self.car_mass * self.g * math.sin(self.incline_angle)

    def _calculate_drag_force(self, velocity: float) -> float:
        """
        Calculate the aerodynamic drag force: (1/2)*ρ*c_d*A_f*v²*sgn(v)
        Opposes motion, so direction determined by sign of velocity.
        """
        # Calculate drag magnitude (always positive)
        drag_magnitude = tm.air_resistance(
            self.air_density, velocity, self.frontal_area, self.drag_coefficient
        )
        # Apply sign to ensure it opposes motion direction
        return -drag_magnitude * tm.sgn(velocity)

