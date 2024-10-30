class SystemState:
    def __init__(self, angular_velocity=0.0, position=0.0):
        self.angular_velocity = angular_velocity
        self.position = position

    def to_array(self):
        """Converts the state to an array for solve_ivp."""
        return [self.angular_velocity, self.position]

    @staticmethod
    def from_array(array):
        """Creates a DrivetrainState from an array."""
        return SystemState(angular_velocity=array[0], position=array[1])
    
    @staticmethod
    def parse_solution(solution):
        """
        Parses the solution from solve_ivp into a list of DrivetrainState instances.
        
        Parameters:
        - solution: The solution object from solve_ivp.
        
        Returns:
        - A list of DrivetrainState instances representing each time step.
        """
        states = [SystemState.from_array(state) for state in solution.y.T]
        return states
