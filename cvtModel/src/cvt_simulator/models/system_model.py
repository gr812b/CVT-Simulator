from cvt_simulator.models.dataTypes import SystemBreakdown
from cvt_simulator.models.slip_model import SlipModel
from cvt_simulator.models.engine_accel_model import EngineAccelModel
from cvt_simulator.models.car_model import CarModel
from cvt_simulator.models.cvt_shift_model import CvtShiftModel
from cvt_simulator.utils.system_state import SystemState


class SystemModel:
    """Single system model that manages all component interactions and dependencies."""

    def __init__(
        self,
        slip_model: SlipModel,
        engine_accel_model: EngineAccelModel,
        car_model: CarModel,
        cvt_shift_model: CvtShiftModel,
    ):
        self.slip_model = slip_model
        self.engine_accel_model = engine_accel_model
        self.car_model = car_model
        self.cvt_shift_model = cvt_shift_model

    def get_breakdown(self, state: SystemState) -> SystemBreakdown:
        """
        Calculate the complete system breakdown in dependency order.

        Dependency order:
        1. CVT (calculated first to get radial forces and wrap angles)
        2. Slip (needs CVT breakdown for T_MAX calculation)
        3. Engine (needs slip)
        4. Car (needs slip)
        """

        # Step 1: Calculate CVT dynamics first
        cvt_breakdown = self.cvt_shift_model.get_breakdown(state, 0)

        # Step 2: Calculate slip dynamics (using CVT breakdown for T_MAX calculation)
        slip_breakdown = self.slip_model.get_breakdown(state, cvt_breakdown)

        # Recalculate CVT dynamics with actual T_c from slip model
        cvt_breakdown = self.cvt_shift_model.get_breakdown(state, slip_breakdown.t_c)

        # Step 3: Calculate engine dynamics (using slip)
        engine_breakdown = self.engine_accel_model.get_breakdown(state, slip_breakdown)

        # Step 4: Calculate car dynamics (using slip)
        car_breakdown = self.car_model.get_breakdown(state, slip_breakdown)

        return SystemBreakdown(
            slip=slip_breakdown,
            engine=engine_breakdown,
            car=car_breakdown,
            cvt=cvt_breakdown,
        )
