from models.radial_model import RadialPulleyModel
from utils.system_state import SystemState
from utils.theoretical_models import TheoreticalModels as tm
from models.engine_model import EngineModel
from models.primary_pulley_model import PrimaryPulleyModel
from models.secondary_pulley_model import SecondaryPulleyModel
from models.belt_model import BeltModel
from constants.car_specs import GEARBOX_RATIO, WHEEL_RADIUS


class CvtShiftModel:
    def __init__(
        self,
        engine_model: EngineModel,
        primary_radial_model: RadialPulleyModel,
        secondary_radial_model: RadialPulleyModel,
    ):
        self.engine_model = engine_model
        self.primary_radial_model = primary_radial_model
        self.secondary_radial_model = secondary_radial_model
        self.cvt_moving_mass = 0.5  # TODO: Use constants

    def calculate_shift_acceleration(self, state: SystemState) -> float:
        pulley_forces = self.get_pulley_forces(state)
        shift_velocity = state.shift_velocity

        sum_of_radial_forces = (
            pulley_forces["primary_radial"] - pulley_forces["secondary_radial"]
        )
        friction = self.frictional_force(sum_of_radial_forces, shift_velocity)
        return (sum_of_radial_forces + friction) / self.cvt_moving_mass

    def get_pulley_forces(self, state: SystemState):
        # Compute CVT ratio and engine velocity
        cvt_ratio = tm.current_cvt_ratio(state.shift_distance)
        wheel_to_engine_ratio = (
            cvt_ratio * GEARBOX_RATIO
        ) / WHEEL_RADIUS  # or import these constants
        engine_velocity = state.car_velocity * wheel_to_engine_ratio

        # Engine torque for secondary force calculation
        engine_torque = self.engine_model.get_torque(engine_velocity)

        # Calculate forces using the provided simulators
        primary_force = self.primary_radial_model.get_breakdown(
            state.shift_distance, engine_velocity
        ).net
        secondary_force = self.secondary_model.get_breakdown(
            engine_torque * cvt_ratio, state.shift_distance
        ).net



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

    
