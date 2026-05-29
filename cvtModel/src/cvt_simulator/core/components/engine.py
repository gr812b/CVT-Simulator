from typing import Callable
from cvt_simulator.core.data_types import EngineTorqueBreakdown


class EngineModel:
    """Pure engine model handling torque curve and power calculations."""

    def __init__(
        self,
        torque_curve: Callable[[float], float],  # rad/s -> Nm
    ):
        self.torque_curve = torque_curve

    def get_torque(self, ω: float) -> float:
        """Get the torque output at a given angular velocity."""
        return self.torque_curve(ω)

    def get_breakdown(self, ω: float) -> EngineTorqueBreakdown:
        """Return a minimal engine breakdown (torque + power)."""
        torque = self.get_torque(ω)
        power = self.get_power(ω)
        return EngineTorqueBreakdown(
            engine_torque=torque, engine_speed=ω, engine_power=power
        )

    def get_power(self, ω: float) -> float:
        """Get the power output at a given angular velocity."""
        return self.get_torque(ω) * ω
