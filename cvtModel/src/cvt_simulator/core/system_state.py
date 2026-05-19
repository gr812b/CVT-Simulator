from dataclasses import dataclass
from cvt_simulator.constants.car_specs import MAX_SHIFT


@dataclass
class SystemState:
    """
    State vector for CVT simulator with 5 degrees of freedom (ODE formulation).

    Contains only the true degrees of freedom evolved by the ODE solver:
    - shift_distance: s [m] - axial position of sheaves (0 to MAX_SHIFT)
    - shift_velocity: ṡ [m/s] - rate of sheave axial movement
    - primary_pulley_angular_velocity: ω_P [rad/s] - primary pulley angular velocity
    - secondary_pulley_angular_velocity: ω_s [rad/s] - secondary pulley angular velocity
    - belt velocity: v_b [m/s] - belt linear transport speed

    All other quantities (car_velocity, engine_angular_velocity, positions, etc.)
    are derived from these DOF and should be computed using StateComputations utility.
    """

    s: float = 0.0
    s_dot: float = 0.0
    ω_p: float = 0.0
    ω_s: float = 0.0
    v_b: float = 0.0

    def to_array(self):
        """Converts the state to an array for solve_ivp."""
        return [
            self.s,
            self.s_dot,
            self.ω_p,
            self.ω_s,
            self.v_b,
        ]

    @staticmethod
    def from_array(array):
        """Creates a SystemState from an array."""
        s = float(array[0])
        # Clamp numerical drift so downstream geometry always sees a valid shift domain.
        if s < 0.0:
            s = 0.0
        elif s > MAX_SHIFT:
            s = float(MAX_SHIFT)

        v_b = float(array[4]) if len(array) > 4 else 0.0

        return SystemState(
            s=s,
            s_dot=array[1],
            ω_p=array[2],
            ω_s=array[3],
            v_b=v_b,
        )
