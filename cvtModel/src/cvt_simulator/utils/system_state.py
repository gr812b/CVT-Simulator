class SystemState:
    car_velocity: float
    car_position: float
    shift_velocity: float
    shift_distance: float

    def __init__(
        self,
        car_velocity=0.0,
        car_position=0.0,
        shift_velocity=0.0,
        shift_distance=0.0,
        engine_angular_velocity=0.0,
    ):
        self.car_velocity = car_velocity
        self.car_position = car_position
        self.shift_velocity = shift_velocity
        self.shift_distance = shift_distance
        self.engine_angular_velocity = engine_angular_velocity

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
