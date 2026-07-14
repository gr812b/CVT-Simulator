from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, pi, sin

from .core import FeatureEffect, TrackEvaluationContext


@dataclass(frozen=True, slots=True)
class SlalomSegment:
    """Smooth sequence of alternating bends.

    For local distance ``xi`` over length ``L`` and ``n`` alternating bends,

        kappa(x) = s kappa_max sin(n pi xi/L),

    where ``s`` is +1 for an initial left bend and -1 for an initial right
    bend. Each half-wave is one bend, so ``bend_count`` is easy to estimate by
    counting visible direction changes or gates in video.
    """

    name: str
    start_m: float
    length_m: float
    bend_count: int
    peak_curvature_1_per_m: float
    initial_direction: str = "left"

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("slalom name must be non-empty")
        if not isfinite(self.start_m) or self.start_m < 0.0:
            raise ValueError("start_m must be finite and non-negative")
        if not isfinite(self.length_m) or self.length_m <= 0.0:
            raise ValueError("length_m must be positive and finite")
        if self.bend_count <= 0:
            raise ValueError("bend_count must be positive")
        if (
            not isfinite(self.peak_curvature_1_per_m)
            or self.peak_curvature_1_per_m <= 0.0
        ):
            raise ValueError("peak_curvature_1_per_m must be positive and finite")
        if self.initial_direction not in {"left", "right"}:
            raise ValueError("initial_direction must be 'left' or 'right'")

    @property
    def type_name(self) -> str:
        return "slalom_segment"

    @property
    def end_m(self) -> float:
        return self.start_m + self.length_m

    def is_active(self, distance_m: float) -> bool:
        return self.start_m <= distance_m < self.end_m

    def evaluate(self, context: TrackEvaluationContext) -> FeatureEffect:
        if not self.is_active(context.distance_m):
            return FeatureEffect()
        xi = context.distance_m - self.start_m
        sign = 1.0 if self.initial_direction == "left" else -1.0
        curvature = sign * self.peak_curvature_1_per_m * sin(
            self.bend_count * pi * xi / self.length_m
        )
        return FeatureEffect(curvature_1_per_m=curvature)

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.type_name,
            "name": self.name,
            "start_m": self.start_m,
            "length_m": self.length_m,
            "bend_count": self.bend_count,
            "peak_curvature_1_per_m": self.peak_curvature_1_per_m,
            "initial_direction": self.initial_direction,
        }
