from utils.system_state import SystemState
from utils.theoretical_models import TheoreticalModels as tm
from simulations.engine_simulation import EngineSimulator
from simulations.primary_pulley import PrimaryPulley
from simulations.secondary_pulley import SecondaryPulley
from simulations.belt_simulator import BeltSimulator
from constants.car_specs import GEARBOX_RATIO, WHEEL_RADIUS


class CvtShift:
    def __init__(
        self,
        engine_simulator: EngineSimulator,
        primary_simulator: PrimaryPulley,
        secondary_simulator: SecondaryPulley,
        primary_belt: BeltSimulator,
        secondary_belt: BeltSimulator,
    ):
        self.engine_simulator = engine_simulator
        self.primary_simulator = primary_simulator
        self.secondary_simulator = secondary_simulator
        self.primary_belt = primary_belt
        self.secondary_belt = secondary_belt
        self.cvt_moving_mass = 1  # TODO: Use constants

    def get_pulley_forces(self, state: SystemState):
        # Compute CVT ratio and engine velocity
        cvt_ratio = tm.current_cvt_ratio(state.shift_distance)
        wheel_to_engine_ratio = (
            cvt_ratio * GEARBOX_RATIO
        ) / WHEEL_RADIUS  # or import these constants
        engine_velocity = state.car_velocity * wheel_to_engine_ratio

        # Engine torque for secondary force calculation
        engine_torque = self.engine_simulator.get_torque(engine_velocity)

        # Calculate forces using the provided simulators
        primary_force = self.primary_simulator.calculate_net_force(
            state.shift_distance, engine_velocity
        )
        secondary_force = self.secondary_simulator.calculate_net_force(
            engine_torque * cvt_ratio, state.shift_distance
        )

        # Calculate wrap angles and convert to radial forces
        primary_wrap_angle = tm.primary_wrap_angle(state.shift_distance)
        secondary_wrap_angle = tm.secondary_wrap_angle(state.shift_distance)
        primary_radial = self.primary_belt.calculate_radial_force(
            engine_velocity, state.shift_distance, primary_wrap_angle, primary_force
        )
        secondary_radial = self.secondary_belt.calculate_radial_force(
            engine_velocity, state.shift_distance, secondary_wrap_angle, secondary_force
        )

        return {
            "primary_force": primary_force,
            "secondary_force": secondary_force,
            "primary_radial": primary_radial,
            "secondary_radial": secondary_radial,
        }

    def frictional_force(
        self, sum_of_radial_forces: float, shift_velocity: float
    ) -> float:
        raw_friction = 20  # TODO: Update to use calculation
        friction_magnitude = min(raw_friction, abs(sum_of_radial_forces))
        if shift_velocity > 0:
            return -friction_magnitude
        return friction_magnitude

    def calculate_shift_acceleration(self, state: SystemState) -> float:
        pulley_forces = self.get_pulley_forces(state)
        shift_velocity = state.shift_velocity

        sum_of_radial_forces = (
            pulley_forces["primary_radial"] - pulley_forces["secondary_radial"]
        )
        friction = self.frictional_force(sum_of_radial_forces, shift_velocity)
        return (sum_of_radial_forces + friction) / self.cvt_moving_mass
