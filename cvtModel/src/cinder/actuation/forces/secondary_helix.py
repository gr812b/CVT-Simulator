"""Local torque-reactive secondary helix axial-force law."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from cinder.closure import AffineClosureScalar, ClosureGains
from cinder.profiles.helix import HelixProfile

from ..types import PulleyActuationState


@dataclass(frozen=True, slots=True)
class SecondaryHelixForceSpec:
    """
    Non-geometric parameters of the local secondary helix force law.

    The physical helix profile is deliberately absent. It is created and
    retained independently at system construction, then passed into this
    local force law and later directly into secondary rotational dynamics.

    I_M is likewise absent: the resolved inertia object remains its single
    physical source of truth.
    """

    torsional_stiffness: float
    initial_twist: float
    movable_sheave_torque_fraction: float = 0.5

    def __post_init__(self) -> None:
        _require_nonnegative(
            "torsional_stiffness",
            self.torsional_stiffness,
        )
        _require_finite("initial_twist", self.initial_twist)
        _require_finite(
            "movable_sheave_torque_fraction",
            self.movable_sheave_torque_fraction,
        )


class SecondaryHelixForce:
    """
    One normal local axial-force law for ``PulleyActuator``.

    The profile is evaluated in the local secondary coordinate x_s. The
    force law remains a standard affine closure contributor; it exposes no
    secondary-specific result object and owns no rotational-row interface.
    """

    def __init__(
        self,
        *,
        spec: SecondaryHelixForceSpec,
        helix_profile: HelixProfile,
        movable_sheave_rotational_inertia: float,
    ) -> None:
        _require_nonnegative(
            "movable_sheave_rotational_inertia",
            movable_sheave_rotational_inertia,
        )
        self._spec = spec
        self._helix_profile = helix_profile
        self._movable_sheave_rotational_inertia = (
            movable_sheave_rotational_inertia
        )

    @property
    def spec(self) -> SecondaryHelixForceSpec:
        return self._spec

    def evaluate(
        self,
        state: PulleyActuationState,
    ) -> AffineClosureScalar:
        """
        Return the local secondary axial-force relation F_xs.

        Let theta = theta(x_s), with local derivatives theta_x and
        theta_xx. The movable sheave has angular acceleration

            alpha_M = alpha_s - theta_xx x_dot_s^2 - theta_x x_ddot_s.

        With x_dot_s = x_s' s_dot and
        x_ddot_s = x_s'' s_dot^2 + x_s' s_ddot, the force law is kept
        affine in the core unknowns while all known s_dot squared terms
        remain in the bias.
        """

        sample = self._helix_profile.evaluate(state.axial_position)
        theta_x = sample.dtheta_dx
        theta_xx = sample.d2theta_dx2

        x_s_prime = state.axial_coordinate_slope
        x_s_double_prime = state.axial_coordinate_curvature
        shift_speed = state.resolved_global_shift_speed

        dtheta_ds = theta_x * x_s_prime
        d2theta_ds2 = (
            theta_xx * x_s_prime**2
            + theta_x * x_s_double_prime
        )

        torsional_spring_torque = (
            self._spec.torsional_stiffness
            * (self._spec.initial_twist + sample.theta)
        )
        inertia = self._movable_sheave_rotational_inertia

        return AffineClosureScalar(
            bias=(
                theta_x * torsional_spring_torque
                + inertia
                * theta_x
                * d2theta_ds2
                * shift_speed**2
            ),
            gains=ClosureGains(
                secondary_angular_acceleration=(
                    -inertia * theta_x
                ),
                shift_acceleration=(
                    inertia * theta_x * dtheta_ds
                ),
                secondary_torque=(
                    self._spec.movable_sheave_torque_fraction
                    * theta_x
                ),
            ),
        )


def _require_finite(name: str, value: float) -> None:
    if not isfinite(value):
        raise ValueError(f"{name} must be finite.")


def _require_nonnegative(name: str, value: float) -> None:
    if not isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative.")
