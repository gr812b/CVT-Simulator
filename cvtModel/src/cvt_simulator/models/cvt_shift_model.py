from cvt_simulator.models.dataTypes import CvtSystemForceBreakdown
from cvt_simulator.models.radial_model import RadialPulleyModel
from cvt_simulator.utils.system_state import SystemState
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm
from cvt_simulator.models.engine_model import EngineModel


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

    def get_breakdown(self, state: SystemState, t_c: float) -> CvtSystemForceBreakdown:
        prim_breakdown, sec_breakdown = self._get_pulley_breakdowns(state, t_c)

        prim_radial = prim_breakdown.net
        sec_radial = sec_breakdown.net
        net = prim_radial - sec_radial

        shift_velocity = state.shift_velocity
        friction = self._frictional_force(net, shift_velocity)

        acceleration = (net + friction) / self.cvt_moving_mass

        cvt_ratio = tm.current_cvt_ratio(state.shift_distance)

        return CvtSystemForceBreakdown(
            prim_breakdown,
            sec_breakdown,
            friction,
            acceleration,
            cvt_ratio,
            net,
        )

    def _get_pulley_breakdowns(self, state: SystemState, t_c: float):
        # Calculate forces using the provided simulators
        primary_radial_breakdown = self.primary_radial_model.get_breakdown(state, t_c)
        cvt_ratio = tm.current_cvt_ratio(state.shift_distance)
        secondary_radial_breakdown = self.secondary_radial_model.get_breakdown(
            state, t_c * cvt_ratio
        )

        return primary_radial_breakdown, secondary_radial_breakdown

    def _frictional_force(
        self, sum_of_radial_forces: float, shift_velocity: float
    ) -> float:
        raw_friction = 20  # TODO: Update to use calculation
        friction_magnitude = min(raw_friction, abs(sum_of_radial_forces))
        if shift_velocity > 0:
            return -friction_magnitude
        return friction_magnitude
