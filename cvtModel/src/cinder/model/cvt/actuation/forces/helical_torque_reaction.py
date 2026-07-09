"""Helical torque-reaction pulley element.

The helix is implemented as a pulley-mounted affine element. It contributes a
local closing force and the movable member's shaft-torque inertia. The CVT
balance rows do not special-case where the helix is mounted.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from cinder.model.cvt.closure import AffineClosureScalar, ClosureGains, ClosureUnknown

from ..types import ActuationContribution, PulleyActuationContext, PulleyElementContribution


@dataclass(frozen=True, slots=True)
class HelicalTorqueReactionSpec:
    """Non-geometric constants of a helical torque reaction."""

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
    """Pulley-agnostic helix element.

    The closing force is positive in the host pulley's closing direction. The
    shaft torque is positive in the host shaft's positive rotation direction.
    """

    def __init__(self, *, spec: HelicalTorqueReactionSpec) -> None:
        self._spec = spec

    @property
    def spec(self) -> HelicalTorqueReactionSpec:
        return self._spec

    def evaluate(self, context: PulleyActuationContext) -> AffineClosureScalar:
        return self.evaluate_element(context).closing_force

    def evaluate_element(self, context: PulleyActuationContext) -> PulleyElementContribution:
        terms = self._terms(context)
        return PulleyElementContribution(
            closing_force=terms.closing_force,
            shaft_torque=terms.movable_member_shaft_torque,
        )

    def inspect(self, context: PulleyActuationContext) -> tuple[ActuationContribution, ...]:
        terms = self._terms(context)
        channels = terms.channels
        inertia = terms.movable_member_inertia
        kinematics = terms.kinematics
        force_per_reacted_torque = terms.force_per_reacted_torque
        return (
            ActuationContribution(
                key="helix_torsional_preload",
                label="Helix torsional preload",
                relation=AffineClosureScalar(
                    bias=force_per_reacted_torque * terms.spring_torque
                ),
            ),
            ActuationContribution(
                key="helix_shift_speed_curvature_force",
                label="Helix curvature force from shift speed",
                relation=AffineClosureScalar(
                    bias=force_per_reacted_torque * terms.curvature_torque
                ),
            ),
            ActuationContribution(
                key="helix_shaft_acceleration_force",
                label="Helix force from shaft acceleration",
                relation=AffineClosureScalar(
                    gains=ClosureGains.from_by_unknown(
                        {
                            channels.shaft_angular_acceleration: -force_per_reacted_torque
                            * inertia
                        }
                    )
                ),
            ),
            ActuationContribution(
                key="helix_shift_acceleration_force",
                label="Helix force from shift acceleration",
                relation=AffineClosureScalar(
                    gains=ClosureGains.from_by_unknown(
                        {
                            ClosureUnknown.SHIFT_ACCELERATION: (
                                force_per_reacted_torque
                                * inertia
                                * kinematics.dtheta_ds
                            )
                        }
                    )
                ),
            ),
            ActuationContribution(
                key="helix_reacted_shaft_torque_force",
                label="Helix force from reacted shaft torque",
                relation=AffineClosureScalar(
                    gains=ClosureGains.from_by_unknown(
                        {
                            channels.shaft_torque: (
                                force_per_reacted_torque
                                * self._spec.movable_member_torque_fraction
                            )
                        }
                    )
                ),
            ),
        )

    def _terms(self, context: PulleyActuationContext) -> "_HelixTerms":
        coupling = context.helical_coupling
        channels = context.closure_channels
        inertia = context.movable_member_rotational_inertia
        if coupling is None:
            raise ValueError("HelicalTorqueReactionForce requires a host helical_coupling.")
        if channels is None:
            raise ValueError("HelicalTorqueReactionForce requires host closure_channels.")
        if inertia is None:
            raise ValueError("HelicalTorqueReactionForce requires host movable-member inertia.")

        kinematics = coupling.kinematics
        spring_torque = self._spec.torsional_stiffness * (
            self._spec.initial_twist + kinematics.theta
        )
        curvature_torque = inertia * kinematics.d2theta_ds2 * context.shift_speed**2
        force_per_reacted_torque = kinematics.dtheta_dopening
        closing_force = AffineClosureScalar(
            bias=force_per_reacted_torque * (spring_torque + curvature_torque),
            gains=ClosureGains.from_by_unknown(
                {
                    channels.shaft_angular_acceleration: -force_per_reacted_torque * inertia,
                    ClosureUnknown.SHIFT_ACCELERATION: (
                        force_per_reacted_torque * inertia * kinematics.dtheta_ds
                    ),
                    channels.shaft_torque: (
                        force_per_reacted_torque * self._spec.movable_member_torque_fraction
                    ),
                }
            ),
        )
        movable_member_shaft_torque = AffineClosureScalar(
            bias=inertia * kinematics.d2theta_ds2 * context.shift_speed**2,
            gains=ClosureGains.from_by_unknown(
                {
                    channels.shaft_angular_acceleration: -inertia,
                    ClosureUnknown.SHIFT_ACCELERATION: inertia * kinematics.dtheta_ds,
                }
            ),
        )
        return _HelixTerms(
            closing_force=closing_force,
            movable_member_shaft_torque=movable_member_shaft_torque,
            force_per_reacted_torque=force_per_reacted_torque,
            spring_torque=spring_torque,
            curvature_torque=curvature_torque,
            channels=channels,
            movable_member_inertia=inertia,
            kinematics=kinematics,
        )


@dataclass(frozen=True, slots=True)
class _HelixTerms:
    closing_force: AffineClosureScalar
    movable_member_shaft_torque: AffineClosureScalar
    force_per_reacted_torque: float
    spring_torque: float
    curvature_torque: float
    channels: object
    movable_member_inertia: float
    kinematics: object


def _require_finite(name: str, value: float) -> None:
    if not isfinite(value):
        raise ValueError(f"{name} must be finite.")


def _require_nonnegative(name: str, value: float) -> None:
    if not isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative.")
