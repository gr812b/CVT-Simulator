from cvt_simulator.models.dataTypes import PrimaryPulleyDynamicsBreakdown
from cvt_simulator.components.engine import EngineModel
from cvt_simulator.core.system_state import SystemState
from cvt_simulator.constants.car_specs import ENGINE_INERTIA


class PrimaryPulleyModel:
    """Primary-pulley-side angular acceleration model."""

    def __init__(self, engine_model: EngineModel):
        self.engine_model = engine_model
        # I_p: primary-side rotational inertia used across coupled dynamics.
        self.inertia = ENGINE_INERTIA

    def get_breakdown(
        self, state: SystemState, coupling_torque: float
    ) -> PrimaryPulleyDynamicsBreakdown:

        # Primary pulley angular velocity is the engine speed
        primary_pulley_angular_velocity = state.ω_p
        primary_pulley_drive_torque = self.engine_model.get_torque(
            primary_pulley_angular_velocity
        )
        power = self.engine_model.get_power(primary_pulley_angular_velocity)

        # Torque balance at primary pulley: I * alpha = T_drive - T_coupling
        primary_pulley_angular_accel = (
            primary_pulley_drive_torque - coupling_torque
        ) / self.inertia

        return PrimaryPulleyDynamicsBreakdown(
            primary_pulley_drive_torque=primary_pulley_drive_torque,
            coupling_torque_at_primary_pulley=coupling_torque,
            power=power,
            primary_pulley_angular_velocity=primary_pulley_angular_velocity,
            primary_pulley_angular_acceleration=primary_pulley_angular_accel,
        )
