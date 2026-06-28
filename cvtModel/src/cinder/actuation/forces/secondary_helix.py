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

    The physical helix profile is created and retained independently at
    system construction. It is passed to this local clamping law and later
    directly to secondary helix dynamics.

    Movable-sheave rotational inertia I_M is deliberately absent. Its
    acceleration coupling belongs only to the future secondary helix
    dynamics mechanism, where it contributes once to the rotational and
    generalized-shift rows.
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

        if (
            not isfinite(self.movable_sheave_torque_fraction)
            or not 0.0
            <= self.movable_sheave_torque_fraction
            <= 1.0
        ):
            raise ValueError(
                "movable_sheave_torque_fraction must lie in [0, 1]."
            )


class SecondaryHelixForce:
    """
    One ordinary local axial-force law for ``PulleyActuator``.

    Let theta = theta(x_s), where x_s is the secondary's local closing
    coordinate. The helix converts the signed torsional-spring torque and
    the selected movable-sheave share of transmitted secondary torque into
    local axial force through dtheta/dx_s.

    It intentionally contains no I_M, alpha_s, or s_ddot term. Those are
    kinematic/inertial effects, not clamping-law effects.
    """

    def __init__(
        self,
        *,
        spec: SecondaryHelixForceSpec,
        helix_profile: HelixProfile,
    ) -> None:
        self._spec = spec
        self._helix_profile = helix_profile

    @property
    def spec(self) -> SecondaryHelixForceSpec:
        return self._spec

    @property
    def helix_profile(self) -> HelixProfile:
        """Return the shared physical helix geometry."""

        return self._helix_profile

    def evaluate(
        self,
        state: PulleyActuationState,
    ) -> AffineClosureScalar:
        """Return F_xs as an affine relation in secondary torque."""

        sample = self._helix_profile.evaluate(state.axial_position)

        torsional_spring_torque = (
            self._spec.torsional_stiffness
            * (self._spec.initial_twist + sample.theta)
        )

        return AffineClosureScalar(
            bias=sample.dtheta_dx * torsional_spring_torque,
            gains=ClosureGains(
                secondary_torque=(
                    self._spec.movable_sheave_torque_fraction
                    * sample.dtheta_dx
                ),
            ),
        )


def _require_finite(name: str, value: float) -> None:
    if not isfinite(value):
        raise ValueError(f"{name} must be finite.")


def _require_nonnegative(name: str, value: float) -> None:
    if not isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative.")
