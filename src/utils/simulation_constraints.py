from constants.car_specs import (
    MAX_SHIFT,
)
from utils.theoretical_models import TheoreticalModels as tm
from utils.system_state import SystemState
import numpy as np


def logistic_clamp(x, lower_bound, upper_bound, slope=5000.0):
    """
    Returns a factor in [0..1] that is ~1 for x in (lower_bound, upper_bound)
    and smoothly transitions to 0 when x is outside [lower_bound, upper_bound].
    The 'slope' controls how sharp the transition is.
    """
    # Transition near the lower bound
    factor_low = 1.0 / (1.0 + np.exp(-slope * (x - lower_bound)))
    # Transition near the upper bound
    factor_up = 1.0 / (1.0 + np.exp(slope * (x - upper_bound)))
    return factor_low * factor_up


def update_y(y, state: SystemState):
    stateArray = state.to_array()
    for i in range(len(y)):
        y[i] = stateArray[i]


def shift_constraint_event(t, y):
    state = SystemState.from_array(y)
    shift_velocity = state.shift_velocity
    shift_distance = state.shift_distance

    if shift_distance < 0:
        state.shift_distance = 0
        state.shift_velocity = max(0, shift_velocity)

    elif shift_distance > MAX_SHIFT:
        state.shift_distance = MAX_SHIFT
        state.shift_velocity = min(0, shift_velocity)

    update_y(y, state)
    return 1

def car_velocity_constraint_event(t, y):
    state = SystemState.from_array(y)
    return state.car_velocity

def shift_velocity_constraint_event(t, y):
    state = SystemState.from_array(y)
    MAX_SHIFT_VELOCITY = 0.01

    if state.shift_velocity > MAX_SHIFT_VELOCITY:
        state.shift_velocity = MAX_SHIFT_VELOCITY
    elif state.shift_velocity < -MAX_SHIFT_VELOCITY:
        state.shift_velocity = -MAX_SHIFT_VELOCITY

    update_y(y, state)
    return 1

car_velocity_constraint_event.terminal = True
car_velocity_constraint_event.direction = -1


# Export all constraints
constraints = [
    shift_constraint_event,
    car_velocity_constraint_event,
    # shift_velocity_constraint_event,
]
