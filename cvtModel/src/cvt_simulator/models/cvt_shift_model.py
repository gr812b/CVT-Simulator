from cvt_simulator.models.dataTypes import CvtSystemForceBreakdown
from cvt_simulator.models.pulley.primary_pulley_interface import PrimaryPulleyModel
from cvt_simulator.models.pulley.secondary_pulley_interface import SecondaryPulleyModel
from cvt_simulator.utils.system_state import SystemState
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm
from cvt_simulator.models.engine_model import EngineModel


class CvtShiftModel:
    """
    CVT shift dynamics model using the new generic pulley interface system.

    This model:
    1. Takes generic pulley models (any implementation: physical, PID, lookup, etc.)
    2. Uses total axial forces from each pulley
    3. Determines net shift force and acceleration from the axial force balance
    4. Handles friction and system dynamics

    The abstraction allows swapping pulley implementations without changing
    the core shift dynamics.
    """

    def __init__(
        self,
        engine_model: EngineModel,
        primary_pulley: PrimaryPulleyModel,
        secondary_pulley: SecondaryPulleyModel,
    ):
        self.engine_model = engine_model
        self.primary_pulley = primary_pulley
        self.secondary_pulley = secondary_pulley
        self.cvt_moving_mass = 0.5  # TODO: Use constants

    def get_breakdown(
        self, state: SystemState, coupling_torque: float
    ) -> CvtSystemForceBreakdown:
        primary_state, secondary_state = self._get_pulley_states(state, coupling_torque)

        prim_axial = primary_state.forces.axial_force_total
        sec_axial = secondary_state.forces.axial_force_total
        net = prim_axial - sec_axial

        shift_velocity = state.shift_velocity
        friction = self._frictional_force(net, shift_velocity)

        acceleration = (net + friction) / self.cvt_moving_mass

        cvt_ratio = tm.current_effective_cvt_ratio(state.shift_distance)

        return CvtSystemForceBreakdown(
            primary_state,
            secondary_state,
            friction,
            acceleration,
            cvt_ratio,
            net,
        )

    def _get_pulley_states(self, state: SystemState, coupling_torque: float):
        """
        Get pulley states from both pulleys using their specific implementations.

        Args:
            state: Current system state
            coupling_torque: Transmitted torque through CVT [N⋅m]

        Returns:
            tuple: (primary_state, secondary_state) as PulleyState objects
        """
        # Get primary pulley state (speed-reactive, doesn't need torque)
        primary_state = self.primary_pulley.get_pulley_state(state)

        # Calculate CVT ratio for torque scaling to secondary
        cvt_ratio = tm.current_effective_cvt_ratio(state.shift_distance)

        # Get secondary pulley state (torque-reactive, needs scaled torque)
        secondary_state = self.secondary_pulley.get_pulley_state(
            state, torque=coupling_torque * cvt_ratio  # Scale torque by CVT ratio
        )

        return primary_state, secondary_state

    def _frictional_force(self, net_axial_force: float, shift_velocity: float) -> float:
        raw_friction = 20  # TODO: Update to use calculation
        friction_magnitude = min(raw_friction, abs(net_axial_force))
        if shift_velocity > 0:
            return -friction_magnitude
        return friction_magnitude
