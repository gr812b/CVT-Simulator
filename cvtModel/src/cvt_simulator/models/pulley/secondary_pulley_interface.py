from cvt_simulator.models.pulley.pulley_interface import PulleyModel
from pyparsing import ABC
from cvt_simulator.constants.car_specs import (
    GEARBOX_RATIO,
    WHEEL_RADIUS,
)
from cvt_simulator.utils.system_state import SystemState
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm


class SecondaryPulleyModel(PulleyModel, ABC):
    """
    Abstract base for secondary (driven-side) pulley implementations.

    Secondary pulleys typically:
    - Run at secondary pulley speed (wheel speed / gearbox)
    - Generate clamping force from torque feedback (helix) or active control
    - Start at small radius (low ratio) and shift to large radius (high ratio)
    - Must react to torque to provide back-pressure for shifting

    Concrete geometric methods are provided based on CVT geometry,
    only clamping force calculation is left to specific implementations.
    """

    def _get_wrap_angle(self, shift_distance: float) -> float:
        """Get secondary belt wrap angle at current shift position [rad]."""
        return tm.secondary_wrap_angle(shift_distance)

    def _get_radius(self, shift_distance: float) -> float:
        """Get secondary effective pitch radius at current shift position [m]."""
        return tm.secondary_effective_radius(shift_distance)

    def _get_angular_velocity(self, state: SystemState) -> float:
        """Get secondary pulley angular velocity [rad/s]."""
        return state.secondary_pulley_angular_velocity

    def _get_angular_position(self, state: SystemState) -> float:
        """Get secondary pulley angular position (wheel position / gearbox) [rad].
        
        Note: Angular position is not part of the core 4 DOF state.
        This method is kept for compatibility but should not be used for ODE integration.
        """
        return 0.0  # Placeholder - position is not integrated as part of core dynamics
