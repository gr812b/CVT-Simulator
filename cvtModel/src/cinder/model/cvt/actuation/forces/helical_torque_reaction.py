"""Pulley-agnostic helical torque-reaction element."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from cinder.model.cvt.closure import (
    AffineClosureScalar,
    ClosureGains,
    ClosureUnknowns,
)

from ..types import (
    ActuationContribution,
    PulleyActuationContext,
    PulleyElementContribution,
)


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
    """Dynamic helix element that contributes both clamp and shaft inertia.

    Let ``theta(x)`` be the relative movable-member angle in the same signed
    rotational sense as the host shaft, with local axial ``x`` positive
    closing. The ideal helix contact converts its reacted torque through
    ``dtheta/dx``. For a movable-member inertia ``I_M`` the reacted torque is

        tau_h = f*tau_belt + k_theta(theta_pre - theta)
                - I_M [alpha + theta_ddot],

    and the local closing force is ``F_h = tau_h dtheta/dx``. The same
    ``I_M[alpha + theta_ddot]`` appears with opposite sign as a shaft inertial
    reaction, so the axial and rotational equations cannot silently diverge.
    """

    def __init__(self, *, spec: HelicalTorqueReactionSpec) -> None:
        self._spec = spec

    @property
    def spec(self) -> HelicalTorqueReactionSpec:
        return self._spec

    def evaluate(self, context: PulleyActuationContext) -> AffineClosureScalar:
        return self.evaluate_element(context).closing_force

    def evaluate_element(
        self, context: PulleyActuationContext
    ) -> PulleyElementContribution:
        terms = self._terms(context)
        return PulleyElementContribution(
            closing_force=terms.closing_force,
            shaft_torque=terms.movable_member_shaft_torque,
        )

    def inspect(
        self, context: PulleyActuationContext
    ) -> tuple[ActuationContribution, ...]:
        terms = self._terms(context)
        channels = terms.channels
        inertia = terms.movable_member_inertia
        motion_ratio = terms.motion_ratio
        kinematics = terms.kinematics
        return (
            ActuationContribution(
                key="helix_torsional_preload",
                label="Helix torsional spring",
                relation=AffineClosureScalar(bias=motion_ratio * terms.spring_torque),
            ),
            ActuationContribution(
                key="helix_shift_speed_curvature_force",
                label="Helix curvature force from shift speed",
                relation=AffineClosureScalar(
                    bias=(
                        -motion_ratio
                        * inertia
                        * kinematics.d2theta_ds2
                        * context.shift_speed**2
                    )
                ),
            ),
            ActuationContribution(
                key="helix_shaft_acceleration_force",
                label="Helix force from shaft acceleration",
                relation=AffineClosureScalar(
                    gains=ClosureGains.from_by_unknown(
                        {channels.shaft_angular_acceleration: (-motion_ratio * inertia)}
                    )
                ),
            ),
            ActuationContribution(
                key="helix_shift_acceleration_force",
                label="Helix force from shift acceleration",
                relation=AffineClosureScalar(
                    gains=ClosureGains(
                        shift_acceleration=(
                            -motion_ratio * inertia * kinematics.dtheta_ds
                        )
                    )
                ),
            ),
            ActuationContribution(
                key="helix_reacted_belt_torque_force",
                label="Helix force from movable-face belt torque",
                relation=AffineClosureScalar(
                    gains=ClosureGains.from_by_unknown(
                        {
                            channels.shaft_torque: (
                                motion_ratio * self._spec.movable_member_torque_fraction
                            )
                        }
                    )
                ),
            ),
        )

    def compressive_contact_margin(
        self,
        *,
        context: PulleyActuationContext,
        unknowns: ClosureUnknowns,
    ) -> float:
        """Return signed reacted torque on the selected helix flank."""

        return float(self._terms(context).reacted_torque.evaluate(unknowns))

    def has_compressive_contact(
        self,
        *,
        context: PulleyActuationContext,
        unknowns: ClosureUnknowns,
        tolerance: float = 0.0,
    ) -> bool:
        if not isfinite(tolerance) or tolerance < 0.0:
            raise ValueError("tolerance must be finite and non-negative.")
        return self.compressive_contact_margin(
            context=context,
            unknowns=unknowns,
        ) >= -tolerance

    def _terms(self, context: PulleyActuationContext) -> "_HelixTerms":
        coupling = context.helical_coupling
        channels = context.closure_channels
        inertia = context.movable_member_rotational_inertia
        if coupling is None:
            raise ValueError(
                "HelicalTorqueReactionForce requires a host helical_coupling."
            )
        if channels is None:
            raise ValueError(
                "HelicalTorqueReactionForce requires host closure_channels."
            )
        if inertia is None:
            raise ValueError(
                "HelicalTorqueReactionForce requires host movable-member inertia."
            )

        kinematics = coupling.kinematics
        motion_ratio = coupling.dtheta_daxial
        if not isfinite(motion_ratio) or motion_ratio == 0.0:
            raise ValueError("Helical coupling requires finite nonzero dtheta/dx.")

        spring_torque = self._spec.torsional_stiffness * (
            self._spec.initial_twist - kinematics.theta
        )
        curvature_angular_acceleration = kinematics.d2theta_ds2 * context.shift_speed**2

        reacted_torque = AffineClosureScalar(
            bias=(spring_torque - inertia * curvature_angular_acceleration),
            gains=(
                ClosureGains.from_by_unknown(
                    {
                        channels.shaft_angular_acceleration: -inertia,
                        channels.shaft_torque: self._spec.movable_member_torque_fraction,
                    }
                )
                + ClosureGains(
                    shift_acceleration=(-inertia * kinematics.dtheta_ds)
                )
            ),
        )
        closing_force = reacted_torque.scaled(motion_ratio)

        movable_member_shaft_torque = AffineClosureScalar(
            bias=(-inertia * curvature_angular_acceleration),
            gains=(
                ClosureGains.from_by_unknown(
                    {channels.shaft_angular_acceleration: -inertia}
                )
                + ClosureGains(shift_acceleration=(-inertia * kinematics.dtheta_ds))
            ),
        )
        return _HelixTerms(
            closing_force=closing_force,
            reacted_torque=reacted_torque,
            movable_member_shaft_torque=movable_member_shaft_torque,
            motion_ratio=motion_ratio,
            spring_torque=spring_torque,
            channels=channels,
            movable_member_inertia=inertia,
            kinematics=kinematics,
        )


@dataclass(frozen=True, slots=True)
class _HelixTerms:
    closing_force: AffineClosureScalar
    reacted_torque: AffineClosureScalar
    movable_member_shaft_torque: AffineClosureScalar
    motion_ratio: float
    spring_torque: float
    channels: object
    movable_member_inertia: float
    kinematics: object


def _require_finite(name: str, value: float) -> None:
    if not isfinite(value):
        raise ValueError(f"{name} must be finite.")


def _require_nonnegative(name: str, value: float) -> None:
    if not isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative.")
