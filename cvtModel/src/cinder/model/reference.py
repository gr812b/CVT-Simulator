"""Small serializable time-reference primitives for physical tracking components.

The reference is deliberately a CINDER model primitive rather than a validation
utility.  Any host, shaft boundary, or actuator can consume a measured,
commanded, or synthetic time history without knowing where it came from.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
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

    Outside the supplied interval the endpoint value is held constant.  Inside
    the interval the value is linearly interpolated and ``slope_at`` returns the
    exact segment slope.  This makes the same primitive suitable for shaft-speed
    commands and axial position/rate commands without introducing controller
    state into CINDER's five-state CVT plant.
    """

    points: tuple[TimeValuePoint, ...]

    def __post_init__(self) -> None:
        if len(self.points) < 2:
            raise ValueError("PiecewiseLinearReference requires at least two points.")
        previous = self.points[0].time
        for point in self.points[1:]:
            if point.time <= previous:
                raise ValueError("reference point times must be strictly increasing.")
            previous = point.time

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
        """Return the local piecewise-linear slope; zero outside the trace."""

        if not isfinite(time):
            raise ValueError("time must be finite.")
        if time < self.points[0].time or time > self.points[-1].time:
            return 0.0
        index = self._segment_index(time)
        left = self.points[index]
        right = self.points[index + 1]
        return (right.value - left.value) / (right.time - left.time)

    def _segment_index(self, time: float) -> int:
        times = tuple(point.time for point in self.points)
        index = bisect_right(times, time) - 1
        return min(max(index, 0), len(self.points) - 2)
