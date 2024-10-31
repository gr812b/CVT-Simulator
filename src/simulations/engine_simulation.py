class EngineSimulator:
    def __init__(self, torque_curve, inertia):
        """
        Initialize the engine simulator.

        Parameters:
        - torque_curve: A function or interpolation of torque vs. angular velocity.
        - inertia: Inertia of the engine (kg*m^2).
        """
        self.torque_curve = torque_curve
        self.inertia = inertia

    def get_torque(self, angular_velocity):
        """
        Get the torque output at a given angular velocity.

        Parameters:
        - angular_velocity: Engine angular velocity.

        Returns:
        - Torque at the specified angular velocity in Nm.
        """
        return self.torque_curve(angular_velocity)

    def calculate_angular_acceleration(self, angular_velocity, load_torque):
        """
        Calculate the angular acceleration based on the current angular velocity.

        Parameters:
        - angular_velocity: Current angular velocity of the engine in rad/s.
        - load_torque: Load torque on the engine in Nm.

        Returns:
        - Angular acceleration in rad/s^2.
        """
        torque = self.get_torque(angular_velocity)
        angular_acceleration = (torque - load_torque) / self.inertia
        return angular_acceleration
