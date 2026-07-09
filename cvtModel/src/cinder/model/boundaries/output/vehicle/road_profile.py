"""Position-indexed road-grade profiles for vehicle-side load evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, pi
from typing import Callable, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class RoadProfileSample:
    """
    Local road condition queried at one signed vehicle distance.

    ``grade_angle`` is positive when the road rises in the positive vehicle
    travel direction. The sample retains the distance at which it was queried
    so a road-profile implementation can return a self-contained local result
    and later extend it with terrain properties. ``DynamicsSnapshot`` does not
    retain this intermediate sample; it consumes only the grade angle needed to
    build ``RoadLoadResult``.
    """

    vehicle_distance: float
    grade_angle: float

    def __post_init__(self) -> None:
        _require_finite("vehicle_distance", self.vehicle_distance)
        _validate_grade_angle(self.grade_angle)


@runtime_checkable
class RoadProfile(Protocol):
    """A physical road definition sampled by signed vehicle distance."""

    def sample(
        self,
        *,
        vehicle_distance: float,
    ) -> RoadProfileSample:
        """Return the local road condition at ``vehicle_distance``."""


@dataclass(frozen=True, slots=True)
class ConstantGradeRoadProfile:
    """Road profile with one constant grade angle; default is level ground."""

    grade_angle: float = 0.0

    def __post_init__(self) -> None:
        _validate_grade_angle(self.grade_angle)

    def sample(
        self,
        *,
        vehicle_distance: float,
    ) -> RoadProfileSample:
        return RoadProfileSample(
            vehicle_distance=vehicle_distance,
            grade_angle=self.grade_angle,
        )


@dataclass(frozen=True, slots=True)
class PiecewiseConstantGradeSegment:
    """One constant-grade route segment starting at signed vehicle distance."""

    start_distance: float
    grade_angle: float

    def __post_init__(self) -> None:
        _require_finite("start_distance", self.start_distance)
        _validate_grade_angle(self.grade_angle)


@dataclass(frozen=True, slots=True)
class PiecewiseConstantGradeRoadProfile:
    """Distance-indexed route made from constant-grade segments.

    Segments are evaluated by signed vehicle distance. The grade from the
    greatest ``start_distance`` not exceeding the queried distance is used;
    distances before the first segment use the first segment. This keeps a
    launch route such as "flat for 90 m, then 30 degrees uphill" executable
    without requiring a time-varying forcing function.
    """

    segments: tuple[PiecewiseConstantGradeSegment, ...]

    def __post_init__(self) -> None:
        if not self.segments:
            raise ValueError("PiecewiseConstantGradeRoadProfile requires at least one segment.")

        previous_start: float | None = None
        for index, segment in enumerate(self.segments):
            if not isinstance(segment, PiecewiseConstantGradeSegment):
                raise TypeError(
                    "segments must contain PiecewiseConstantGradeSegment instances."
                )
            if previous_start is not None and segment.start_distance <= previous_start:
                raise ValueError(
                    "segment start distances must be strictly increasing."
                )
            if index == 0 and segment.start_distance != 0.0:
                raise ValueError("the first road-profile segment must start at 0.0 m.")
            previous_start = segment.start_distance

    def sample(
        self,
        *,
        vehicle_distance: float,
    ) -> RoadProfileSample:
        _require_finite("vehicle_distance", vehicle_distance)

        active = self.segments[0]
        for segment in self.segments[1:]:
            if vehicle_distance < segment.start_distance:
                break
            active = segment

        return RoadProfileSample(
            vehicle_distance=vehicle_distance,
            grade_angle=active.grade_angle,
        )


@dataclass(frozen=True, slots=True)
class CallableRoadProfile:
    """
    Adapt a user-supplied ``grade_angle(vehicle_distance)`` function.

    The callable is intentionally defined in physical vehicle distance rather
    than in a CVT coordinate. ``CVTDynamicsModel`` performs the one fixed
    final-drive conversion from accumulated secondary-shaft angle before it
    samples this profile.
    """

    grade_angle_function: Callable[[float], float]

    def __post_init__(self) -> None:
        if not callable(self.grade_angle_function):
            raise TypeError("grade_angle_function must be callable.")

    def sample(
        self,
        *,
        vehicle_distance: float,
    ) -> RoadProfileSample:
        _require_finite("vehicle_distance", vehicle_distance)
        grade_angle = self.grade_angle_function(vehicle_distance)

        return RoadProfileSample(
            vehicle_distance=vehicle_distance,
            grade_angle=grade_angle,
        )


def _require_finite(name: str, value: float) -> None:
    if not isfinite(value):
        raise ValueError(f"{name} must be finite.")


def _validate_grade_angle(grade_angle: float) -> None:
    if not isfinite(grade_angle):
        raise ValueError("grade_angle must be finite.")

    if not -pi / 2.0 < grade_angle < pi / 2.0:
        raise ValueError("grade_angle must lie strictly between -pi/2 and pi/2.")
