from __future__ import annotations

from dataclasses import dataclass

from cinder.profiles import HelixProfile

from ..types import PulleyActuationResult, PulleyActuationState


@dataclass(frozen=True, slots=True)
class HelixTorqueReactionForceSpec:
    """
    Torque-reactive local axial-force relation through a helix.

    Let the helix see a torque:

        tau_helix = torque_to_helix_sign * tau_pulley.

    Virtual work gives:

        F_x = tau_helix * dtheta/dx.

    Therefore the force relation returned to the closure is:

        F_x = 0 + (
            torque_to_helix_sign * dtheta/dx
        ) * tau_pulley.

    ``torque_to_helix_sign`` maps the chosen pulley-torque sign convention to
    the torque applied across the helix. It is a physical handedness / torque
    path parameter, not a primary-versus-secondary assembly patch.

    Choose it so normal transmitted torque gives the desired local direction:
    positive force closes the pulley; negative force opens it.
    """

    helix_profile: HelixProfile
    torque_to_helix_sign: int

    def __post_init__(self) -> None:
        if self.torque_to_helix_sign not in (-1, 1):
            raise ValueError(
                "torque_to_helix_sign must be either -1 or 1."
            )


class HelixTorqueReactionForce:
    """
    Affine pulley-torque coefficient for either primary or secondary.

    The surrounding actuator determines which closure torque multiplies the
    returned gain: tau_p for a primary and tau_s for a secondary.
    """

    def __init__(self, spec: HelixTorqueReactionForceSpec) -> None:
        self._spec = spec

    @property
    def spec(self) -> HelixTorqueReactionForceSpec:
        return self._spec

    def force_relation(
        self,
        state: PulleyActuationState,
    ) -> PulleyActuationResult:
        helix = self._spec.helix_profile.evaluate(state.axial_position)

        return PulleyActuationResult(
            bias_force=0.0,
            torque_gain=(
                self._spec.torque_to_helix_sign
                * helix.dtheta_dx
            ),
        )
