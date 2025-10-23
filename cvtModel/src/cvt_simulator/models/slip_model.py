import math
import numpy as np
from cvt_simulator.models.dataTypes import SlipBreakdown, CvtSystemForceBreakdown
from cvt_simulator.models.external_load_model import LoadModel
from cvt_simulator.models.engine_model import EngineModel
from cvt_simulator.utils.system_state import SystemState
from cvt_simulator.constants.car_specs import (
    WHEEL_RADIUS,
    GEARBOX_RATIO,
    ENGINE_INERTIA,
    DRIVELINE_INERTIA,
)
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm
from cvt_simulator.constants.constants import (
    RUBBER_ALUMINUM_STATIC_FRICTION,
)

class SlipModel:
    def __init__(
        self, load_model: LoadModel, engine_model: EngineModel, car_mass: float
    ):
        self.load_model = load_model
        self.engine_model = engine_model
        self.car_mass = car_mass
        self.μ = RUBBER_ALUMINUM_STATIC_FRICTION # TODO: Look into V-belt groove friction enhancement

    def get_breakdown(self, state: SystemState, cvt_breakdown: CvtSystemForceBreakdown) -> SlipBreakdown:
        t_max = self.calculate_t_max(cvt_breakdown)
        t_c = self.get_tc(state, t_max)
        cvt_ratio_derivative = tm.current_cvt_ratio_rate_of_change(
            state.shift_distance, state.shift_velocity
        )

        return SlipBreakdown(
            t_c=t_c,
            cvt_ratio_derivative=cvt_ratio_derivative,
            t_max=t_max,
        )

    def get_tc(self, state: SystemState, t_max: float):       
        wheel_inertia = DRIVELINE_INERTIA + self.car_mass * (
            WHEEL_RADIUS**2
        )  # This is the driveline + car's translational mass at wheels

        engine_torque = self.engine_model.get_torque(state.engine_angular_velocity)
        load_force = self.load_model.get_breakdown(state.car_velocity).net
        load_torque = load_force * WHEEL_RADIUS
        wheel_angular_velocity = self.get_wheel_speed(state.car_velocity)
        engine_to_wheel_ratio = (
            tm.current_cvt_ratio(state.shift_distance) * GEARBOX_RATIO
        )
        engine_to_wheel_ratio_rate_of_change = (
            tm.current_cvt_ratio_rate_of_change(
                state.shift_distance, state.shift_velocity
            )
            * GEARBOX_RATIO
        )

        # The secret butter
        eng_term = engine_torque * wheel_inertia
        load_term = ENGINE_INERTIA * load_torque * engine_to_wheel_ratio
        shift_term = (
            ENGINE_INERTIA
            * wheel_inertia
            * wheel_angular_velocity
            * engine_to_wheel_ratio_rate_of_change
        )

        numerator = eng_term + load_term - shift_term
        denominator = wheel_inertia + ENGINE_INERTIA * engine_to_wheel_ratio**2

        t_c = numerator / denominator
        t_max = 10000
        t_c = max(-t_max, min(t_max, t_c))  # Apply coulomb slip law with calculated T_MAX

        return t_c

    def get_wheel_speed(self, car_velocity: float):
        return car_velocity / WHEEL_RADIUS

    def calculate_t_max(self, cvt_breakdown: CvtSystemForceBreakdown) -> float:
        """
        Calculate maximum transferable torque using CVT breakdown data.
        
        Uses the more restrictive (smaller) T_MAX from either primary or secondary pulley.
        This ensures we don't exceed the slip limit of either pulley.
        """
        # Extract data from primary pulley breakdown
        primary_radial_force = cvt_breakdown.primaryRadialForce.net
        primary_wrap_angle = cvt_breakdown.primaryRadialForce.wrap_angle
        primary_radius = cvt_breakdown.primaryRadialForce.radius
        
        # Extract data from secondary pulley breakdown
        secondary_radial_force = cvt_breakdown.secondaryRadialForce.net
        secondary_wrap_angle = cvt_breakdown.secondaryRadialForce.wrap_angle
        secondary_radius = cvt_breakdown.secondaryRadialForce.radius
        
        # Calculate slack tension for both pulleys
        primary_t_max = self._get_max_torque(
            primary_radial_force, primary_wrap_angle, primary_radius, self.μ
        )
        secondary_t_max = self._get_max_torque(
            secondary_radial_force, secondary_wrap_angle, secondary_radius, self.μ
        )
        
        # Use the more restrictive (smaller) T_MAX
        return max(min(primary_t_max, secondary_t_max), 0)

    def _get_max_torque(self, radial_force: float, wrap_angle: float, radius: float, μ: float):
        capstan_term = math.exp(μ * wrap_angle) - 1 / (np.exp(μ * wrap_angle) + 1)
        radial_force_term = radial_force * radius / np.sin(wrap_angle / 2)
        return capstan_term * radial_force_term
