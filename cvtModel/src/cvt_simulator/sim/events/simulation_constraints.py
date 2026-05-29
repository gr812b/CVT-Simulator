from cvt_simulator.constants.car_specs import (
    MAX_SHIFT,
)

from cvt_simulator.utils.state_computations import (
    secondary_pulley_angular_velocity_to_car_velocity,
)
from cvt_simulator.sim.system_state import SystemState

MIN_CAR_VELOCITY_MPS = -20.0


def update_y(y, state: SystemState):
    stateArray = state.to_array()
    for i in range(len(y)):
        y[i] = stateArray[i]


def shift_constraint_event(t, y):
    state = SystemState.from_array(y)
    shift_velocity = state.s_dot
    shift_distance = state.s

    if shift_distance < 0:
        state.s = 0
        state.s_dot = max(0, shift_velocity)

    elif shift_distance > MAX_SHIFT:
        state.s = MAX_SHIFT
        state.s_dot = min(0, shift_velocity)

    update_y(y, state)
    return 1


def car_velocity_constraint_event(t, y):
    state = SystemState.from_array(y)
    return (
        secondary_pulley_angular_velocity_to_car_velocity(
            state.ω_s
        )
        - MIN_CAR_VELOCITY_MPS
    )


car_velocity_constraint_event.terminal = True
car_velocity_constraint_event.direction = -1

# Export all constraints
constraints = [
    shift_constraint_event,
    car_velocity_constraint_event,
]
