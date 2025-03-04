from constants.car_specs import (
    BELT_WIDTH,
    GEARBOX_RATIO,
    INNER_PRIMARY_PULLEY_RADIUS,
    INNER_SECONDARY_PULLEY_RADIUS,
    SHEAVE_ANGLE,
    WHEEL_RADIUS,
)
from utils.theoretical_models import TheoreticalModels as tm
from utils.system_state import SystemState


def update_y(y, state: SystemState):
    stateArray = state.to_array()
    for i in range(len(y)):
        y[i] = stateArray[i]


def shift_constraint_event(t, y):
    state = SystemState.from_array(y)
    MAX_SHIFT = BELT_WIDTH
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

    cvt_ratio = tm.current_cvt_ratio(
        state.shift_distance,
        SHEAVE_ANGLE,
        BELT_WIDTH,
        INNER_PRIMARY_PULLEY_RADIUS,
        INNER_SECONDARY_PULLEY_RADIUS,
    )

    max_car_velocity = (
        (state.engine_angular_velocity / cvt_ratio) / GEARBOX_RATIO * WHEEL_RADIUS
    )

    if abs(state.car_velocity) > max_car_velocity:
        state.car_velocity = max_car_velocity

    update_y(y, state)
    return 1


def engine_angular_velocity_constraint_event(t, y):
    state = SystemState.from_array(y)
    MAX_ENGINE_ANGULAR_VELOCITY = 400

    if state.engine_angular_velocity < 0:
        state.engine_angular_velocity = 0
    elif state.engine_angular_velocity > MAX_ENGINE_ANGULAR_VELOCITY:
        state.engine_angular_velocity = MAX_ENGINE_ANGULAR_VELOCITY

    update_y(y, state)
    return 1


# Export all constraints
constraints = [
    shift_constraint_event,
]
