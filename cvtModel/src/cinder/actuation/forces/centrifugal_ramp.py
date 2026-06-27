from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from cinder.profiles import ScalarProfile

from ..types import PulleyActuationResult, PulleyActuationState


@dataclass(frozen=True, slots=True)
class CentrifugalRampForceSpec:
    """
    Parameters for one centrifugal flyweight-ramp mechanism.

    ``radial_displacement_profile`` represents the flyweight radial movement
    relative to its local x = 0 condition:

        Delta_r_f(x)

    so the physical flyweight radius is:

        r_f(x) = radius_at_zero_position + Delta_r_f(x).

    The resulting local axial force is:

        F = m_f * omega^2 * r_f(x) * d(Delta_r_f)/dx.

    The returned force is signed in the local pulley convention: positive
    closes the pulley, negative opens it.
    """

    flyweight_mass: float
    radius_at_zero_position: float
    radial_displacement_profile: ScalarProfile

    def __post_init__(self) -> None:
        _require_positive(
            flyweight_mass=self.flyweight_mass,
            radius_at_zero_position=self.radius_at_zero_position,
        )


class CentrifugalRampForce:
    """Centrifugal flyweight load projected through a radial ramp profile."""

    def __init__(self, spec: CentrifugalRampForceSpec) -> None:
        self._spec = spec

    @property
    def spec(self) -> CentrifugalRampForceSpec:
        return self._spec

    def force_relation(
        self,
        state: PulleyActuationState,
    ) -> PulleyActuationResult:
        profile = self._spec.radial_displacement_profile.evaluate(
            state.axial_position
        )

        flyweight_radius = (
            self._spec.radius_at_zero_position + profile.value
        )
        if flyweight_radius <= 0.0:
            raise ValueError(
                "The flyweight radius must remain positive over the "
                "actuator's operating interval."
            )

        axial_force = (
            self._spec.flyweight_mass
            * state.shaft_speed**2
            * flyweight_radius
            * profile.first_derivative
        )

        return PulleyActuationResult(
            bias_force=axial_force,
            torque_gain=0.0,
        )


def _require_positive(**values: float) -> None:
    for name, value in values.items():
        if not isfinite(value) or value <= 0.0:
            raise ValueError(f"{name} must be finite and positive.")
