import math
import numpy as np
from scipy.integrate import solve_ivp
import matplotlib.pyplot as plt
from utils.system_state import SystemState
from simulations.engine_simulation import EngineSimulator
from constants.engine_specs import torque_curve
from constants.car_specs import ENGINE_INTERTIA, GEAR_RATIO
from utils.conversions import rpm_to_rad_s, rad_s_to_rpm



engine_simulator = EngineSimulator(torque_curve=torque_curve, inertia=ENGINE_INTERTIA)


# Define the system of differential equations
def angular_velocity_and_position_derivative(t, y):
    state = SystemState.from_array(y)
    
    # Angular acceleration due to engine torque
    angular_acceleration = engine_simulator.calculate_angular_acceleration(state.angular_velocity)
    
    # Convert engine angular velocity to output angular velocity using the gear ratio for position calculation
    output_angular_velocity = state.angular_velocity / GEAR_RATIO
    
    # Return [d(ω))/dt, d(position)/dt]
    return [angular_acceleration, output_angular_velocity]

time_span = (0, 10)
time_eval = np.linspace(*time_span, 10000)
initial_state = SystemState(angular_velocity=rpm_to_rad_s(1800), position=0.0)

# Solve the system over the desired time span
solution = solve_ivp(
    angular_velocity_and_position_derivative, 
    time_span, 
    initial_state.to_array(),
    t_eval=time_eval
)

states = SystemState.parse_solution(solution)

rpms = [rad_s_to_rpm(state.angular_velocity) for state in states]
positions = [state.position for state in states]

plt.plot(solution.t, rpms, label="Engine RPM")
plt.plot(solution.t, positions, label="Output Position (radians)")
plt.xlabel("Time (s)")
plt.legend()
plt.title("Engine RPM and Output Position Over Time")
plt.grid()
plt.show()
