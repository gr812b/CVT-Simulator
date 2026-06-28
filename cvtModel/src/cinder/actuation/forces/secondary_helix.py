"""Local secondary helix axial-force law."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from cinder.closure import AffineClosureScalar, ClosureGains
from cinder.profiles.helix import HelixProfile

from ..types import PulleyActuationState


@dataclass(frozen=True, slots=True)
class SecondaryHelixForceSpec:
    """
    Elastic and torque-transfer parameters of the local helix force law.

    Helix geometry is deliberately absent. The physical ``HelixProfile`` is
    passed separately when the force law is built, because the same profile
    is also required later by secondary rotational dynamics.

    The movable-sheave rotational inertia I_M is likewise supplied
    separately from resolved inertia data so it has one source of truth.
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
    Ordinary local axial-force law used by ``PulleyActuator``.

    The local helix profile is theta(x_s). The force law uses that profile
    to form the local secondary axial-force relation. It does not expose
    helix kinematics for other equations; later rotational dynamics uses
    the same separately owned ``HelixProfile`` directly.
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

        The profile is evaluated locally at x_s. The local movable-sheave
        acceleration is represented through the global-shift closure
        coefficients already carried by ``PulleyActuationState``.
        """

        sample = self._helix_profile.evaluate(state.axial_position)

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

        torsional_spring_torque = (
            self._spec.torsional_stiffness
            * (self._spec.initial_twist + theta)
        )
        inertia = self._movable_sheave_rotational_inertia

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


def _require_finite(name: str, value: float) -> None:
    if not isfinite(value):
        raise ValueError(f"{name} must be finite.")


def _require_nonnegative(name: str, value: float) -> None:
    if not isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative.")
