class SystemState:
    def __init__(self, engine_angular_velocity=0.0, car_velocity=0.0, car_position=0.0):
        self.engine_angular_velocity = engine_angular_velocity
        self.car_velocity = car_velocity
        self.car_position = car_position

    def to_array(self):
        """Converts the state to an array for solve_ivp."""
        return [self.engine_angular_velocity, self.car_velocity, self.car_position]

    @staticmethod
    def from_array(array):
        """Creates a DrivetrainState from an array."""
        return SystemState(
            engine_angular_velocity=array[0],
            car_velocity=array[1],
            car_position=array[2],
        )
