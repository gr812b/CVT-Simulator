from dataclasses import dataclass


@dataclass
class SystemState:
    """
    State vector for CVT simulator with 4 degrees of freedom (ODE formulation).
    
    Contains only the 4 true degrees of freedom evolved by the ODE solver:
    - shift_distance: s [m] - axial position of sheaves (0 to MAX_SHIFT)
    - shift_velocity: ṡ [m/s] - rate of sheave axial movement
    - primary_pulley_angular_velocity: ω_P [rad/s] - primary pulley angular velocity
    - secondary_pulley_angular_velocity: ω_s [rad/s] - secondary pulley angular velocity
    
    All other quantities (car_velocity, engine_angular_velocity, positions, etc.)
    are derived from these 4 DOF and should be computed using StateComputations utility.
    """
    shift_distance: float = 0.0
    shift_velocity: float = 0.0
    primary_pulley_angular_velocity: float = 0.0
    secondary_pulley_angular_velocity: float = 0.0

    def to_array(self):
        """Converts the state to an array for solve_ivp (4 DOF only)."""
        return [
            self.shift_distance,
            self.shift_velocity,
            self.primary_pulley_angular_velocity,
            self.secondary_pulley_angular_velocity,
        ]

    @staticmethod
    def from_array(array):
        """Creates a SystemState from an array (4 DOF)."""
        return SystemState(
            shift_distance=array[0],
            shift_velocity=array[1],
            primary_pulley_angular_velocity=array[2],
            secondary_pulley_angular_velocity=array[3],
        )
