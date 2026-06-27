"""Secondary helix kinematics and local torque-reactive axial force."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from cinder.closure import (
    AffineClosureScalar,
    ClosureGains,
    ClosureUnknowns,
)
from cinder.profiles.helix import HelixProfile

from ..types import PulleyActuationState


@dataclass(frozen=True, slots=True)
class SecondaryHelixForceSpec:
    """
    Fixed geometric and elastic parameters of the secondary helix.

    The movable sheave rotational inertia I_M is intentionally absent.
    It is owned by the resolved secondary inertia and supplied when the
    helix mechanism is constructed.
    """

    helix_profile: HelixProfile
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


@dataclass(frozen=True, slots=True)
class SecondaryHelixEvaluation:
    """
    One secondary-helix evaluation at the current known state.

    ``dtheta_ds`` and ``d2theta_ds2`` are the global derivatives used
    directly by the secondary rotational balance:

        alpha_M =
            alpha_s
            - d2theta_ds2 * s_dot^2
            - dtheta_ds * s_ddot.

    ``local_axial_force`` is still a force in the local secondary
    coordinate x_s. The global shift equation later applies virtual
    work once:

        Q_s = F_xs * dx_s/ds.
    """

    theta: float
    dtheta_ds: float
    d2theta_ds2: float
    local_axial_force: AffineClosureScalar

    @property
    def bias(self) -> float:
        return self.local_axial_force.bias

    @property
    def gains(self) -> ClosureGains:
        return self.local_axial_force.gains

    def force(self, unknowns: ClosureUnknowns) -> float:
        return self.local_axial_force.evaluate(unknowns)


class SecondaryHelixForce:
    """
    Evaluate the local secondary helix force and global helix kinematics.

    The profile is parameterized by local secondary coordinate x_s.
    Geometry provides x_s(s), dx_s/ds, and d2x_s/ds2 through
    ``PulleyActuationState``.

    For theta(x_s(s)):

        H  = dtheta/ds
           = (dtheta/dx_s) (dx_s/ds)

        H' = d2theta/ds2
           = (d2theta/dx_s2) (dx_s/ds)^2
             + (dtheta/dx_s) (d2x_s/ds2).

    The same H and H' are returned for use in the secondary rotational
    equation, while the local force relation remains available for the
    secondary clamp and global shift equation.
    """

    def __init__(
        self,
        *,
        spec: SecondaryHelixForceSpec,
        movable_sheave_rotational_inertia: float,
    ) -> None:
        _require_nonnegative(
            "movable_sheave_rotational_inertia",
            movable_sheave_rotational_inertia,
        )

        self._spec = spec
        self._movable_sheave_rotational_inertia = (
            movable_sheave_rotational_inertia
        )

    @property
    def spec(self) -> SecondaryHelixForceSpec:
        return self._spec

    @property
    def movable_sheave_rotational_inertia(self) -> float:
        """Return I_M from the resolved secondary inertia."""

        return self._movable_sheave_rotational_inertia

    def evaluate(
        self,
        state: PulleyActuationState,
    ) -> SecondaryHelixEvaluation:
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

        torsional_spring_torque = (
            self._spec.torsional_stiffness
            * (self._spec.initial_twist + theta)
        )

        local_axial_force = AffineClosureScalar(
            bias=(
                dtheta_dx * torsional_spring_torque
                + self._movable_sheave_rotational_inertia
                * dtheta_dx
                * d2theta_ds2
                * shift_speed**2
            ),
            gains=ClosureGains(
                secondary_angular_acceleration=(
                    -self._movable_sheave_rotational_inertia
                    * dtheta_dx
                ),
                shift_acceleration=(
                    self._movable_sheave_rotational_inertia
                    * dtheta_dx
                    * dtheta_ds
                ),
                secondary_torque=(
                    self._spec.movable_sheave_torque_fraction
                    * dtheta_dx
                ),
            ),
        )

        return SecondaryHelixEvaluation(
            theta=theta,
            dtheta_ds=dtheta_ds,
            d2theta_ds2=d2theta_ds2,
            local_axial_force=local_axial_force,
        )


def _require_finite(name: str, value: float) -> None:
    if not isfinite(value):
        raise ValueError(f"{name} must be finite.")


def _require_nonnegative(name: str, value: float) -> None:
    if not isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative.")
