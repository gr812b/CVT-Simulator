class SystemState:
    def __init__(
        self,
        engine_angular_velocity=0.0,
        engine_angular_position=0.0,
        car_velocity=0.0,
        car_position=0.0,
        shift_velocity=0.0,
        shift_distance=0.0,
    ):
        self.engine_angular_velocity = engine_angular_velocity
        self.engine_angular_position = engine_angular_position
        self.car_velocity = car_velocity
        self.car_position = car_position
        self.shift_velocity = shift_velocity
        self.shift_distance = shift_distance

    def to_array(self):
        """Converts the state to an array for solve_ivp."""
        return [
            self.engine_angular_velocity,
            self.engine_angular_position,
            self.car_velocity,
            self.car_position,
            self.shift_velocity,
            self.shift_distance,
        ]

    @staticmethod
    def from_array(array):
        """Creates a DrivetrainState from an array."""
        return SystemState(
            engine_angular_velocity=array[0],
            engine_angular_position=array[1],
            car_velocity=array[2],
            car_position=array[3],
            shift_velocity=array[4],
            shift_distance=array[5],
        )
