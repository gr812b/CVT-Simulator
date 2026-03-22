import math
from cvt_simulator.constants.constants import GRAVITY, AIR_DENSITY
from cvt_simulator.constants.car_specs import (
    FRONTAL_AREA,
    DRAG_COEFFICIENT,
    WHEEL_RADIUS,
    GEARBOX_RATIO,
    ROLLING_RESISTANCE_COEFFICIENT,
)
from cvt_simulator.utils.system_state import SystemState
from cvt_simulator.utils.state_computations import (
    secondary_pulley_angular_velocity_to_car_velocity,
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

    def get_breakdown(self, state: SystemState) -> ExternalLoadForceBreakdown:
        """
        Calculate equivalent road load as seen at the secondary pulley using:

        η_load(t) = (r_w/G) * [C_rr*m*g*cos(α)*sgn(v) + m*g*sin(α) + (1/2)*ρ*c_d*A_f*v²*sgn(v)]

        The velocity term v is derived from the state vector's secondary pulley
        angular velocity ω_s.
        """
        velocity = secondary_pulley_angular_velocity_to_car_velocity(
            state.secondary_pulley_angular_velocity
        )

        rolling_resistance_force = self._calculate_rolling_resistance_force(velocity)
        incline_force = self._calculate_incline_force()
        drag_force = self._calculate_drag_force(velocity)

        # Sum all road-load forces at the car contact patch.
        net_force_at_car = rolling_resistance_force + incline_force + drag_force

        # Convert each force component to equivalent torque at the secondary side.
        force_to_secondary_torque_scale = self.wheel_radius / self.gearbox_ratio
        rolling_resistance_torque_at_secondary = (
            force_to_secondary_torque_scale * rolling_resistance_force
        )
        incline_torque_at_secondary = force_to_secondary_torque_scale * incline_force
        drag_torque_at_secondary = force_to_secondary_torque_scale * drag_force
        net_torque_at_secondary = force_to_secondary_torque_scale * net_force_at_car

        return ExternalLoadForceBreakdown(
            rolling_resistance_force=rolling_resistance_force,
            incline_force=incline_force,
            drag_force=drag_force,
            net_force_at_car=net_force_at_car,
            rolling_resistance_torque_at_secondary=rolling_resistance_torque_at_secondary,
            incline_torque_at_secondary=incline_torque_at_secondary,
            drag_torque_at_secondary=drag_torque_at_secondary,
            net_torque_at_secondary=net_torque_at_secondary,
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
        return 0 #-rolling_force_magnitude * tm.sgn(velocity)

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
        return drag_magnitude * tm.sgn(velocity)

