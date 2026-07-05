from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from .types import ProfileSample, require_coordinate, require_finite


@dataclass(frozen=True, slots=True)
class RampSegment(ABC):
    """
    Base contract for one local segment of a PiecewiseRamp.

    Every segment is expressed in its own local coordinates:

        0 <= x_local <= length
        value_local(0) = 0

    PiecewiseRamp owns the global x and value offsets that connect segments.
    This keeps a segment reusable and prevents it from carrying mutable
    placement state such as x_start or y_start.
    """

    length: float

    def __post_init__(self) -> None:
        require_finite(length=self.length)

        if self.length <= 0.0:
            raise ValueError("length must be positive.")

    @abstractmethod
    def evaluate_local(self, x_local: float) -> ProfileSample:
        """
        Return local value, slope, and curvature at x_local.

        Implementations must return a profile whose local value is zero at
        x_local = 0. The slope and curvature are derivatives with respect to
        x_local.
        """

    def height_local(self, x_local: float) -> float:
        """Convenience alias for evaluate_local(x_local).value."""

        return self.evaluate_local(x_local).value

    def slope_local(self, x_local: float) -> float:
        """Convenience alias for the local first derivative."""

        return self.evaluate_local(x_local).first_derivative

    def curvature_local(self, x_local: float) -> float:
        """Convenience alias for the local second derivative."""

        return self.evaluate_local(x_local).second_derivative

    def inverse_local_value(self, value: float) -> float:
        """
        Return x_local for a local profile value, when the segment is invertible.

        This is optional because not every valid segment is one-to-one in value.
        PiecewiseRamp.find_x_at_height() uses it for segments that support it.
        """

        raise NotImplementedError(
            f"{type(self).__name__} does not provide inverse_local_value()."
        )

    def _validate_local_coordinate(self, x_local: float) -> None:
        require_coordinate(
            x=x_local,
            x_min=0.0,
            x_max=self.length,
        )
