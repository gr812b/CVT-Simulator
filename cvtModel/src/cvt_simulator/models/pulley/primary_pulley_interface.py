from cvt_simulator.models.pulley.pulley_interface import PulleyModel
from pyparsing import ABC
from cvt_simulator.constants.car_specs import (
    BELT_HEIGHT,
)
from cvt_simulator.utils.system_state import SystemState
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm

class PrimaryPulleyModel(PulleyModel, ABC):
    """
    Abstract base for primary (engine-side) pulley implementations.
    
    Primary pulleys typically:
    - Run at engine speed
    - Generate clamping force from centrifugal mechanisms (flyweights) or active control
    - Start at large radius (low ratio) and shift to small radius (high ratio)
    
    Concrete geometric methods are provided based on CVT geometry,
    only clamping force calculation is left to specific implementations.
    """
    
    def _get_wrap_angle(self, shift_distance: float) -> float:
        """Get primary belt wrap angle at current shift position [rad]."""
        return tm.primary_wrap_angle(shift_distance)
    
    def _get_radius(self, shift_distance: float) -> float:
        """Get primary effective pitch radius at current shift position [m]."""
        return tm.outer_prim_radius(shift_distance) - BELT_HEIGHT / 2
    
    def _get_angular_velocity(self, state: SystemState) -> float:
        """Get primary pulley angular velocity (engine speed) [rad/s]."""
        return state.engine_angular_velocity