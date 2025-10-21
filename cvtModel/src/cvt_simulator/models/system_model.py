from cvt_simulator.models.dataTypes import SystemBreakdown
from cvt_simulator.models.slip_model import SlipModel
from cvt_simulator.models.engine_accel_model import EngineAccelModel
from cvt_simulator.models.car_model import CarModel
from cvt_simulator.models.cvt_shift_model import CvtShiftModel
from cvt_simulator.utils.system_state import SystemState


class SystemModel:
    """
    Single system model that manages all component interactions and dependencies.
    
    This solves the circular dependency problem by:
    1. Calculating components in the correct dependency order
    2. Passing computed dependencies to components that need them
    3. Providing a single breakdown that contains everything
    """
    
    def __init__(
        self,
        slip_model: SlipModel,
        engine_accel_model: EngineAccelModel,
        car_model: CarModel,
        cvt_shift_model: CvtShiftModel
    ):
        self.slip_model = slip_model
        self.engine_accel_model = engine_accel_model
        self.car_model = car_model
        self.cvt_shift_model = cvt_shift_model
    
    def get_breakdown(self, state: SystemState) -> SystemBreakdown:
        """
        Calculate the complete system breakdown in dependency order.
        
        Dependency order:
        1. Slip (needs engine & car state, but we calculate iteratively)
        2. Engine (needs slip)
        3. Car (needs slip)  
        4. CVT (needs current state)
        """
        
        # Step 1: Calculate slip dynamics (the coupling between systems)
        slip_breakdown = self.slip_model.get_breakdown(state)
        
        # Step 2: Calculate engine dynamics (using slip)
        engine_breakdown = self.engine_accel_model.get_breakdown(state, slip_breakdown)
        
        # Step 3: Calculate car dynamics (using slip)
        car_breakdown = self.car_model.get_breakdown(state, slip_breakdown)
        
        # Step 4: Calculate CVT dynamics
        cvt_breakdown = self.cvt_shift_model.get_breakdown(state)
        
        return SystemBreakdown(
            slip=slip_breakdown,
            engine=engine_breakdown,
            car=car_breakdown,
            cvt=cvt_breakdown
        )