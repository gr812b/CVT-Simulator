from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .ramp_segment import RampSegment
from .types import ProfileSample, ScalarProfile, require_coordinate, require_finite


@dataclass(frozen=True, slots=True)
class _PlacedSegment:
    segment: RampSegment
    x_start: float
    x_end: float
    value_start: float


class PiecewiseRamp(ScalarProfile):
    """
    C0-continuous profile assembled from local RampSegment instances.

    Every segment retains its own local geometry. This class alone owns global
    placement and applies the vertical offsets required for continuity.

    At an exact segment junction, evaluate() uses the segment on the left.
    This is deterministic and permits designed slope/curvature discontinuities.
    """

    def __init__(self, segments: Iterable[RampSegment] = ()) -> None:
        self._placements: list[_PlacedSegment] = []

        for segment in segments:
            self.add_segment(segment)

    @property
    def segments(self) -> tuple[RampSegment, ...]:
        return tuple(placement.segment for placement in self._placements)

    @property
    def x_min(self) -> float:
        return 0.0

    @property
    def x_max(self) -> float:
        if not self._placements:
            raise ValueError("A ramp with no segments has no coordinate range.")

        return self._placements[-1].x_end

    def add_segment(self, segment: RampSegment) -> None:
        if not isinstance(segment, RampSegment):
            raise TypeError("segment must implement the RampSegment contract.")

        if self._placements:
            previous = self._placements[-1]
            x_start = previous.x_end
            value_start = self._value_at_placement_end(previous)
        else:
            x_start = 0.0
            value_start = 0.0

        self._placements.append(
            _PlacedSegment(
                segment=segment,
                x_start=x_start,
                x_end=x_start + segment.length,
                value_start=value_start,
            )
        )

    def evaluate(self, x: float) -> ProfileSample:
        placement = self._placement_at(x)
        local_x = x - placement.x_start

        # At each exact junction, select the segment on the left.
        if x == placement.x_end:
            local_x = placement.segment.length

        local = placement.segment.evaluate_local(local_x)

        return ProfileSample(
            value=placement.value_start + local.value,
            first_derivative=local.first_derivative,
            second_derivative=local.second_derivative,
        )

    def height(self, x: float) -> float:
        return self.evaluate(x).value

    def slope(self, x: float) -> float:
        return self.evaluate(x).first_derivative

    def curvature(self, x: float) -> float:
        return self.evaluate(x).second_derivative

    def find_x_at_height(self, target_height: float) -> float:
        """
        Find a global coordinate whose profile value equals target_height.

        The result is only defined when exactly one segment provides an
        unambiguous inverse. This helper is useful for design/UI work and is
        intentionally not needed by the runtime CVT model.
        """

        require_finite(target_height=target_height)
        matches: list[float] = []
        tolerance = 1e-12

        for placement in self._placements:
            local_end = placement.segment.evaluate_local(placement.segment.length).value
            value_end = placement.value_start + local_end

            lower_value = min(placement.value_start, value_end)
            upper_value = max(placement.value_start, value_end)

            if not lower_value - tolerance <= target_height <= upper_value + tolerance:
                continue

            try:
                local_x = placement.segment.inverse_local_value(
                    target_height - placement.value_start
                )
            except NotImplementedError:
                continue

            matches.append(placement.x_start + local_x)

        unique_matches: list[float] = []
        for x in matches:
            if not any(abs(x - other) <= tolerance for other in unique_matches):
                unique_matches.append(x)

        if len(unique_matches) == 1:
            return unique_matches[0]

        if len(unique_matches) > 1:
            raise ValueError("target_height maps to multiple positions in this ramp.")

        raise ValueError("target_height is not invertible within this ramp.")

    def _placement_at(self, x: float) -> _PlacedSegment:
        if not self._placements:
            raise ValueError("Cannot evaluate a ramp with no segments.")

        require_coordinate(x=x, x_min=self.x_min, x_max=self.x_max)

        for placement in self._placements:
            if x <= placement.x_end:
                return placement

        raise RuntimeError("Could not locate the requested ramp coordinate.")

    @staticmethod
    def _value_at_placement_end(placement: _PlacedSegment) -> float:
        return (
            placement.value_start
            + placement.segment.evaluate_local(placement.segment.length).value
        )
