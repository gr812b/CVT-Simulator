"""Position-indexed road-grade profiles for vehicle-side load evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, pi
from typing import Callable, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class RoadProfileSample:
    """
    Local road condition at one signed vehicle distance.

    ``grade_angle`` is positive when the road rises in the positive vehicle
    travel direction. The current road-load model needs only grade angle, but
    retaining the queried distance in the sample makes a snapshot self-
    describing and leaves a natural home for later surface or terrain data.
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
