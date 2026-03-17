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
    - Run at wheel speed (through gearbox)
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
        """Get secondary pulley angular velocity (wheel speed / gearbox) [rad/s]."""
        wheel_to_sec_ratio = GEARBOX_RATIO / WHEEL_RADIUS
        return state.car_velocity * wheel_to_sec_ratio

    def _get_angular_position(self, state: SystemState) -> float:
        """Get secondary pulley angular position (wheel position / gearbox) [rad]."""
        wheel_to_sec_ratio = GEARBOX_RATIO / WHEEL_RADIUS
        return state.car_position * wheel_to_sec_ratio
