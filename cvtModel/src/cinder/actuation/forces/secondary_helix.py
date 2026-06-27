"""Torque-reactive secondary helix with torsional spring and sheave inertia."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from cinder.closure import AffineClosureScalar, ClosureGains
from cinder.profiles.helix import HelixProfile

from ..types import PulleyActuationState


@dataclass(frozen=True, slots=True)
class SecondaryHelixForceSpec:
    """
    Parameters of the physical secondary helix assembly.

    ``movable_sheave_rotational_inertia`` is I_M. It is the same physical
    inertia that appears in the secondary rotational balance.
    """

    helix_profile: HelixProfile
    movable_sheave_rotational_inertia: float
    torsional_stiffness: float
    initial_twist: float
    movable_sheave_torque_fraction: float = 0.5

    def __post_init__(self) -> None:
        if (
            not isfinite(self.movable_sheave_rotational_inertia)
            or self.movable_sheave_rotational_inertia < 0.0
        ):
            raise ValueError(
                "movable_sheave_rotational_inertia must be finite and "
                "non-negative."
            )

        if (
            not isfinite(self.torsional_stiffness)
            or self.torsional_stiffness < 0.0
        ):
            raise ValueError(
                "torsional_stiffness must be finite and non-negative."
            )

        if not isfinite(self.initial_twist):
            raise ValueError("initial_twist must be finite.")

        if not isfinite(self.movable_sheave_torque_fraction):
            raise ValueError(
                "movable_sheave_torque_fraction must be finite."
            )


class SecondaryHelixForce:
    """
    Return the *local* secondary axial-force relation.

    The helix profile is parameterized by local secondary coordinate x_s,
    while the closure solve uses global shift coordinate s. With

        H = dtheta/ds
          = (dtheta/dx_s) (dx_s/ds)

        H' = d²theta/ds²
           = (d²theta/dx_s²) (dx_s/ds)²
             + (dtheta/dx_s) (d²x_s/ds²),

    the movable sheave's absolute angular acceleration is

        alpha_M = alpha_s - H' s_dot² - H s_ddot.

    This force law returns local force F_xs. The later global shift row
    must apply virtual work once:

        Q_s = F_xs (dx_s/ds).

    That one factor produces the expected global helix terms
    -I_M H alpha_s, I_M H² s_ddot, and I_M H H' s_dot².
    """

    def __init__(self, spec: SecondaryHelixForceSpec) -> None:
        self._spec = spec

    @property
    def spec(self) -> SecondaryHelixForceSpec:
        return self._spec

    def evaluate(
        self,
        state: PulleyActuationState,
    ) -> AffineClosureScalar:
        sample = self._spec.helix_profile.evaluate(
            state.axial_position
        )

        theta = sample.theta
        dtheta_dx = sample.dtheta_dx
        d2theta_dx2 = sample.d2theta_dx2

        dx_ds = state.axial_coordinate_slope
        d2x_ds2 = state.axial_coordinate_curvature
        shift_speed = state.resolved_global_shift_speed

        dtheta_ds = dtheta_dx * dx_ds
        d2theta_ds2 = (
            d2theta_dx2 * dx_ds**2
            + dtheta_dx * d2x_ds2
        )

        inertia = self._spec.movable_sheave_rotational_inertia

        torsional_spring_torque = (
            self._spec.torsional_stiffness
            * (self._spec.initial_twist + theta)
        )

        return AffineClosureScalar(
            bias=(
                dtheta_dx * torsional_spring_torque
                + inertia
                * dtheta_dx
                * d2theta_ds2
                * shift_speed**2
            ),
            gains=ClosureGains(
                secondary_angular_acceleration=(
                    -inertia * dtheta_dx
                ),
                shift_acceleration=(
                    inertia * dtheta_dx * dtheta_ds
                ),
                secondary_torque=(
                    self._spec.movable_sheave_torque_fraction
                    * dtheta_dx
                ),
            ),
        )
