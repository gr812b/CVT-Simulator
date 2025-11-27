from dataclasses import dataclass


@dataclass
class SystemState:
    car_velocity: float = 0.0
    car_position: float = 0.0
    shift_velocity: float = 0.0
    shift_distance: float = 0.0
    engine_angular_velocity: float = 0.0

    def to_array(self):
        """Converts the state to an array for solve_ivp."""
        return [
            self.car_velocity,
            self.car_position,
            self.shift_velocity,
            self.shift_distance,
            self.engine_angular_velocity,
        ]

    @staticmethod
    def from_array(array):
        """Creates a DrivetrainState from an array."""
        return SystemState(
            car_velocity=array[0],
            car_position=array[1],
            shift_velocity=array[2],
            shift_distance=array[3],
            engine_angular_velocity=array[4],
        )
