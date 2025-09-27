from typing import Callable

from cvt_simulator.models.dataTypes import EngineForceBreakdown


class EngineModel:
    def __init__(
        self,
        torque_curve: Callable[[float], float],  # rad/s -> Nm
        inertia: float,  # kg*m^2
    ):
        self.torque_curve = torque_curve
        self.inertia = inertia

    def get_torque(self, angular_velocity: float) -> float:
        """Get the torque output at a given angular velocity."""
        return self.torque_curve(angular_velocity)

    def get_power(self, angular_velocity: float) -> float:
        """Get the power output at a given angular velocity."""
        return self.get_torque(angular_velocity) * angular_velocity

    def get_breakdown(self, angular_velocity: float) -> EngineForceBreakdown:
        torque = self.get_torque(angular_velocity)
        power = self.get_power(angular_velocity)
        return EngineForceBreakdown(
            torque,
            power,
            angular_velocity,
        )
