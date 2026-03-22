from cvt_simulator.constants.car_specs import (
    MAX_SHIFT,
)
from cvt_simulator.models.system_model import SystemModel
from cvt_simulator.utils.state_computations import (
    secondary_pulley_angular_velocity_to_car_velocity,
)
from cvt_simulator.utils.system_state import SystemState

MIN_CAR_VELOCITY_MPS = -20.0


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
    return (
        secondary_pulley_angular_velocity_to_car_velocity(
            state.secondary_pulley_angular_velocity
        )
        - MIN_CAR_VELOCITY_MPS
    )


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


def get_mid_shift_steady_event(
    system_model: SystemModel,
    velocity_tol: float = 1e-4,
    accel_tol: float = 0.1,
    wake_accel_guard_tol: float = 0.5,
    boundary_margin: float = 1e-5,
):
    """
    Trigger when the system is quasi-static in the shift DOF away from hard limits.

    Conditions to enter steady mode:
      1. Shift distance is not clamped against hard bounds.
            2. |shift_velocity| <= velocity_tol.
            3. |shift_accel| <= accel_tol.
            4. If shift were locked now (shift_velocity=0), the resulting
                 |shift_accel| must also be <= wake_accel_guard_tol.

    This is used to enter a locked mid-shift mode to avoid costly dithering.
    """

    def mid_shift_steady_event(t, y):
        state = SystemState.from_array(y)

        # Only apply in the interior region, not near hard shift boundaries.
        if (
            state.shift_distance <= boundary_margin
            or state.shift_distance >= MAX_SHIFT - boundary_margin
        ):
            return 1.0

        coupling_torque = system_model.slip_model.get_breakdown(state).coupling_torque
        shift_accel = system_model.cvt_shift_model.get_breakdown(
            state, coupling_torque
        ).acceleration

        # Guard against immediate wake chatter: only lock if the locked-state
        # acceleration would also remain below the wake threshold.
        locked_state = SystemState(
            shift_distance=state.shift_distance,
            shift_velocity=0.0,
            primary_pulley_angular_velocity=state.primary_pulley_angular_velocity,
            secondary_pulley_angular_velocity=state.secondary_pulley_angular_velocity,
        )
        locked_coupling_torque = system_model.slip_model.get_breakdown(
            locked_state
        ).coupling_torque
        locked_shift_accel = system_model.cvt_shift_model.get_breakdown(
            locked_state, locked_coupling_torque
        ).acceleration

        # Deterministic event value: <= 0 means quasi-static and eligible to lock.
        return max(
            abs(state.shift_velocity) - velocity_tol,
            abs(shift_accel) - accel_tol,
            abs(locked_shift_accel) - wake_accel_guard_tol,
        )

    mid_shift_steady_event.terminal = True
    mid_shift_steady_event.direction = (
        -1
    )  # enter steady mode when value drops below zero
    return mid_shift_steady_event


def get_mid_shift_wake_event(
    system_model: SystemModel,
    wake_accel_tol: float = 1.5,
    boundary_margin: float = 1e-5,
):
    """
    Trigger when locked mid-shift mode should resume normal shift dynamics.

        Event value is negative while near equilibrium and becomes positive when
        acceleration indicates the locked shift should move again.

        Direction logic:
            - Near lower bound: only positive acceleration can move the shift, so wake on
                shift_accel - wake_accel_tol.
            - Near upper bound: only negative acceleration can move the shift, so wake on
                -shift_accel - wake_accel_tol.
            - Interior: wake on |shift_accel| - wake_accel_tol.
    """

    def mid_shift_wake_event(t, y):
        state = SystemState.from_array(y)
        coupling_torque = system_model.slip_model.get_breakdown(state).coupling_torque
        shift_accel = system_model.cvt_shift_model.get_breakdown(
            state, coupling_torque
        ).acceleration
        if state.shift_distance <= boundary_margin:
            return shift_accel - wake_accel_tol
        if state.shift_distance >= MAX_SHIFT - boundary_margin:
            return -shift_accel - wake_accel_tol
        return abs(shift_accel) - wake_accel_tol

    mid_shift_wake_event.terminal = True
    mid_shift_wake_event.direction = 1  # wake when value rises through zero
    return mid_shift_wake_event


# Export all constraints
constraints = [
    shift_constraint_event,
    car_velocity_constraint_event,
]
