from typing import Callable


class EngineSimulator:
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

    def calculate_angular_acceleration(
        self, angular_velocity: float, load_torque: float
    ) -> float:
        """Calculate the angular acceleration based on the current angular velocity."""
        torque = self.get_torque(angular_velocity)
        angular_acceleration = (torque - load_torque) / self.inertia
        return angular_acceleration
