"""Dynamic force law for the fixed-pivot flyweight mechanism."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from cinder.model.cvt.closure import (
    AffineClosureScalar,
    ClosureGains,
    ClosureUnknowns,
)

from ..fixed_pivot_flyweight import FixedPivotFlyweightMap
from ..types import (
    ActuationContribution,
    PulleyActuationContext,
    PulleyElementContribution,
    PulleyKineticMode,
)


@dataclass(frozen=True, slots=True)
class FixedPivotFlyweightForceSpec:
    """The mechanism-specific ``q_f(x), J_f(x), I_f`` map."""

    mechanism_map: FixedPivotFlyweightMap

    def __post_init__(self) -> None:
        if not isinstance(self.mechanism_map, FixedPivotFlyweightMap):
            raise TypeError("mechanism_map must implement FixedPivotFlyweightMap.")


class FixedPivotFlyweightForce:
    """Pulley-mounted fixed-pivot flyweight force and shaft coupling.

    For local pulley-closing coordinate ``x`` this element supplies

        F = 1/2 omega^2 J'(x)
            - I q'(x)^2 x_ddot
            - I q'(x) q''(x) x_dot^2,

    and the owning shaft receives the inertial reaction

        -J(x) alpha - J'(x) x_dot omega.

    The host context maps ``x_ddot`` into the shared shift-acceleration column,
    so the same class can be mounted on either pulley without named branches.
    """

    def __init__(self, spec: FixedPivotFlyweightForceSpec) -> None:
        if not isinstance(spec, FixedPivotFlyweightForceSpec):
            raise TypeError("spec must be a FixedPivotFlyweightForceSpec.")
        self._spec = spec

    @property
    def spec(self) -> FixedPivotFlyweightForceSpec:
        return self._spec

    def evaluate(self, context: PulleyActuationContext) -> AffineClosureScalar:
        axial_acceleration = _require_axial_acceleration(context)
        sample = self._spec.mechanism_map.evaluate(context.axial_position)
        pivot_inertia = sample.pivot_inertia
        motion_ratio = sample.angle_gradient
        known_force = (
            0.5 * context.shaft_speed**2 * sample.shaft_inertia_gradient
            - pivot_inertia
            * motion_ratio
            * sample.angle_curvature
            * context.axial_speed**2
        )
        return AffineClosureScalar.constant(known_force) + (
            axial_acceleration.scaled(
                -pivot_inertia * motion_ratio**2
            )
        )

    def evaluate_element(
        self, context: PulleyActuationContext
    ) -> PulleyElementContribution:
        channels = context.closure_channels
        if channels is None:
            raise ValueError(
                "FixedPivotFlyweightForce requires host closure_channels so its "
                "shaft inertia can enter the owning rotational balance."
            )
        sample = self._spec.mechanism_map.evaluate(context.axial_position)
        shaft_torque = AffineClosureScalar(
            bias=(
                -sample.shaft_inertia_gradient
                * context.axial_speed
                * context.shaft_speed
            ),
            gains=ClosureGains.from_by_unknown(
                {
                    channels.shaft_angular_acceleration: (
                        -sample.shaft_inertia
                    )
                }
            ),
        )
        return PulleyElementContribution(
            closing_force=self.evaluate(context),
            shaft_torque=shaft_torque,
        )

    def kinetic_modes(
        self, context: PulleyActuationContext
    ) -> tuple[PulleyKineticMode, ...]:
        """Return shaft rotation and relative pivot rotation as separate modes."""

        sample = self._spec.mechanism_map.evaluate(context.axial_position)
        return (
            PulleyKineticMode(
                inertia=sample.shaft_inertia,
                shaft_speed_coefficient=1.0,
            ),
            PulleyKineticMode(
                inertia=sample.pivot_inertia,
                axial_speed_coefficient=sample.angle_gradient,
            ),
        )

    def inspect(
        self, context: PulleyActuationContext
    ) -> tuple[ActuationContribution, ...]:
        axial_acceleration = _require_axial_acceleration(context)
        sample = self._spec.mechanism_map.evaluate(context.axial_position)
        pivot_inertia = sample.pivot_inertia
        motion_ratio = sample.angle_gradient
        return (
            ActuationContribution(
                key="fixed_pivot_flyweight_centrifugal",
                label="Fixed-pivot flyweight centrifugal drive",
                relation=AffineClosureScalar.constant(
                    0.5
                    * context.shaft_speed**2
                    * sample.shaft_inertia_gradient
                ),
            ),
            ActuationContribution(
                key="fixed_pivot_flyweight_axial_inertia",
                label="Fixed-pivot flyweight reflected axial inertia",
                relation=axial_acceleration.scaled(
                    -pivot_inertia * motion_ratio**2
                ),
            ),
            ActuationContribution(
                key="fixed_pivot_flyweight_motion_ratio_curvature",
                label="Fixed-pivot flyweight motion-ratio curvature",
                relation=AffineClosureScalar.constant(
                    -pivot_inertia
                    * motion_ratio
                    * sample.angle_curvature
                    * context.axial_speed**2
                ),
            ),
        )

    def has_compressive_contact(
        self,
        *,
        context: PulleyActuationContext,
        unknowns: ClosureUnknowns,
        tolerance: float = 0.0,
    ) -> bool:
        """Return whether the solved ramp force is compressive.

        The affine closure is intentionally not clipped with ``max(0, F)``;
        doing so would hide a change of mechanism topology inside a smooth RHS.
        Callers can use this check as a diagnostic or event admissibility test.
        """

        if not isfinite(tolerance) or tolerance < 0.0:
            raise ValueError("tolerance must be finite and non-negative.")
        return self.evaluate(context).evaluate(unknowns) >= -tolerance


def _require_axial_acceleration(
    context: PulleyActuationContext,
) -> AffineClosureScalar:
    relation = context.axial_acceleration
    if relation is None:
        raise ValueError(
            "FixedPivotFlyweightForce requires the host local axial-acceleration "
            "relation so pivot inertia can enter the shared closure solve."
        )
    return relation
