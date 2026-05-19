from cvt_simulator.models.pulley.pulley_interface import PulleyModel
from pyparsing import ABC
from cvt_simulator.core.system_state import SystemState
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm


class PrimaryPulleyModel(PulleyModel, ABC):
    """
    Abstract base for primary (engine-side) pulley implementations.

    Primary pulleys typically:
    - Run at primary pulley speed (engine speed)
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
        return tm.primary_effective_radius(shift_distance)

    def _get_radius_rate_of_change(self, shift_distance: float):
        """Get dr/dt at current shift position [m/m]."""
        return tm.primary_radius_rate_of_change(shift_distance)

    def _get_angular_velocity(self, state: SystemState) -> float:
        """Get primary pulley angular velocity [rad/s]."""
        return state.ω_p

    def _get_angular_position(self, state: SystemState) -> float:
        """Get primary pulley angular position (engine position) [rad].

        Note: Angular position is not part of the core 4 DOF state.
        This method is kept for compatibility but should not be used for ODE integration.
        """
        return 0.0  # Placeholder - position is not integrated as part of core dynamics
