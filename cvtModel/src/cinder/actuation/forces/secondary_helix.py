"""Local inertia-inclusive torque-reactive secondary helix force law."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from cinder.closure import AffineClosureScalar, ClosureGains
from cinder.profiles.helix import HelixProfile

from ..types import PulleyActuationState


@dataclass(frozen=True, slots=True)
class SecondaryHelixForceSpec:
    """
    Non-geometric parameters of the local secondary helix-force law.

    The shared ``HelixProfile`` is retained outside this specification because
    it is physical geometry needed both here and by the later rotational-row
    assembly. ``movable_sheave_rotational_inertia`` is retained here because
    the torque reaching the helix must first supply movable-sheave angular
    acceleration before it can create axial clamp force.
    """

    torsional_stiffness: float
    initial_twist: float
    movable_sheave_rotational_inertia: float
    movable_sheave_torque_fraction: float = 0.5

    def __post_init__(self) -> None:
        _require_nonnegative(
            "torsional_stiffness",
            self.torsional_stiffness,
        )
        _require_finite("initial_twist", self.initial_twist)
        _require_nonnegative(
            "movable_sheave_rotational_inertia",
            self.movable_sheave_rotational_inertia,
        )

        if (
            not isfinite(self.movable_sheave_torque_fraction)
            or not 0.0 <= self.movable_sheave_torque_fraction <= 1.0
        ):
            raise ValueError("movable_sheave_torque_fraction must lie in [0, 1].")


@dataclass(frozen=True, slots=True)
class SecondaryHelixActuationState(PulleyActuationState):
    """
    Secondary-only known quantities for the inertia-inclusive helix relation.

    The inherited coordinate is the public local secondary closing coordinate:

        axial_position = x_s.

    Positive ``x_s`` closes the secondary. The helix instead uses its internal
    positive opening coordinate:

        q = -x_s.

    Geometry supplies the map from common global shift ``s`` to ``x_s``:

        dx_s/ds,
        d2x_s/ds2.

    With q' = -dx_s/ds and q'' = -d2x_s/ds2, the helix kinematics are:

        H  = dtheta/ds
           = (dtheta/dq) q',

        H' = d2theta/ds2
           = (d2theta/dq2) q'^2 + (dtheta/dq) q''.

    Together with ``global_shift_speed = s_dot``:

        alpha_M = alpha_s - H' s_dot^2 - H s_ddot.

    The class remains a ``PulleyActuationState`` subclass so a normal
    ``PulleyActuator`` still aggregates the axial spring and helix force.
    """

    global_shift_speed: float
    local_axial_coordinate_slope: float
    local_axial_coordinate_curvature: float

    def __post_init__(self) -> None:
        PulleyActuationState.__post_init__(self)

        for name, value in (
            ("global_shift_speed", self.global_shift_speed),
            (
                "local_axial_coordinate_slope",
                self.local_axial_coordinate_slope,
            ),
            (
                "local_axial_coordinate_curvature",
                self.local_axial_coordinate_curvature,
            ),
        ):
            _require_finite(name, value)


class SecondaryHelixForce:
    """
    One ordinary local axial-force law for ``PulleyActuator``.

    Let q = -x_s be positive secondary opening travel, and let theta(q) be
    positive spring-winding relative rotation. The reacted movable-sheave-to-
    helix torque is:

        tau_M_to_helix
          = k_theta (theta_0 + theta)
          + kappa_M tau_s
          - I_M alpha_M,

    with:

        alpha_M = alpha_s - H' s_dot^2 - H s_ddot,
        H        = dtheta/ds,
        H'       = d2theta/ds2.

    Because the actuator convention is positive local force = secondary
    closing/clamping, the virtual-work conversion uses the positive opening
    slope:

        F_helix = (dtheta/dq) tau_M_to_helix.

    Thus ordinary positive forward torque has gain:

        dF_helix/dtau_s = kappa_M dtheta/dq > 0.

    The relation is affine in the closure unknowns ``tau_s``, ``alpha_s``,
    and ``s_ddot``. The secondary itself remains a normal
    ``PulleyActuator``.
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
        """Return the shared physical secondary helix geometry."""

        return self._helix_profile

    def evaluate(
        self,
        state: PulleyActuationState,
    ) -> AffineClosureScalar:
        """Return the local positive-closing helix-force relation."""

        if not isinstance(state, SecondaryHelixActuationState):
            raise TypeError(
                "SecondaryHelixForce requires SecondaryHelixActuationState."
            )

        opening_travel = -state.axial_position
        sample = self._helix_profile.evaluate(opening_travel)

        opening_slope = -state.local_axial_coordinate_slope
        opening_curvature = -state.local_axial_coordinate_curvature

        theta_rate_per_shift = sample.dtheta_dopening * opening_slope
        theta_acceleration_per_shift_squared = (
            sample.d2theta_dopening2 * opening_slope**2
            + sample.dtheta_dopening * opening_curvature
        )

        torsional_spring_torque = self._spec.torsional_stiffness * (
            self._spec.initial_twist + sample.theta
        )
        movable_sheave_inertia = self._spec.movable_sheave_rotational_inertia

        # tau_M_to_helix = spring + kappa_M tau_s - I_M alpha_M,
        # alpha_M = alpha_s - H' s_dot^2 - H s_ddot.
        known_helix_torque = (
            torsional_spring_torque
            + movable_sheave_inertia
            * theta_acceleration_per_shift_squared
            * state.global_shift_speed**2
        )

        force_per_reacted_torque = sample.dtheta_dopening

        return AffineClosureScalar(
            bias=force_per_reacted_torque * known_helix_torque,
            gains=ClosureGains(
                secondary_angular_acceleration=(
                    -force_per_reacted_torque * movable_sheave_inertia
                ),
                shift_acceleration=(
                    force_per_reacted_torque
                    * movable_sheave_inertia
                    * theta_rate_per_shift
                ),
                secondary_torque=(
                    force_per_reacted_torque * self._spec.movable_sheave_torque_fraction
                ),
            ),
        )


def _require_finite(name: str, value: float) -> None:
    if not isfinite(value):
        raise ValueError(f"{name} must be finite.")


def _require_nonnegative(name: str, value: float) -> None:
    if not isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative.")
