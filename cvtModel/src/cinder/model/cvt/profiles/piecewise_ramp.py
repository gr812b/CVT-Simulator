from __future__ import annotations

from dataclasses import dataclass
from math import isclose
from typing import Iterable

from .ramp_segment import RampSegment
from .types import ProfileSample, ScalarProfile, require_coordinate, require_finite


@dataclass(frozen=True, slots=True)
class RampJunctionContinuity:
    """Derivative continuity data at one PiecewiseRamp junction."""

    coordinate: float
    left_first_derivative: float
    right_first_derivative: float
    left_second_derivative: float
    right_second_derivative: float
    left_third_derivative: float | None
    right_third_derivative: float | None

    def is_continuous(
        self,
        *,
        order: int,
        relative_tolerance: float = 1.0e-9,
        absolute_tolerance: float = 1.0e-10,
    ) -> bool:
        """Return whether derivatives through ``order`` match."""

        if order not in (0, 1, 2, 3):
            raise ValueError("order must be one of 0, 1, 2, or 3.")
        if relative_tolerance < 0.0 or absolute_tolerance < 0.0:
            raise ValueError("continuity tolerances must be non-negative.")
        if order == 0:
            return True

        def close(left: float, right: float) -> bool:
            return isclose(
                left,
                right,
                rel_tol=relative_tolerance,
                abs_tol=absolute_tolerance,
            )

        if not close(
            self.left_first_derivative,
            self.right_first_derivative,
        ):
            return False
        if order == 1:
            return True

        if not close(
            self.left_second_derivative,
            self.right_second_derivative,
        ):
            return False
        if order == 2:
            return True

        if (
            self.left_third_derivative is None
            or self.right_third_derivative is None
        ):
            return False
        return close(
            self.left_third_derivative,
            self.right_third_derivative,
        )

    def as_dict(self) -> dict[str, float | None]:
        """Return derivative jumps for diagnostics/UI use."""

        return {
            "coordinate_m": self.coordinate,
            "first_derivative_jump": (
                self.right_first_derivative
                - self.left_first_derivative
            ),
            "second_derivative_jump_per_m": (
                self.right_second_derivative
                - self.left_second_derivative
            ),
            "third_derivative_jump_per_m2": (
                None
                if (
                    self.left_third_derivative is None
                    or self.right_third_derivative is None
                )
                else (
                    self.right_third_derivative
                    - self.left_third_derivative
                )
            ),
        }


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

    The generic container remains permissive. Consumers that require smoother
    profiles can inspect :meth:`junction_continuity` or call
    :meth:`require_continuity` at the derivative order their physics needs.
    """

    def __init__(self, segments: Iterable[RampSegment] = ()) -> None:
        self._placements: list[_PlacedSegment] = []

        for segment in segments:
            self.add_segment(segment)

    @property
    def segments(self) -> tuple[RampSegment, ...]:
        return tuple(
            placement.segment
            for placement in self._placements
        )

    @property
    def x_min(self) -> float:
        return 0.0

    @property
    def x_max(self) -> float:
        if not self._placements:
            raise ValueError(
                "A ramp with no segments has no coordinate range."
            )

        return self._placements[-1].x_end

    def add_segment(self, segment: RampSegment) -> None:
        if not isinstance(segment, RampSegment):
            raise TypeError(
                "segment must implement the RampSegment contract."
            )

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
            third_derivative=local.third_derivative,
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
            local_end = placement.segment.evaluate_local(
                placement.segment.length
            ).value
            value_end = placement.value_start + local_end

            lower_value = min(placement.value_start, value_end)
            upper_value = max(placement.value_start, value_end)

            if not (
                lower_value - tolerance
                <= target_height
                <= upper_value + tolerance
            ):
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
            if not any(
                abs(x - other) <= tolerance
                for other in unique_matches
            ):
                unique_matches.append(x)

        if len(unique_matches) == 1:
            return unique_matches[0]

        if len(unique_matches) > 1:
            raise ValueError(
                "target_height maps to multiple positions in this ramp."
            )

        raise ValueError(
            "target_height is not invertible within this ramp."
        )

    def junction_continuity(
        self,
    ) -> tuple[RampJunctionContinuity, ...]:
        """Return derivative matching data at every segment junction."""

        results: list[RampJunctionContinuity] = []
        for left, right in zip(
            self._placements[:-1],
            self._placements[1:],
            strict=True,
        ):
            left_sample = left.segment.evaluate_local(
                left.segment.length
            )
            right_sample = right.segment.evaluate_local(0.0)
            results.append(
                RampJunctionContinuity(
                    coordinate=left.x_end,
                    left_first_derivative=(
                        left_sample.first_derivative
                    ),
                    right_first_derivative=(
                        right_sample.first_derivative
                    ),
                    left_second_derivative=(
                        left_sample.second_derivative
                    ),
                    right_second_derivative=(
                        right_sample.second_derivative
                    ),
                    left_third_derivative=(
                        left_sample.third_derivative
                    ),
                    right_third_derivative=(
                        right_sample.third_derivative
                    ),
                )
            )
        return tuple(results)

    def require_continuity(
        self,
        *,
        order: int,
        relative_tolerance: float = 1.0e-9,
        absolute_tolerance: float = 1.0e-10,
    ) -> None:
        """Raise when any segment junction lacks required continuity."""

        failures = tuple(
            junction
            for junction in self.junction_continuity()
            if not junction.is_continuous(
                order=order,
                relative_tolerance=relative_tolerance,
                absolute_tolerance=absolute_tolerance,
            )
        )
        if not failures:
            return

        coordinates = ", ".join(
            f"{junction.coordinate:.12g}"
            for junction in failures
        )
        raise ValueError(
            f"Piecewise ramp is not C{order} at profile "
            f"coordinate(s) {coordinates} m."
        )

    def _placement_at(self, x: float) -> _PlacedSegment:
        if not self._placements:
            raise ValueError(
                "Cannot evaluate a ramp with no segments."
            )

        require_coordinate(
            x=x,
            x_min=self.x_min,
            x_max=self.x_max,
        )

        for placement in self._placements:
            if x <= placement.x_end:
                return placement

        raise RuntimeError(
            "Could not locate the requested ramp coordinate."
        )

    @staticmethod
    def _value_at_placement_end(
        placement: _PlacedSegment,
    ) -> float:
        return (
            placement.value_start
            + placement.segment.evaluate_local(
                placement.segment.length
            ).value
        )
