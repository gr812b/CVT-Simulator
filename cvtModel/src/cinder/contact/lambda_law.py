"""Physical signed static and kinetic lambda limits for engaged contact."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import TYPE_CHECKING

from .relative_motion import ContactInterface, SlipDirection
from .utilization import ContactTractionUtilization

if TYPE_CHECKING:
    from .slip import KineticSlipSpecification


@dataclass(frozen=True, slots=True)
class SignedLambdaInterval:
    """A physically admissible signed interval for one sticking contact.

    Static traction must permit the zero-traction state, hence every physical
    interval is required to contain zero. Asymmetric intervals are permitted
    for a future direction-dependent fitted contact law.
    """

    lower: float
    upper: float

    def __post_init__(self) -> None:
        _require_finite(lower=self.lower, upper=self.upper)
        if not self.lower < self.upper:
            raise ValueError("SignedLambdaInterval must satisfy lower < upper.")
        if not self.lower <= 0.0 <= self.upper:
            raise ValueError("A static lambda interval must contain zero.")

    @classmethod
    def symmetric(cls, magnitude: float) -> "SignedLambdaInterval":
        """Build ``[-magnitude, +magnitude]``."""

        if not isfinite(magnitude) or magnitude <= 0.0:
            raise ValueError("magnitude must be finite and strictly positive.")
        return cls(lower=-magnitude, upper=magnitude)

    def contains(self, value: float) -> bool:
        """Return whether ``value`` is statically supportable."""

        return self.lower <= value <= self.upper

    def signed_margin(self, value: float) -> float:
        """Return clearance to the nearer static-capacity boundary.

        A positive margin is inside the physical static interval, zero lies on
        a boundary, and a negative margin means the required lambda exceeds
        static traction capacity.
        """

        if not isfinite(value):
            raise ValueError("value must be finite.")
        return min(value - self.lower, self.upper - value)


@dataclass(frozen=True, slots=True)
class StaticLambdaAssessment:
    """Physical static-capacity assessment for one solved lambda pair."""

    requirement: ContactTractionUtilization
    primary_margin: float
    secondary_margin: float

    @property
    def primary_admissible(self) -> bool:
        return self.primary_margin >= 0.0

    @property
    def secondary_admissible(self) -> bool:
        return self.secondary_margin >= 0.0

    @property
    def all_admissible(self) -> bool:
        return self.primary_admissible and self.secondary_admissible

    def admissible_at(self, interface: ContactInterface) -> bool:
        if interface is ContactInterface.PRIMARY:
            return self.primary_admissible
        if interface is ContactInterface.SECONDARY:
            return self.secondary_admissible
        raise ValueError(f"Unsupported contact interface: {interface!r}.")

    def margin_at(self, interface: ContactInterface) -> float:
        if interface is ContactInterface.PRIMARY:
            return self.primary_margin
        if interface is ContactInterface.SECONDARY:
            return self.secondary_margin
        raise ValueError(f"Unsupported contact interface: {interface!r}.")


@dataclass(frozen=True, slots=True)
class ContactTractionLaw:
    """Physical traction-capacity law separate from numerical lambda search.

    ``primary_static_interval`` and ``secondary_static_interval`` determine
    whether a *solved requirement* can remain stuck. They do not constrain the
    root search itself. This lets the solver expose, for example, a required
    ``lambda_p = 1.67`` even when the physical static capacity is only 0.65.

    ``*_kinetic_lambda_magnitude`` is used only after a slip branch has been
    selected. The branch direction determines the sign.
    """

    primary_static_interval: SignedLambdaInterval
    secondary_static_interval: SignedLambdaInterval
    primary_kinetic_lambda_magnitude: float
    secondary_kinetic_lambda_magnitude: float

    def __post_init__(self) -> None:
        if not isinstance(self.primary_static_interval, SignedLambdaInterval):
            raise TypeError("primary_static_interval must be a SignedLambdaInterval.")
        if not isinstance(self.secondary_static_interval, SignedLambdaInterval):
            raise TypeError("secondary_static_interval must be a SignedLambdaInterval.")
        _require_finite_positive(
            primary_kinetic_lambda_magnitude=self.primary_kinetic_lambda_magnitude,
            secondary_kinetic_lambda_magnitude=self.secondary_kinetic_lambda_magnitude,
        )

    @classmethod
    def symmetric(
        cls,
        *,
        primary_static_lambda_limit: float,
        secondary_static_lambda_limit: float,
        primary_kinetic_lambda_magnitude: float,
        secondary_kinetic_lambda_magnitude: float,
    ) -> "ContactTractionLaw":
        """Build a direction-symmetric physical contact law."""

        return cls(
            primary_static_interval=SignedLambdaInterval.symmetric(
                primary_static_lambda_limit
            ),
            secondary_static_interval=SignedLambdaInterval.symmetric(
                secondary_static_lambda_limit
            ),
            primary_kinetic_lambda_magnitude=primary_kinetic_lambda_magnitude,
            secondary_kinetic_lambda_magnitude=secondary_kinetic_lambda_magnitude,
        )

    def static_interval_at(self, interface: ContactInterface) -> SignedLambdaInterval:
        """Return the physical static-capacity interval at one interface."""

        if interface is ContactInterface.PRIMARY:
            return self.primary_static_interval
        if interface is ContactInterface.SECONDARY:
            return self.secondary_static_interval
        raise ValueError(f"Unsupported contact interface: {interface!r}.")

    def static_contains_at(self, interface: ContactInterface, value: float) -> bool:
        """Return whether one required lambda lies within static capacity."""

        return self.static_interval_at(interface).contains(value)

    def static_margin_at(self, interface: ContactInterface, value: float) -> float:
        """Return physical static-capacity clearance at one interface."""

        return self.static_interval_at(interface).signed_margin(value)

    def assess_static_requirement(
        self,
        requirement: ContactTractionUtilization,
    ) -> StaticLambdaAssessment:
        """Compare a solved lambda requirement against both static limits."""

        return StaticLambdaAssessment(
            requirement=requirement,
            primary_margin=self.static_margin_at(
                ContactInterface.PRIMARY,
                requirement.primary_lambda,
            ),
            secondary_margin=self.static_margin_at(
                ContactInterface.SECONDARY,
                requirement.secondary_lambda,
            ),
        )

    def kinetic_lambda_magnitude_at(self, interface: ContactInterface) -> float:
        """Return the positive kinetic lambda magnitude for one interface."""

        if interface is ContactInterface.PRIMARY:
            return self.primary_kinetic_lambda_magnitude
        if interface is ContactInterface.SECONDARY:
            return self.secondary_kinetic_lambda_magnitude
        raise ValueError(f"Unsupported contact interface: {interface!r}.")

    def kinetic_slip_specification(
        self,
        *,
        interface: ContactInterface,
        direction: SlipDirection,
    ) -> "KineticSlipSpecification":
        """Build the signed-kinetic specification selected by a slip regime."""

        from .slip import KineticSlipSpecification

        return KineticSlipSpecification(
            interface=interface,
            direction=direction,
            kinetic_lambda_magnitude=self.kinetic_lambda_magnitude_at(interface),
        )


def _require_finite(**values: float) -> None:
    for name, value in values.items():
        if not isfinite(value):
            raise ValueError(f"{name} must be finite.")


def _require_finite_positive(**values: float) -> None:
    _require_finite(**values)
    for name, value in values.items():
        if value <= 0.0:
            raise ValueError(f"{name} must be strictly positive.")
