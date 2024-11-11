import pandas as pd

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

    @staticmethod
    def parse_solution(solution):
        """Parses the solution from solve_ivp into a list of DrivetrainState instances."""
        states = [SystemState.from_array(state) for state in solution.y.T]
        return states
    
    @staticmethod
    def write_csv(solution, filename="simulation_output.csv"):
        """Parses the solution and writes it to a CSV file."""
        # Parse the solution into SystemState instances
        states = SystemState.parse_solution(solution)
        
        # Prepare data for CSV
        data = {
            "time": solution.t,
            "engine_angular_velocity": [state.engine_angular_velocity for state in states],
            "car_velocity": [state.car_velocity for state in states],
            "car_position": [state.car_position for state in states],
        }
        
        # Create DataFrame and write to CSV
        df = pd.DataFrame(data)
        df.to_csv(filename, index=False)
