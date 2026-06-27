"""Torque-reactive secondary helix with torsional spring and sheave inertia."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from cinder.closure import AffineClosureScalar, ClosureGains
from cinder.profiles.helix import HelixProfile

from ..types import PulleyActuationState


@dataclass(frozen=True, slots=True)
class SecondaryHelixForceSpec:
    """Parameters of the physical secondary helix assembly.

    With

        h(s) = dtheta_s/ds,
        h'(s) = d²theta_s/ds²,

    this model returns the exact local axial-force relation:

        F_s,helix = h [
            f_tau tau_s
            + k_theta (theta_0 + theta_s)
            - I_M (alpha_s - h' s_dot² - h s_ddot)
        ].

    Therefore the known bias and closure gains are:

        bias = h k_theta (theta_0 + theta_s) + I_M h h' s_dot²,
        gain(alpha_s) = -I_M h,
        gain(s_ddot) = I_M h²,
        gain(tau_s) = f_tau h.

    ``initial_twist`` mirrors an axial-spring preload: it is the signed torsion
    spring deflection at local x = 0.  With CINDER's normal HelixProfile,
    theta(0) = 0 when ``theta_offset`` is left at its default zero.
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
    """Secondary helix relation aligned to CINDER's root closure basis."""

    def __init__(self, spec: SecondaryHelixForceSpec) -> None:
        self._spec = spec

    @property
    def spec(self) -> SecondaryHelixForceSpec:
        return self._spec

    def evaluate(self, state: PulleyActuationState) -> AffineClosureScalar:
        sample = self._spec.helix_profile.evaluate(state.axial_position)

        theta = sample.theta
        dtheta_dx = sample.dtheta_dx
        d2theta_dx2 = sample.d2theta_dx2
        inertia = self._spec.movable_sheave_rotational_inertia

        torsional_spring_torque = self._spec.torsional_stiffness * (
            self._spec.initial_twist + theta
        )

        bias_force = (
            dtheta_dx * torsional_spring_torque
            + inertia
            * dtheta_dx
            * d2theta_dx2
            * state.axial_speed**2
        )

        gains = ClosureGains(
            secondary_angular_acceleration=-inertia * dtheta_dx,
            shift_acceleration=inertia * dtheta_dx**2,
            secondary_torque=(
                self._spec.movable_sheave_torque_fraction * dtheta_dx
            ),
        )

        return AffineClosureScalar(bias=bias_force, gains=gains)
