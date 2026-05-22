"""Shift dynamics model.

Computes shift acceleration using primary and secondary pulley states
and net axial force balance.
"""
from cvt_simulator.core.data_types import CvtDynamicsBreakdown
from cvt_simulator.core.components.primary_pulley import PrimaryPulley
from cvt_simulator.core.components.secondary_pulley import SecondaryPulley
from cvt_simulator.sim_utils.system_state import SystemState

class ShiftDynamics:
    """Compute shift acceleration from pulley states and axial force balance.

    This model:
    1. Takes generic pulley models (any implementation)
    2. Gets pulley states from each pulley
    3. Extracts net axial forces
    4. Computes shift acceleration from force balance
    5. Handles friction and system dynamics

    Parameters:
        primary_pulley: PrimaryPulleyModel interface instance
        secondary_pulley: SecondaryPulleyModel interface instance
        cvt_moving_mass: Equivalent mass of shift mechanism [kg]
    """

    def __init__(
        self,
        primary_pulley: PrimaryPulley,
        secondary_pulley: SecondaryPulley,
        cvt_moving_mass: float = 0.5,
    ) -> None:
        self.primary_pulley = primary_pulley
        self.secondary_pulley = secondary_pulley
        self.cvt_moving_mass = cvt_moving_mass
        # Shift dynamics now rely on pulley-provided `PulleyForces`

    def get_breakdown(
        self,
        state: SystemState,
        τ_s: float,
    ) -> CvtDynamicsBreakdown:
        """Compute shift dynamics breakdown.

        Args:
            state: Current system state
            τ_s: Secondary torque transmitted through CVT [N·m].

        Returns:
            CvtDynamicsBreakdown with all force and acceleration data
        """
        # Get primary pulley state (speed-reactive)
        primary_forces = self.primary_pulley.calculate_axial_clamping_force(state)

        # Get secondary pulley forces (torque-reactive)
        secondary_forces = self.secondary_pulley.calculate_axial_clamping_force(state, τ_s)

        prim_axial = primary_forces.net
        sec_axial = secondary_forces.net
        net = prim_axial - sec_axial

        friction = self._frictional_force(net, state.s_dot)

        acceleration = (net + friction) / self.cvt_moving_mass

        return CvtDynamicsBreakdown(
            primaryPulleyState=primary_forces,
            secondaryPulleyState=secondary_forces,
            friction=friction,
            acceleration=acceleration,
            net=net,
        )

    def _frictional_force(self, net_axial_force: float, s_dot: float) -> float:
        """Compute frictional force opposing shift motion.

        Args:
            net_axial_force: Net force from pulley balance [N]
            s_dot: Current shift velocity [m/s]

        Returns:
            Frictional force [N]
        """
        raw_friction = 20  # TODO: Use calculated/tuned value
        friction_magnitude = min(raw_friction, abs(net_axial_force))
        if s_dot > 0:
            return -friction_magnitude
        return friction_magnitude

