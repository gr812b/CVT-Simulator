from typing import Callable

class EngineModel:
    """Pure engine model handling torque curve and power calculations."""
    
    def __init__(
        self,
        torque_curve: Callable[[float], float],  # rad/s -> Nm
    ):
        self.torque_curve = torque_curve

    def get_torque(self, angular_velocity: float) -> float:
        """Get the torque output at a given angular velocity."""
        return self.torque_curve(angular_velocity)

    def get_power(self, angular_velocity: float) -> float:
        """Get the power output at a given angular velocity."""
        return self.get_torque(angular_velocity) * angular_velocity
