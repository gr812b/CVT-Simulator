from cvt_simulator.core.system_state import SystemState
from cvt_simulator.models.dataTypes import SecondaryPulleyDynamicsBreakdown
from cvt_simulator.components.vehicle_load import LoadModel
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm
from cvt_simulator.constants.car_specs import (
    GEARBOX_RATIO,
    WHEEL_RADIUS,
    SECONDARY_INERTIA,
    GEARBOX_INERTIA,
    WHEEL_INERTIA,
)


class SecondaryPulleyModel:
    """Secondary-pulley-side angular acceleration model."""

    def __init__(
        self,
        car_mass: float,
        load_model: LoadModel,
    ):
        self.car_mass = car_mass
        self.load_model = load_model
        # I_s: secondary-side equivalent rotational inertia used across coupled dynamics.
        self.inertia = self._calculate_total_inertia()

    def get_breakdown(
        self, state: SystemState, coupling_torque: float
    ) -> SecondaryPulleyDynamicsBreakdown:
        external_forces = self.load_model.get_breakdown(state)

        primary_to_secondary_ratio = (
            tm.current_effective_cvt_ratio(state.s) * GEARBOX_RATIO
        )

        # Linear acceleration at the vehicle from torque balance at the secondary side.
        linear_accel = (
            WHEEL_RADIUS
            * (
                coupling_torque * primary_to_secondary_ratio
                - external_forces.net_torque_at_secondary
            )
            / self.inertia
        )

        return SecondaryPulleyDynamicsBreakdown(
            coupling_torque_at_secondary_pulley=(
                coupling_torque * primary_to_secondary_ratio
            ),
            external_load_torque_at_secondary_pulley=(
                external_forces.net_torque_at_secondary
            ),
            external_forces=external_forces,
            secondary_pulley_angular_acceleration=linear_accel / WHEEL_RADIUS,
        )

    def _calculate_total_inertia(self) -> float:
        """
        Calculate total system inertia using: I_s = I_sec + I_gb + (I_wheel + m*r_w^2) / G^2

        Returns:
            Total inertia in kg*m^2
        """
        wheel_and_car_inertia = WHEEL_INERTIA + self.car_mass * WHEEL_RADIUS**2
        return (
            SECONDARY_INERTIA
            + GEARBOX_INERTIA
            + wheel_and_car_inertia / (GEARBOX_RATIO**2)
        )
