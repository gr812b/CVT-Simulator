"""Centrifugal flyweight load projected through a physical radial ramp."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from cinder.closure import AffineClosureScalar
from cinder.profiles.types import ScalarProfile

from ..types import PulleyActuationState


@dataclass(frozen=True, slots=True)
class CentrifugalRampForceSpec:
    """Parameters of one equivalent flyweight/ramp mechanism.

    ``radial_displacement_profile`` is the physical radial displacement
    relative to local x = 0:

        r_f(x) = radius_at_zero_position + Delta_r_f(x).

    The local axial force is:

        F = m_f omega^2 r_f(x) d(Delta_r_f)/dx.
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
    """Known centrifugal axial-force contribution of a primary ramp."""

    def __init__(self, spec: CentrifugalRampForceSpec) -> None:
        self._spec = spec

    @property
    def spec(self) -> CentrifugalRampForceSpec:
        return self._spec

    def evaluate(self, state: PulleyActuationState) -> AffineClosureScalar:
        ramp = self._spec.radial_displacement_profile.evaluate(
            state.axial_position
        )
        flyweight_radius = self._spec.radius_at_zero_position + ramp.value

        if flyweight_radius <= 0.0:
            raise ValueError(
                "The flyweight radius must remain positive over the "
                "actuator operating interval."
            )

        axial_force = (
            self._spec.flyweight_mass
            * state.shaft_speed**2
            * flyweight_radius
            * ramp.first_derivative
        )

        return AffineClosureScalar(bias=axial_force)


def _require_nonnegative(**values: float) -> None:
    for name, value in values.items():
        if not isfinite(value) or value < 0.0:
            raise ValueError(f"{name} must be finite and non-negative.")
