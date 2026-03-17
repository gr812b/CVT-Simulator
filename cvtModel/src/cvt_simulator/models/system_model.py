from cvt_simulator.models.dataTypes import DrivetrainBreakdown
from cvt_simulator.models.slip_model import SlipModel
from cvt_simulator.models.primary_pulley_model import PrimaryPulleyModel
from cvt_simulator.models.secondary_pulley_model import SecondaryPulleyModel
from cvt_simulator.models.cvt_shift_model import CvtShiftModel
from cvt_simulator.utils.system_state import SystemState


class SystemModel:
    """Single system model that manages all component interactions and dependencies."""

    def __init__(
        self,
        slip_model: SlipModel,
        primary_pulley_model: PrimaryPulleyModel,
        secondary_pulley_model: SecondaryPulleyModel,
        cvt_shift_model: CvtShiftModel,
    ):
        self.slip_model = slip_model
        self.primary_pulley_model = primary_pulley_model
        self.secondary_pulley_model = secondary_pulley_model
        self.cvt_shift_model = cvt_shift_model

    def get_breakdown(self, state: SystemState) -> DrivetrainBreakdown:
        """
        Calculate the complete system breakdown in dependency order.

        Dependency order:
        1. Slip (can calculate T_max directly from pulley models)
        2. CVT Shift (needs slip for coupling_torque)
        3. Engine (needs torque through belt)
        4. Car (needs torque through belt)
        """

        # Step 1: Calculate slip dynamics (using pulley models directly)
        slip_breakdown = self.slip_model.get_breakdown(state)

        # Step 2: Calculate CVT dynamics with actual coupling_torque from slip model
        cvt_breakdown = self.cvt_shift_model.get_breakdown(
            state, slip_breakdown.coupling_torque
        )

        # Step 3: Calculate primary-pulley-side dynamics (using slip)
        primary_pulley_breakdown = self.primary_pulley_model.get_breakdown(
            state, slip_breakdown.coupling_torque
        )

        # Step 4: Calculate secondary-pulley-side dynamics (using slip)
        secondary_pulley_breakdown = self.secondary_pulley_model.get_breakdown(
            state, slip_breakdown.coupling_torque
        )

        return DrivetrainBreakdown(
            belt_slip=slip_breakdown,
            primary_pulley=primary_pulley_breakdown,
            secondary_pulley=secondary_pulley_breakdown,
            cvt_dynamics=cvt_breakdown,
        )
