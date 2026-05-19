"""Secondary pulley clamping helper (focused, no abstracts).

Exposes `SecondaryPulley.calculate_axial_clamping_force(shift, torque)` which returns
`(axial_force, SecondaryForceBreakdown)` using existing datatypes.
"""
from typing import Tuple
import numpy as np
from cvt_simulator.geometry.cvt_geometry import CVT_GEOMETRY
from cvt_simulator.constants.car_specs import MAX_SHIFT
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm
from cvt_simulator.core.system_state import SystemState
from cvt_simulator.models.dataTypes import (
    HelixForceBreakdown,
    SpringTorsForceBreakdown,
    springCompForceBreakdown,
    SecondaryForceBreakdown,
)


class SecondaryPulley:
    """Compute secondary pulley clamping (helix torque-reactive + springs).

    Parameters:
        spring_coeff_tors: Torsion spring stiffness [N⋅m/rad]
        spring_coeff_comp: Compression spring stiffness [N/m]
        initial_rotation: Torsion spring preload [rad]
        initial_compression: Compression spring preload [m]
        helix_ramp: Object providing `theta(shift)`, `dtheta_dx(shift)`,
                    and `angle_multiplier(shift)` methods (ThetaRamp)
        helix_radius: Base helix radius [m]
    """

    def __init__(
        self,
        spring_coeff_tors: float,
        spring_coeff_comp: float,
        initial_rotation: float,
        initial_compression: float,
        helix_ramp,
        helix_radius: float,
    ) -> None:
        self.spring_coeff_tors = spring_coeff_tors
        self.spring_coeff_comp = spring_coeff_comp
        self.initial_rotation = initial_rotation
        self.initial_compression = initial_compression
        self.helix_ramp = helix_ramp
        self.helix_radius = helix_radius
        self.cvt = CVT_GEOMETRY

    def calculate_axial_clamping_force(self, state: SystemState, τ: float) -> SecondaryForceBreakdown:
        """Return (axial_clamping_force, SecondaryForceBreakdown) from `state` and `tau`.

        Args:
            state: Current system state
            τ: Transmitted torque at the secondary [N·m]
        """
        s = float(np.clip(state.s, 0.0, MAX_SHIFT))

        helix = self._calculate_helix_force(τ, s)
        spring_comp = self._calculate_spring_comp_force(s)

        axial = helix.net + spring_comp.net

        breakdown = SecondaryForceBreakdown(
            springCompForce=spring_comp,
            helix_force=helix,
            net=axial,
        )

        return breakdown

    def _calculate_helix_force(
        self, τ: float, s: float
    ) -> HelixForceBreakdown:
        """Calculate helix cam force from transmitted torque.

        Uses: F_s,helix,ax = [τ_s + k_s,0(θ_s,0 + θ_s(s)) * dθ_s/ds] / 2
        """
        s = np.clip(s, 0.0, MAX_SHIFT)

        spring_torque_breakdown = self._calculate_spring_tors_torque(s)
        angle_multiplier = self.helix_ramp.angle_multiplier(s)
        dtheta_ds = self.helix_ramp.dtheta_dx(s)
        helix_angle = float(np.arctan2(1.0, self.helix_radius * dtheta_ds))

        net = (τ + spring_torque_breakdown.net) * dtheta_ds / 2.0

        return HelixForceBreakdown(
            feedbackTorque=τ,
            springTorque=spring_torque_breakdown,
            angle=helix_angle,
            radius=self.helix_radius,
            angle_multiplier=angle_multiplier,
            net=net,
        )

    def _calculate_spring_comp_force(self, s: float) -> springCompForceBreakdown:
        """Calculate compression spring force (static clamping)."""
        s = np.clip(s, 0.0, MAX_SHIFT)
        total_compression = self.initial_compression + s
        net = tm.hookes_law_comp(self.spring_coeff_comp, total_compression)
        return springCompForceBreakdown(compression=s, net=net)

    def _calculate_spring_tors_torque(self, s: float) -> SpringTorsForceBreakdown:
        """Calculate torsion spring torque from preload + ramp rotation."""
        s = np.clip(s, 0.0, MAX_SHIFT)
        rotation_from_shift = self.helix_ramp.theta(s)
        total_rotation = self.initial_rotation + rotation_from_shift
        net = tm.hookes_law_tors(self.spring_coeff_tors, total_rotation)
        return SpringTorsForceBreakdown(rotation=total_rotation, net=net)

