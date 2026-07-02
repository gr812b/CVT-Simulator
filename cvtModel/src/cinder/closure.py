"""Canonical instantaneous-closure coordinates for CINDER.

The coupled CVT closure solve uses one named eight-column basis. Components
that contribute a scalar relation use this module rather than keeping their
own tuple order or column indices.

    scalar = bias + gains dot unknowns

A :class:`ClosureEquation` wraps one such affine residual. The generic trial
solver converts the residual form

    bias + gains dot unknowns = 0

to the matrix form

    A unknowns = b,

using ``A = gains`` and ``b = -bias``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from math import isfinite
from typing import Iterable, Iterator


class ClosureUnknown(IntEnum):
    """Canonical column order of the instantaneous CVT closure solve."""

    PRIMARY_ANGULAR_ACCELERATION = 0
    SECONDARY_ANGULAR_ACCELERATION = 1
    BELT_ACCELERATION = 2
    SHIFT_ACCELERATION = 3
    PRIMARY_TORQUE = 4
    SECONDARY_TORQUE = 5
    PRIMARY_NORMAL_RESULTANT = 6
    SECONDARY_NORMAL_RESULTANT = 7


CLOSURE_UNKNOWN_COUNT = len(ClosureUnknown)


@dataclass(frozen=True, slots=True)
class ClosureUnknowns:
    """Solved instantaneous values in the canonical closure basis.

    The field order is deliberately visible and named. Matrix assembly should
    use :meth:`as_tuple` when it needs the corresponding ordered NumPy row or
    column.
    """

    primary_angular_acceleration: float = 0.0
    secondary_angular_acceleration: float = 0.0
    belt_acceleration: float = 0.0
    shift_acceleration: float = 0.0
    primary_torque: float = 0.0
    secondary_torque: float = 0.0
    primary_normal_resultant: float = 0.0
    secondary_normal_resultant: float = 0.0

    def __post_init__(self) -> None:
        _require_finite(**self._components())

    @classmethod
    def zeros(cls) -> "ClosureUnknowns":
        return cls()

    @classmethod
    def from_components(
        cls,
        *,
        primary_angular_acceleration: float = 0.0,
        secondary_angular_acceleration: float = 0.0,
        belt_acceleration: float = 0.0,
        shift_acceleration: float = 0.0,
        primary_torque: float = 0.0,
        secondary_torque: float = 0.0,
        primary_normal_resultant: float = 0.0,
        secondary_normal_resultant: float = 0.0,
    ) -> "ClosureUnknowns":
        """Keyword-only constructor retained for readable call sites."""

        return cls(
            primary_angular_acceleration=primary_angular_acceleration,
            secondary_angular_acceleration=secondary_angular_acceleration,
            belt_acceleration=belt_acceleration,
            shift_acceleration=shift_acceleration,
            primary_torque=primary_torque,
            secondary_torque=secondary_torque,
            primary_normal_resultant=primary_normal_resultant,
            secondary_normal_resultant=secondary_normal_resultant,
        )

    @classmethod
    def from_ordered_values(cls, values: Iterable[float]) -> "ClosureUnknowns":
        """Construct from values in :class:`ClosureUnknown` column order."""

        ordered_values = tuple(values)
        if len(ordered_values) != CLOSURE_UNKNOWN_COUNT:
            raise ValueError(
                "ClosureUnknowns requires exactly "
                f"{CLOSURE_UNKNOWN_COUNT} ordered values."
            )

        return cls(*ordered_values)

    def __getitem__(self, unknown: ClosureUnknown) -> float:
        return self.as_tuple()[int(unknown)]

    def __iter__(self) -> Iterator[float]:
        return iter(self.as_tuple())

    def as_tuple(
        self,
    ) -> tuple[float, float, float, float, float, float, float, float]:
        """Return values in :class:`ClosureUnknown` column order."""

        return (
            self.primary_angular_acceleration,
            self.secondary_angular_acceleration,
            self.belt_acceleration,
            self.shift_acceleration,
            self.primary_torque,
            self.secondary_torque,
            self.primary_normal_resultant,
            self.secondary_normal_resultant,
        )

    def _components(self) -> dict[str, float]:
        return {
            "primary_angular_acceleration": self.primary_angular_acceleration,
            "secondary_angular_acceleration": self.secondary_angular_acceleration,
            "belt_acceleration": self.belt_acceleration,
            "shift_acceleration": self.shift_acceleration,
            "primary_torque": self.primary_torque,
            "secondary_torque": self.secondary_torque,
            "primary_normal_resultant": self.primary_normal_resultant,
            "secondary_normal_resultant": self.secondary_normal_resultant,
        }


@dataclass(frozen=True, slots=True)
class ClosureGains:
    """Gain row aligned with :class:`ClosureUnknowns`.

    Its fields have different physical units from the unknown values but the
    same column ordering. This separate type prevents a solved unknown vector
    from being accidentally used as a matrix gain row.
    """

    primary_angular_acceleration: float = 0.0
    secondary_angular_acceleration: float = 0.0
    belt_acceleration: float = 0.0
    shift_acceleration: float = 0.0
    primary_torque: float = 0.0
    secondary_torque: float = 0.0
    primary_normal_resultant: float = 0.0
    secondary_normal_resultant: float = 0.0

    def __post_init__(self) -> None:
        _require_finite(**self._components())

    @classmethod
    def zeros(cls) -> "ClosureGains":
        return cls()

    @classmethod
    def from_components(
        cls,
        *,
        primary_angular_acceleration: float = 0.0,
        secondary_angular_acceleration: float = 0.0,
        belt_acceleration: float = 0.0,
        shift_acceleration: float = 0.0,
        primary_torque: float = 0.0,
        secondary_torque: float = 0.0,
        primary_normal_resultant: float = 0.0,
        secondary_normal_resultant: float = 0.0,
    ) -> "ClosureGains":
        """Construct a named gain row without manually remembering indices."""

        return cls(
            primary_angular_acceleration=primary_angular_acceleration,
            secondary_angular_acceleration=secondary_angular_acceleration,
            belt_acceleration=belt_acceleration,
            shift_acceleration=shift_acceleration,
            primary_torque=primary_torque,
            secondary_torque=secondary_torque,
            primary_normal_resultant=primary_normal_resultant,
            secondary_normal_resultant=secondary_normal_resultant,
        )

    def __getitem__(self, unknown: ClosureUnknown) -> float:
        return self.as_tuple()[int(unknown)]

    def __iter__(self) -> Iterator[float]:
        return iter(self.as_tuple())

    def __add__(self, other: "ClosureGains") -> "ClosureGains":
        if not isinstance(other, ClosureGains):
            return NotImplemented

        return ClosureGains(
            primary_angular_acceleration=(
                self.primary_angular_acceleration + other.primary_angular_acceleration
            ),
            secondary_angular_acceleration=(
                self.secondary_angular_acceleration
                + other.secondary_angular_acceleration
            ),
            belt_acceleration=self.belt_acceleration + other.belt_acceleration,
            shift_acceleration=self.shift_acceleration + other.shift_acceleration,
            primary_torque=self.primary_torque + other.primary_torque,
            secondary_torque=self.secondary_torque + other.secondary_torque,
            primary_normal_resultant=(
                self.primary_normal_resultant + other.primary_normal_resultant
            ),
            secondary_normal_resultant=(
                self.secondary_normal_resultant + other.secondary_normal_resultant
            ),
        )

    def __neg__(self) -> "ClosureGains":
        return self.scaled(-1.0)

    def __sub__(self, other: "ClosureGains") -> "ClosureGains":
        if not isinstance(other, ClosureGains):
            return NotImplemented
        return self + (-other)

    def scaled(self, factor: float) -> "ClosureGains":
        """Return this gain row multiplied by one known scalar."""

        _require_finite(factor=factor)
        return ClosureGains(
            primary_angular_acceleration=(
                factor * self.primary_angular_acceleration
            ),
            secondary_angular_acceleration=(
                factor * self.secondary_angular_acceleration
            ),
            belt_acceleration=factor * self.belt_acceleration,
            shift_acceleration=factor * self.shift_acceleration,
            primary_torque=factor * self.primary_torque,
            secondary_torque=factor * self.secondary_torque,
            primary_normal_resultant=factor * self.primary_normal_resultant,
            secondary_normal_resultant=factor * self.secondary_normal_resultant,
        )

    def dot(self, unknowns: ClosureUnknowns) -> float:
        """Evaluate this gain row against solved closure unknowns."""

        return sum(
            gain * value
            for gain, value in zip(
                self.as_tuple(),
                unknowns.as_tuple(),
                strict=True,
            )
        )

    def as_tuple(
        self,
    ) -> tuple[float, float, float, float, float, float, float, float]:
        """Return gains in :class:`ClosureUnknown` column order."""

        return (
            self.primary_angular_acceleration,
            self.secondary_angular_acceleration,
            self.belt_acceleration,
            self.shift_acceleration,
            self.primary_torque,
            self.secondary_torque,
            self.primary_normal_resultant,
            self.secondary_normal_resultant,
        )

    def _components(self) -> dict[str, float]:
        return {
            "primary_angular_acceleration": self.primary_angular_acceleration,
            "secondary_angular_acceleration": self.secondary_angular_acceleration,
            "belt_acceleration": self.belt_acceleration,
            "shift_acceleration": self.shift_acceleration,
            "primary_torque": self.primary_torque,
            "secondary_torque": self.secondary_torque,
            "primary_normal_resultant": self.primary_normal_resultant,
            "secondary_normal_resultant": self.secondary_normal_resultant,
        }


@dataclass(frozen=True, slots=True)
class AffineClosureScalar:
    """A scalar relation affine in the canonical closure unknowns.

        value = bias + gains.dot(unknowns)

    This is deliberately not actuation-specific. It can represent a force,
    torque, compatibility residual, or any other scalar equation whose
    unknown-dependent part is linear in the closure variables.
    """

    bias: float = 0.0
    gains: ClosureGains = field(default_factory=ClosureGains.zeros)

    def __post_init__(self) -> None:
        _require_finite(bias=self.bias)

    @classmethod
    def zero(cls) -> "AffineClosureScalar":
        return cls()

    @classmethod
    def constant(cls, value: float) -> "AffineClosureScalar":
        """Return a relation containing one known scalar and no gains."""

        return cls(bias=value)

    def evaluate(self, unknowns: ClosureUnknowns) -> float:
        return self.bias + self.gains.dot(unknowns)

    def __add__(self, other: "AffineClosureScalar") -> "AffineClosureScalar":
        if not isinstance(other, AffineClosureScalar):
            return NotImplemented

        return AffineClosureScalar(
            bias=self.bias + other.bias,
            gains=self.gains + other.gains,
        )

    def __neg__(self) -> "AffineClosureScalar":
        return self.scaled(-1.0)

    def __sub__(self, other: "AffineClosureScalar") -> "AffineClosureScalar":
        if not isinstance(other, AffineClosureScalar):
            return NotImplemented
        return self + (-other)

    def scaled(self, factor: float) -> "AffineClosureScalar":
        """Return this relation multiplied by one known scalar."""

        _require_finite(factor=factor)
        return AffineClosureScalar(
            bias=factor * self.bias,
            gains=self.gains.scaled(factor),
        )


@dataclass(frozen=True, slots=True)
class ClosureEquation:
    """One named affine closure residual written in zero-equals form.

    ``residual`` is always represented as:

        residual(unknowns) = bias + gains.dot(unknowns).

    The equation imposed by a closure solve is:

        residual(unknowns) = 0.

    Therefore the corresponding matrix row is ``gains`` and its right-hand
    side is ``-bias``. Keeping that conversion here prevents individual CVT
    row builders from independently choosing incompatible signs.
    """

    name: str
    residual: AffineClosureScalar

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("ClosureEquation.name must be a non-empty string.")

    @property
    def matrix_row(
        self,
    ) -> tuple[float, float, float, float, float, float, float, float]:
        """Return the matrix coefficients in canonical column order."""

        return self.residual.gains.as_tuple()

    @property
    def right_hand_side(self) -> float:
        """Return the matrix right-hand side for ``A unknowns = b``."""

        return -self.residual.bias

    def evaluate(self, unknowns: ClosureUnknowns) -> float:
        """Evaluate this named residual after a trial solve."""

        return self.residual.evaluate(unknowns)


def _require_finite(**values: float) -> None:
    for name, value in values.items():
        if not isfinite(value):
            raise ValueError(f"{name} must be finite.")
