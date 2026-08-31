from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class ProfileSample:
    """
    One scalar profile evaluated at a coordinate.

    The derivative fields are always with respect to the coordinate supplied
    to the corresponding evaluate method.
    """

    value: float
    first_derivative: float
    second_derivative: float
    third_derivative: float | None = None


class ScalarProfile(ABC):
    """A scalar profile defined over a finite one-dimensional interval."""

    @property
    @abstractmethod
    def x_min(self) -> float:
        """Smallest valid profile coordinate [m]."""

    @property
    @abstractmethod
    def x_max(self) -> float:
        """Largest valid profile coordinate [m]."""

    @abstractmethod
    def evaluate(self, x: float) -> ProfileSample:
        """Return value, first derivative, and second derivative at x."""


def require_finite(**values: float) -> None:
    for name, value in values.items():
        if not isfinite(value):
            raise ValueError(f"{name} must be finite.")


def require_coordinate(*, x: float, x_min: float, x_max: float) -> None:
    require_finite(x=x)

    if not x_min <= x <= x_max:
        raise ValueError(f"x={x} is outside the valid interval [{x_min}, {x_max}].")
