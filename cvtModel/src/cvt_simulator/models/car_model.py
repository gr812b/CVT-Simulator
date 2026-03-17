from cvt_simulator.utils.system_state import SystemState
from cvt_simulator.models.dataTypes import CarForceBreakdown
from cvt_simulator.models.external_load_model import LoadModel
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm
from cvt_simulator.constants.car_specs import (
    GEARBOX_RATIO,
    WHEEL_RADIUS,
    SECONDARY_INERTIA,
    GEARBOX_INERTIA,
    WHEEL_INERTIA,
)


class CarModel:
    def __init__(
        self,
        car_mass: float,
        load_model: LoadModel,
    ):
        self.car_mass = car_mass
        self.load_model = load_model

    def _calculate_total_inertia(self) -> float:
        """
        Calculate total system inertia using: I_s = I_sec + I_gb + (I_wheel + m*r_w^2) / G^2
        
        Returns:
            Total inertia in kg*m^2
        """
        wheel_and_car_inertia = WHEEL_INERTIA + self.car_mass * WHEEL_RADIUS**2
        return SECONDARY_INERTIA + GEARBOX_INERTIA + wheel_and_car_inertia / (GEARBOX_RATIO**2)

    def get_breakdown(
        self, state: SystemState, coupling_torque: float
    ) -> CarForceBreakdown:
        load_force = self.load_model.get_breakdown(state.car_velocity).net
        load_torque = load_force * WHEEL_RADIUS

        engine_to_wheel_ratio = (
            tm.current_effective_cvt_ratio(state.shift_distance) * GEARBOX_RATIO
        )
        total_inertia = self._calculate_total_inertia()
        accel = (
            WHEEL_RADIUS
            * (coupling_torque * engine_to_wheel_ratio - load_torque)
            / total_inertia
        )

        return CarForceBreakdown(
            coupling_torque_at_wheel=coupling_torque * engine_to_wheel_ratio, # TODO: Question this
            load_torque_at_wheel=load_torque,
            external_forces=self.load_model.get_breakdown(state.car_velocity),
            acceleration=accel,
        )
