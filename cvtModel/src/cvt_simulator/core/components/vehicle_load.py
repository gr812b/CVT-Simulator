import math
from cvt_simulator.constants.constants import GRAVITY, AIR_DENSITY
from cvt_simulator.constants.car_specs import (
    FRONTAL_AREA,
    DRAG_COEFFICIENT,
    WHEEL_RADIUS,
    GEARBOX_RATIO,
    ROLLING_RESISTANCE_COEFFICIENT,
)
from cvt_simulator.sim.system_state import SystemState
from cvt_simulator.utils.state_computations import (
    secondary_pulley_angular_velocity_to_car_velocity,
)
from cvt_simulator.geometry.theoretical_models import TheoreticalModels as tm
from cvt_simulator.core.data_types import ExternalLoadForceBreakdown


class LoadModel:
    # Velocity range for smooth rolling resistance transition [m/s]
    # Below min: no resistance (lets drivetrain accelerate freely)
    # Between min and max: smooth interpolation (avoids hard cutoff)
    # Above max: full rolling resistance
    ROLLING_RESISTANCE_MIN_VELOCITY = 0.001
    ROLLING_RESISTANCE_MAX_VELOCITY = 0.01

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
        velocity = secondary_pulley_angular_velocity_to_car_velocity(state.ω_s)

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
        Calculate rolling resistance force with smooth activation: -C_rr*m*g*cos(α)*smooth(|v|)*sgn(v)

        Smoothly ramps from 0 to full resistance over MIN to MAX velocity range.
        This avoids circular dependency at low speeds while preventing hard cutoffs.
        """
        rolling_force_magnitude = tm.rolling_resistance(
            self.rolling_resistance_coefficient,
            self.car_mass,
            self.g,
            self.incline_angle,
        )

        # Calculate smooth activation factor (0 to 1) based on absolute velocity
        abs_velocity = abs(velocity)

        if abs_velocity < self.ROLLING_RESISTANCE_MIN_VELOCITY:
            # Below min threshold: no resistance
            activation_factor = 0.0
        elif abs_velocity > self.ROLLING_RESISTANCE_MAX_VELOCITY:
            # Above max threshold: full resistance
            activation_factor = 1.0
        else:
            # Smooth interpolation between min and max (smoothstep)
            t = (abs_velocity - self.ROLLING_RESISTANCE_MIN_VELOCITY) / (
                self.ROLLING_RESISTANCE_MAX_VELOCITY
                - self.ROLLING_RESISTANCE_MIN_VELOCITY
            )
            # Smoothstep formula: 3t² - 2t³ (smooth cubic interpolation)
            activation_factor = 3 * t**2 - 2 * t**3

        # Apply activation factor and oppose motion direction
        return rolling_force_magnitude * activation_factor * tm.sgn(velocity)

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
