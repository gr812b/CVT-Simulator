"""Generic inertia-inclusive helical torque-reaction force law."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from cinder.model.cvt.closure import AffineClosureScalar, ClosureGains, ClosureUnknown

from ..types import ActuationContribution, PulleyActuationContext


@dataclass(frozen=True, slots=True)
class HelicalTorqueReactionSpec:
    """Intrinsic non-geometric constants of a helical torque reaction."""

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
    """A pulley-agnostic affine force law supplied by a host helical coupling."""

    def __init__(self, *, spec: HelicalTorqueReactionSpec) -> None:
        self._spec = spec

    @property
    def spec(self) -> HelicalTorqueReactionSpec:
        return self._spec

    def evaluate(self, context: PulleyActuationContext) -> AffineClosureScalar:
        return self._terms(context)[0]

    def inspect(self, context: PulleyActuationContext) -> tuple[ActuationContribution, ...]:
        """Expose the physical helix decomposition outside the RHS path."""

        _, force_per_reacted_torque, spring_torque, curvature_torque, channels, inertia, kinematics = (
            self._terms(context, retain_components=True)
        )
        return (
            ActuationContribution(
                key="helix_torsional_preload",
                label="Helix torsional preload",
                relation=AffineClosureScalar(
                    bias=force_per_reacted_torque * spring_torque
                ),
            ),
            ActuationContribution(
                key="helix_shift_speed_curvature",
                label="Helix shift-speed curvature inertia",
                relation=AffineClosureScalar(
                    bias=force_per_reacted_torque * curvature_torque
                ),
            ),
            ActuationContribution(
                key="helix_shaft_acceleration_inertia",
                label="Helix shaft-acceleration inertia",
                relation=AffineClosureScalar(
                    gains=ClosureGains.from_by_unknown(
                        {channels.shaft_angular_acceleration: -force_per_reacted_torque * inertia}
                    )
                ),
            ),
            ActuationContribution(
                key="helix_shift_acceleration_inertia",
                label="Helix shift-acceleration inertia",
                relation=AffineClosureScalar(
                    gains=ClosureGains.from_by_unknown(
                        {
                            ClosureUnknown.SHIFT_ACCELERATION: (
                                force_per_reacted_torque * inertia * kinematics.dtheta_ds
                            )
                        }
                    )
                ),
            ),
            ActuationContribution(
                key="helix_reacted_shaft_torque",
                label="Helix reacted shaft torque",
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

    def _terms(
        self,
        context: PulleyActuationContext,
        *,
        retain_components: bool = False,
    ):
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
        spring_torque = self._spec.torsional_stiffness * (
            self._spec.initial_twist + kinematics.theta
        )
        curvature_torque = inertia * kinematics.d2theta_ds2 * context.shift_speed**2
        force_per_reacted_torque = (
            -coupling.opening_per_axial_position * kinematics.dtheta_dopening
        )
        gains = ClosureGains.from_by_unknown(
            {
                channels.shaft_angular_acceleration: -force_per_reacted_torque * inertia,
                ClosureUnknown.SHIFT_ACCELERATION: (
                    force_per_reacted_torque * inertia * kinematics.dtheta_ds
                ),
                channels.shaft_torque: (
                    force_per_reacted_torque
                    * self._spec.movable_member_torque_fraction
                ),
            }
        )
        relation = AffineClosureScalar(
            bias=force_per_reacted_torque * (spring_torque + curvature_torque),
            gains=gains,
        )
        if retain_components:
            return (
                relation,
                force_per_reacted_torque,
                spring_torque,
                curvature_torque,
                channels,
                inertia,
                kinematics,
            )
        return (relation,)


def _require_finite(name: str, value: float) -> None:
    if not isfinite(value):
        raise ValueError(f"{name} must be finite.")


def _require_nonnegative(name: str, value: float) -> None:
    if not isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative.")
