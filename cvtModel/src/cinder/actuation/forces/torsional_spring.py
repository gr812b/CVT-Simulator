from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from cinder.profiles import HelixProfile

from ..types import PulleyActuationResult, PulleyActuationState


@dataclass(frozen=True, slots=True)
class TorsionalSpringForceSpec:
    """
    Torsion spring reflected into local axial force through a helix.

    The HelixProfile convention gives theta(0) = 0 for an un-offset physical
    profile. Define the spring's signed twist as:

        delta_theta(x) = initial_twist
                         + twist_per_helix_rotation * theta(x).

    The local force is obtained directly from stored energy:

        U = 1/2 * k_theta * delta_theta(x)^2
        F_x = -dU/dx
            = -k_theta * delta_theta(x)
              * twist_per_helix_rotation
              * dtheta/dx.

    Local x is positive toward pulley closure.

    The two sign-bearing inputs describe actual assembly geometry:
      - ``initial_twist`` is the signed preload at x = 0;
      - ``twist_per_helix_rotation`` says whether increasing helix theta
        increases (+) or decreases (-) spring twist.

    A conventional secondary can therefore be configured so its preloaded
    torsion spring contributes a positive closing force, without giving the
    law any primary/secondary-specific branch.
    """

    torsional_stiffness: float
    initial_twist: float
    twist_per_helix_rotation: float
    helix_profile: HelixProfile

    def __post_init__(self) -> None:
        if (
            not isfinite(self.torsional_stiffness)
            or self.torsional_stiffness <= 0.0
        ):
            raise ValueError(
                "torsional_stiffness must be finite and positive."
            )

        if not isfinite(self.initial_twist):
            raise ValueError("initial_twist must be finite.")

        if (
            not isfinite(self.twist_per_helix_rotation)
            or self.twist_per_helix_rotation == 0.0
        ):
            raise ValueError(
                "twist_per_helix_rotation must be finite and nonzero."
            )


class TorsionalSpringForce:
    """A torsion spring reflected through a HelixProfile."""

    def __init__(self, spec: TorsionalSpringForceSpec) -> None:
        self._spec = spec

    @property
    def spec(self) -> TorsionalSpringForceSpec:
        return self._spec

    def force_relation(
        self,
        state: PulleyActuationState,
    ) -> PulleyActuationResult:
        helix = self._spec.helix_profile.evaluate(state.axial_position)

        spring_twist = (
            self._spec.initial_twist
            + self._spec.twist_per_helix_rotation * helix.theta
        )

        axial_force = (
            -self._spec.torsional_stiffness
            * spring_twist
            * self._spec.twist_per_helix_rotation
            * helix.dtheta_dx
        )

        return PulleyActuationResult(
            bias_force=axial_force,
            torque_gain=0.0,
        )
