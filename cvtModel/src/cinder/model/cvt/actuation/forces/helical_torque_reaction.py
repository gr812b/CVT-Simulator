"""Generic inertia-inclusive helical torque-reaction force law.

This force law is independent of whether it is mounted on the input or output
pulley.  The host pulley supplies the closure columns for its shaft torque and
shaft acceleration through :class:`PulleyClosureChannels`.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose, isfinite

from cinder.model.cvt.closure import AffineClosureScalar, ClosureGains, ClosureUnknown
from cinder.model.cvt.profiles import HelixShiftKinematics

from ..types import HelicalTorqueReactionState, PulleyActuationState


@dataclass(frozen=True, slots=True)
class HelicalTorqueReactionSpec:
    """Non-geometric constants for a mounted helical torque reaction.

    The host pulley supplies movable-member inertia through
    :class:`HelicalTorqueReactionState`; this specification contains only
    intrinsic helical-actuation parameters.
    """

    torsional_stiffness: float
    initial_twist: float
    movable_member_torque_fraction: float = 0.5

    def __post_init__(self) -> None:
        _require_nonnegative("torsional_stiffness", self.torsional_stiffness)
        _require_finite("initial_twist", self.initial_twist)
        if (
            not isfinite(self.movable_member_torque_fraction)
            or not 0.0 <= self.movable_member_torque_fraction <= 1.0
        ):
            raise ValueError("movable_member_torque_fraction must lie in [0, 1].")


class HelicalTorqueReactionForce:
    """Affine local clamp-force law produced by a mounted helical coupling.

    The law evaluates to a local positive-closing axial force.  It obtains the
    host shaft's closure columns from the state, so no force-law class is tied
    to a particular pulley name.
    """

    def __init__(self, *, spec: HelicalTorqueReactionSpec) -> None:
        self._spec = spec

    @property
    def spec(self) -> HelicalTorqueReactionSpec:
        return self._spec

    def evaluate(self, state: PulleyActuationState) -> AffineClosureScalar:
        if not isinstance(state, HelicalTorqueReactionState):
            raise TypeError(
                "HelicalTorqueReactionForce requires HelicalTorqueReactionState."
            )

        kinematics = state.helix_kinematics
        inertia = _require_host_movable_member_inertia(state)
        spring_torque = self._spec.torsional_stiffness * (
            self._spec.initial_twist + kinematics.theta
        )

        # tau_member_to_helix = spring + kappa*tau_shaft - I*alpha_member
        # alpha_member = alpha_shaft - H' s_dot^2 - H s_ddot.
        known_reacted_torque = (
            spring_torque
            + inertia * kinematics.d2theta_ds2 * state.global_shift_speed**2
        )

        # dtheta/dq maps reacted torque to a positive-closing force when q is
        # positive opening travel.  ``opening_per_axial_position`` carries the
        # host-pulley coordinate convention; -1 reproduces the present output
        # pulley relation q = -x.
        force_per_reacted_torque = (
            -state.opening_per_axial_position * kinematics.dtheta_dopening
        )
        gains = ClosureGains.from_by_unknown(
            {
                state.closure_channels.shaft_angular_acceleration: (
                    -force_per_reacted_torque * inertia
                ),
                ClosureUnknown.SHIFT_ACCELERATION: (
                    force_per_reacted_torque * inertia * kinematics.dtheta_ds
                ),
                state.closure_channels.shaft_torque: (
                    force_per_reacted_torque
                    * self._spec.movable_member_torque_fraction
                ),
            }
        )
        return AffineClosureScalar(
            bias=force_per_reacted_torque * known_reacted_torque,
            gains=gains,
        )


def _require_host_movable_member_inertia(
    state: HelicalTorqueReactionState,
) -> float:
    if state.movable_member_inertia is None:
        raise ValueError(
            "HelicalTorqueReactionForce requires host-pulley movable-member inertia "
            "in HelicalTorqueReactionState."
        )
    return state.movable_member_inertia


def _require_finite(name: str, value: float) -> None:
    if not isfinite(value):
        raise ValueError(f"{name} must be finite.")


def _require_nonnegative(name: str, value: float) -> None:
    if not isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative.")
