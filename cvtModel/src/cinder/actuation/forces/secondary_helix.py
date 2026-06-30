"""Local inertia-inclusive torque-reactive secondary helix force law."""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose, isfinite

from cinder.closure import AffineClosureScalar, ClosureGains
from cinder.profiles import HelixShiftKinematics

from ..types import PulleyActuationState


@dataclass(frozen=True, slots=True)
class SecondaryHelixForceSpec:
    """
    Non-geometric parameters of the local secondary helix-force law.

    Helix geometry is evaluated once by ``CVTDynamicsModel.snapshot()`` and
    supplied through ``SecondaryHelixActuationState.helix_kinematics``. This
    force law therefore owns only the force-model parameters, not a separate
    ``HelixProfile`` reference.

    ``movable_sheave_rotational_inertia`` remains here because the torque
    reaching the helix must first supply movable-sheave angular acceleration
    before it can create axial clamp force.
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

    Positive ``x_s`` closes the secondary. The shared helix kinematics instead
    use the internal positive opening coordinate:

        q = -x_s.

    ``helix_kinematics`` is evaluated once by the dynamics snapshot from the
    current geometry and shift speed. The same immutable object is retained by
    the snapshot for later secondary-rotational-row assembly, guaranteeing
    that the force law and rotational row use identical ``theta``, ``H``, and
    ``H'`` values.
    """

    global_shift_speed: float
    helix_kinematics: HelixShiftKinematics

    def __post_init__(self) -> None:
        PulleyActuationState.__post_init__(self)
        _require_finite("global_shift_speed", self.global_shift_speed)

        if not isinstance(self.helix_kinematics, HelixShiftKinematics):
            raise TypeError(
                "helix_kinematics must be a HelixShiftKinematics instance."
            )

        expected_opening_travel = -self.axial_position
        if not isclose(
            self.helix_kinematics.opening_travel,
            expected_opening_travel,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ValueError(
                "helix_kinematics opening_travel must equal -axial_position."
            )


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

    The relation is affine in the closure unknowns ``tau_s``, ``alpha_s``, and
    ``s_ddot``. The helix geometry itself is deliberately supplied through the
    state rather than being re-evaluated here.
    """

    def __init__(
        self,
        *,
        spec: SecondaryHelixForceSpec,
    ) -> None:
        self._spec = spec

    @property
    def spec(self) -> SecondaryHelixForceSpec:
        return self._spec

    def evaluate(
        self,
        state: PulleyActuationState,
    ) -> AffineClosureScalar:
        """Return the local positive-closing helix-force relation."""

        if not isinstance(state, SecondaryHelixActuationState):
            raise TypeError(
                "SecondaryHelixForce requires SecondaryHelixActuationState."
            )

        kinematics = state.helix_kinematics
        torsional_spring_torque = self._spec.torsional_stiffness * (
            self._spec.initial_twist + kinematics.theta
        )
        movable_sheave_inertia = self._spec.movable_sheave_rotational_inertia

        # tau_M_to_helix = spring + kappa_M tau_s - I_M alpha_M,
        # alpha_M = alpha_s - H' s_dot^2 - H s_ddot.
        known_helix_torque = (
            torsional_spring_torque
            + movable_sheave_inertia
            * kinematics.d2theta_ds2
            * state.global_shift_speed**2
        )

        force_per_reacted_torque = kinematics.dtheta_dopening

        return AffineClosureScalar(
            bias=force_per_reacted_torque * known_helix_torque,
            gains=ClosureGains(
                secondary_angular_acceleration=(
                    -force_per_reacted_torque * movable_sheave_inertia
                ),
                shift_acceleration=(
                    force_per_reacted_torque
                    * movable_sheave_inertia
                    * kinematics.dtheta_ds
                ),
                secondary_torque=(
                    force_per_reacted_torque
                    * self._spec.movable_sheave_torque_fraction
                ),
            ),
        )


def _require_finite(name: str, value: float) -> None:
    if not isfinite(value):
        raise ValueError(f"{name} must be finite.")


def _require_nonnegative(name: str, value: float) -> None:
    if not isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative.")
