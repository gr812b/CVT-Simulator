import numpy as np
from scipy.integrate import solve_ivp
import matplotlib.pyplot as plt
from simulations.car_simulation import CarSimulator
from simulations.load_simulation import LoadSimulator
from utils.system_state import SystemState
from simulations.engine_simulation import EngineSimulator
from constants.engine_specs import torque_curve
from constants.car_specs import (
    ENGINE_INERTIA,
    GEARBOX_RATIO,
    FRONTAL_AREA,
    DRAG_COEFFICIENT,
    CAR_MASS,
    WHEEL_RADIUS,
)
from utils.conversions import rpm_to_rad_s, deg_to_rad


engine_simulator = EngineSimulator(torque_curve=torque_curve, inertia=ENGINE_INERTIA)
load_simulator = LoadSimulator(
    frontal_area=FRONTAL_AREA,
    drag_coefficient=DRAG_COEFFICIENT,
    car_mass=CAR_MASS,
    wheel_radius=WHEEL_RADIUS,
    gearbox_ratio=GEARBOX_RATIO,
    incline_angle=deg_to_rad(0),
)
car_simulator = CarSimulator(car_mass=CAR_MASS)

# Define the system of differential equations
def angular_velocity_and_position_derivative(t, y):
    state = SystemState.from_array(y)

    # Load from external forces
    gearbox_load = load_simulator.calculate_gearbox_load(state.car_velocity)

    # Engines angular acceleration due to engine torque
    engine_angular_acceleration = engine_simulator.calculate_angular_acceleration(
        state.engine_angular_velocity,
        gearbox_load,
    )

    # Net force on the car
    net_torque = (
        engine_simulator.get_torque(state.engine_angular_velocity) - gearbox_load
    )
    force_at_wheel = net_torque * GEARBOX_RATIO / WHEEL_RADIUS

    # Vehicle acceleration
    car_acceleration = car_simulator.calculate_acceleration(force_at_wheel)

    # Maximum car velocity at the current engine speed (Wheels can't spin faster than the engine + gearbox)
    max_car_velocity = state.engine_angular_velocity / GEARBOX_RATIO * WHEEL_RADIUS

    if state.car_velocity > max_car_velocity:
        car_acceleration = 0

    # TODO: Remove temporary solution to act as limiter for engine speed
    if state.engine_angular_velocity > 400:
        engine_angular_acceleration = 0

    return [engine_angular_acceleration, car_acceleration, state.car_velocity]


time_span = (0, 15)
time_eval = np.linspace(*time_span, 10000)
initial_state = SystemState(
    engine_angular_velocity=rpm_to_rad_s(2400), car_velocity=0.0, car_position=0.0
)

# Solve the system over the desired time span
solution = solve_ivp(
    angular_velocity_and_position_derivative,
    time_span,
    initial_state.to_array(),
    t_eval=time_eval,
)

states = SystemState.parse_solution(solution)

positions = [state.car_velocity for state in states]

plt.plot(solution.t, positions)
plt.xlabel("Time (s)")
plt.title("Car velocity Over Time")
plt.grid()
plt.show()
