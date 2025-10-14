


from cvt_simulator.models.external_load_model import LoadModel
from cvt_simulator.models.engine_model import EngineModel
from cvt_simulator.utils.system_state import SystemState
from cvt_simulator.constants.car_specs import (
    WHEEL_RADIUS,
    GEARBOX_RATIO,
)


class slip_model:
    T_MAX = 10 # TODO: Replace with calculation
    inertia = 0.1 # TODO: Replace with real value

    def __init__(
        self,
        load_model: LoadModel,
        engine_model: EngineModel,
    ):
        self.load_model = load_model
        self.engine_model = engine_model

    def get_breakdown(self, state: SystemState):
        # Load seen at secondary as a torque
        # Assume infinite friction on secondary, so no slip on this side
        # Meaning belt transfers all that torque to the primary
        # Then determine if we slip on the primary
        sec_torque = self.get_secondary_torque(state)

        torque_experienced = min(sec_torque, self.T_MAX)
        # T_MAX should rise with clamping force, meaning
        # the engine will experience more load and slow down more
        # This is what we see in real life

        # torque produced
        engine_torque = self.engine_model.get_breakdown(state.engine_angular_velocity).torque

        # Now get accel
        angular_accel = (torque_experienced - engine_torque) / self.inertia

        return angular_accel
        


    def get_secondary_torque(self, state: SystemState):
        # Load that is applied at wheel radius
        load_force = self.load_model.get_breakdown(state).total_load_force

        # Convert to torque
        load_torque = load_force * WHEEL_RADIUS

        # Divide by gearbox (spin faster, less torque)
        load_torque /= GEARBOX_RATIO

        return load_torque