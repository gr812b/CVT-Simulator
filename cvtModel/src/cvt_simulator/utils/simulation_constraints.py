from cvt_simulator.constants.car_specs import (
    MAX_SHIFT,
)
from cvt_simulator.models.system_model import SystemModel
from cvt_simulator.utils.system_state import SystemState
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


car_velocity_constraint_event.terminal = True
car_velocity_constraint_event.direction = -1


def get_shift_steady_event(system_model: SystemModel):
    """
    Returns an event function that triggers only when:
      1. The system is close enough to full shift (i.e. shift_distance within tol of MAX_SHIFT).
      2. The desired shift acceleration (as computed by shift_simulator)
         transitions from negative to positive (i.e. it wants to push further).
    """

    def shift_steady_event(t, y):
        state = SystemState.from_array(y)
        tol = 1e-5  # Tolerance for proximity to MAX_SHIFT

        # Before we get near full shift, return a fixed negative value.
        if state.shift_distance < MAX_SHIFT - tol:
            return -tol

        # Clamp here as clamping from other events doesn't propagate immediately
        shift_velocity = state.shift_velocity
        shift_distance = state.shift_distance
        if shift_distance < 0:
            state.shift_distance = 0
            state.shift_velocity = max(0, shift_velocity)

        elif shift_distance > MAX_SHIFT:
            state.shift_distance = MAX_SHIFT
            state.shift_velocity = min(0, shift_velocity)

        update_y(y, state)

        # Once near full shift, return the computed shift acceleration.
        # The event will trigger when this value crosses from negative to positive.
        # TODO: Clean this up!
        coupling_torque = system_model.slip_model.get_breakdown(state).coupling_torque
        return system_model.cvt_shift_model.get_breakdown(
            state, coupling_torque
        ).acceleration

    shift_steady_event.terminal = True
    shift_steady_event.direction = 1  # Looking for a negative-to-positive crossing.
    return shift_steady_event


def get_back_shift_event(system_model: SystemModel):
    """
    Returns an event function that triggers when the system wants to back-shift
    from full shift position. This detects when the shift acceleration becomes
    sufficiently negative while at MAX_SHIFT.
    """

    def back_shift_event(t, y):
        state = SystemState.from_array(y)
        
        # Should only trigger when at full shift
        if state.shift_distance < MAX_SHIFT - 1e-5:
            return 1.0  # Return positive value when not at full shift
        
        # Calculate the shift acceleration
        coupling_torque = system_model.slip_model.get_breakdown(state).coupling_torque
        shift_accel = system_model.cvt_shift_model.get_breakdown(
            state, coupling_torque
        ).acceleration
        
        # Return the acceleration + small threshold
        # Event triggers when this crosses from positive to negative
        # (i.e., when acceleration becomes sufficiently negative)
        return shift_accel + 5.0  # 5 N threshold to avoid numerical noise

    back_shift_event.terminal = True
    back_shift_event.direction = -1  # Looking for a positive-to-negative crossing
    return back_shift_event


# Export all constraints
constraints = [
    shift_constraint_event,
    car_velocity_constraint_event,
]
