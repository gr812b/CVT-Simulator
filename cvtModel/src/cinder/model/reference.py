"""Small serializable scalar time-history primitives."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from math import isfinite


@dataclass(frozen=True, slots=True)
class TimeValuePoint:
    """One scalar reference sample at physical time ``time``."""

    time: float
    value: float

    def __post_init__(self) -> None:
        if not isfinite(self.time):
            raise ValueError("time must be finite.")
        if not isfinite(self.value):
            raise ValueError("value must be finite.")


@dataclass(frozen=True, slots=True)
class PiecewiseLinearReference:
    """Clamped piecewise-linear scalar time history.

    Values are linearly interpolated between samples and held at the endpoint
    values outside the supplied interval.  Times must be strictly increasing.
    """

    points: tuple[TimeValuePoint, ...]
    _times: tuple[float, ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if len(self.points) < 2:
            raise ValueError("PiecewiseLinearReference requires at least two points.")
        if not all(isinstance(point, TimeValuePoint) for point in self.points):
            raise TypeError("points must contain only TimeValuePoint values.")

        times = tuple(point.time for point in self.points)
        if any(right <= left for left, right in zip(times, times[1:])):
            raise ValueError("reference point times must be strictly increasing.")
        object.__setattr__(self, "_times", times)

    @property
    def start_time(self) -> float:
        return self.points[0].time

    @property
    def end_time(self) -> float:
        return self.points[-1].time

    def value_at(self, time: float) -> float:
        if not isfinite(time):
            raise ValueError("time must be finite.")
        if time <= self.points[0].time:
            return self.points[0].value
        if time >= self.points[-1].time:
            return self.points[-1].value

        index = self._segment_index(time)
        left = self.points[index]
        right = self.points[index + 1]
        fraction = (time - left.time) / (right.time - left.time)
        return left.value + fraction * (right.value - left.value)

    def slope_at(self, time: float) -> float:
        """Return the local piecewise-linear slope; zero outside the interval."""

        if not isfinite(time):
            raise ValueError("time must be finite.")
        if time < self.points[0].time or time > self.points[-1].time:
            return 0.0

        index = self._segment_index(time)
        left = self.points[index]
        right = self.points[index + 1]
        return (right.value - left.value) / (right.time - left.time)

    def _segment_index(self, time: float) -> int:
        index = bisect_right(self._times, time) - 1
        return min(max(index, 0), len(self.points) - 2)
