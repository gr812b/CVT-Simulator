from utils.system_state import SystemState
from utils.theoretical_models import TheoreticalModels as tm
from utils.system_state import SystemState
from simulations.engine_simulation import EngineSimulator
from simulations.primary_pulley import PrimaryPulley
from simulations.secondary_pulley import SecondaryPulley
from simulations.belt_simulator import BeltSimulator

def get_pulley_forces(
    state: SystemState,
    engine_simulator: EngineSimulator,
    primary_simulator: PrimaryPulley,
    secondary_simulator: SecondaryPulley,
    primary_belt: BeltSimulator,
    secondary_belt: BeltSimulator,
):
    # Compute CVT ratio and engine velocity
    cvt_ratio = tm.current_cvt_ratio(state.shift_distance)
    wheel_to_engine_ratio = (cvt_ratio * primary_simulator.GEARBOX_RATIO) / primary_simulator.WHEEL_RADIUS  # or import these constants
    engine_velocity = state.car_velocity * wheel_to_engine_ratio

    # Engine torque for secondary force calculation
    engine_torque = engine_simulator.get_torque(engine_velocity)

    # Calculate forces using the provided simulators
    primary_force = primary_simulator.calculate_net_force(
        state.shift_distance, engine_velocity
    )
    secondary_force = secondary_simulator.calculate_net_force(
        engine_torque * cvt_ratio, state.shift_distance
    )

    # Calculate wrap angles and convert to radial forces
    primary_wrap_angle = tm.primary_wrap_angle(state.shift_distance)
    secondary_wrap_angle = tm.secondary_wrap_angle(state.shift_distance)
    primary_radial = primary_belt.calculate_radial_force(
        engine_velocity, state.shift_distance, primary_wrap_angle, primary_force
    )
    secondary_radial = secondary_belt.calculate_radial_force(
        engine_velocity, state.shift_distance, secondary_wrap_angle, secondary_force
    )

    return {
        "primary_force": primary_force,
        "secondary_force": secondary_force,
        "primary_radial": primary_radial,
        "secondary_radial": secondary_radial,
    }
