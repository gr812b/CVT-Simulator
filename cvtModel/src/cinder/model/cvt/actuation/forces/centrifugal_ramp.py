"""Centrifugal point-mass flyweight/ramp mechanism."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from cinder.model.cvt.closure import AffineClosureScalar, ClosureGains
from cinder.model.cvt.profiles.types import ScalarProfile

from ..types import (
    ActuationContribution,
    PulleyActuationContext,
    PulleyElementContribution,
    PulleyKineticMode,
)


@dataclass(frozen=True, slots=True)
class CentrifugalRampForceSpec:
    """Parameters of one equivalent point-mass flyweight/ramp mechanism.

    ``radial_displacement_profile`` supplies the compatible flyweight center-of-
    mass radius

        r_f(x) = radius_at_zero_position + Delta_r_f(x).

    The point-mass reduction has shaft-axis inertia ``J_f = m_f r_f^2``. The
    same map therefore contributes to both sides of the pulley mechanics:

        F_x = 1/2 omega^2 dJ_f/dx
            = m_f omega^2 r_f dr_f/dx,

    and

        d(J_f omega)/dt = J_f alpha + (dJ_f/dx) x_dot omega.

    The latter is returned as a shaft inertial-reaction torque, so changing the
    flyweight mechanism automatically cascades into the rotational dynamics.
    A future rigid/pivoted flyweight model can replace this point-mass element
    with one carrying explicit ``q_f(x)``, ``I_f``, and ``J_f(x)`` maps without
    changing the surrounding pulley interface.
    """

    flyweight_mass: float
    radius_at_zero_position: float
    radial_displacement_profile: ScalarProfile

    def __post_init__(self) -> None:
        _require_nonnegative(
            flyweight_mass=self.flyweight_mass,
            radius_at_zero_position=self.radius_at_zero_position,
        )


class CentrifugalRampForce:
    """Pulley-agnostic dynamic point-mass centrifugal ramp element."""

    def __init__(self, spec: CentrifugalRampForceSpec) -> None:
        self._spec = spec

    @property
    def spec(self) -> CentrifugalRampForceSpec:
        return self._spec

    def evaluate(self, context: PulleyActuationContext) -> AffineClosureScalar:
        """Return the axial relation without requiring closure channels.

        This preserves the ordinary force-law inspection/study API. The runtime
        pulley path calls :meth:`evaluate_element`, where host closure channels
        are available and the same flyweight's shaft inertia is included.
        """

        _radius, _shaft_inertia, d_inertia_dx = self._kinematics(context)
        return AffineClosureScalar(bias=(0.5 * context.shaft_speed**2 * d_inertia_dx))

    def evaluate_element(
        self, context: PulleyActuationContext
    ) -> PulleyElementContribution:
        channels = context.closure_channels
        if channels is None:
            raise ValueError(
                "CentrifugalRampForce requires host closure_channels so its "
                "flyweight inertia can enter shaft rotation."
            )

        _radius, shaft_inertia, d_inertia_dx = self._kinematics(context)

        closing_force = self.evaluate(context)

        # PulleyElementContribution.shaft_torque is an applied/reaction torque
        # in the positive shaft direction. The inertia therefore appears with
        # a minus sign in residual form: T_ext + T_elem + tau_belt = 0.
        shaft_torque = AffineClosureScalar(
            bias=(-d_inertia_dx * context.axial_speed * context.shaft_speed),
            gains=ClosureGains.from_by_unknown(
                {channels.shaft_angular_acceleration: -shaft_inertia}
            ),
        )
        return PulleyElementContribution(
            closing_force=closing_force,
            shaft_torque=shaft_torque,
        )

    def inspect(
        self, context: PulleyActuationContext
    ) -> tuple[ActuationContribution, ...]:
        return (
            ActuationContribution(
                key="centrifugal_ramp",
                label="Centrifugal ramp closing force",
                relation=self.evaluate(context),
            ),
        )

    def kinetic_modes(
        self, context: PulleyActuationContext
    ) -> tuple[PulleyKineticMode, ...]:
        """Return the point mass's shaft-axis kinetic mode."""

        _radius, shaft_inertia, _d_inertia_dx = self._kinematics(context)
        return (
            PulleyKineticMode(
                inertia=shaft_inertia,
                shaft_speed_coefficient=1.0,
            ),
        )

    def _kinematics(
        self, context: PulleyActuationContext
    ) -> tuple[float, float, float]:
        """Return ``(r_f, J_f, dJ_f/dx)`` for the frozen local state."""

        ramp = self._spec.radial_displacement_profile.evaluate(context.axial_position)
        flyweight_radius = self._spec.radius_at_zero_position + ramp.value
        if flyweight_radius <= 0.0:
            raise ValueError(
                "The flyweight radius must remain positive over the actuator "
                "operating interval."
            )
        mass = self._spec.flyweight_mass
        shaft_inertia = mass * flyweight_radius**2
        d_inertia_dx = 2.0 * mass * flyweight_radius * ramp.first_derivative
        return flyweight_radius, shaft_inertia, d_inertia_dx


def _require_nonnegative(**values: float) -> None:
    for name, value in values.items():
        if not isfinite(value) or value < 0.0:
            raise ValueError(f"{name} must be finite and non-negative.")
