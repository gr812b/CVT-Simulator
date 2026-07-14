from __future__ import annotations

import json
from dataclasses import dataclass
from math import atan, cos, degrees, radians, sin, sqrt
from pathlib import Path
from typing import Any

from .base_section import TrackSection
from .core import TrackEvaluationContext, TrackFeature
from .curvature_segment import CurvatureSegment
from .log_crossing import LogCrossing
from .profile_obstacle import ProfileObstacle
from .rough_patch import RoughPatch
from .slalom_segment import SlalomSegment
from .surface_patch import SurfacePatch
from .whoop_train import WhoopTrain


@dataclass(frozen=True, slots=True)
class TrackSample:
    section_index: int
    section_name: str
    surface: str
    section_start_m: float
    section_end_m: float
    local_distance_m: float
    elevation_m: float
    grade_degrees: float
    curvature_1_per_m: float
    bank_angle_degrees: float
    friction_coefficient: float
    rolling_resistance_coefficient: float
    normal_load_scale: float
    additional_resistance_force_n: float
    physical_corner_speed_limit_mps: float | None
    active_features: tuple[str, ...]
    active_feature_types: tuple[str, ...]

    @property
    def grade_radians(self) -> float:
        return radians(self.grade_degrees)


@dataclass(frozen=True, slots=True)
class Track:
    name: str
    sections: tuple[TrackSection, ...]
    features: tuple[TrackFeature, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("track name must be non-empty")
        if not self.sections:
            raise ValueError("track must contain at least one section")
        for feature in self.features:
            if feature.start_m < 0.0 or feature.end_m > self.length_m + 1.0e-9:
                raise ValueError(
                    f"feature {feature.name!r} spans {feature.start_m:.3f}–"
                    f"{feature.end_m:.3f} m outside 0–{self.length_m:.3f} m"
                )

    @property
    def length_m(self) -> float:
        return float(sum(section.length_m for section in self.sections))

    @property
    def boundaries_m(self) -> tuple[float, ...]:
        boundaries = [0.0]
        distance = 0.0
        for section in self.sections:
            distance += section.length_m
            boundaries.append(distance)
        return tuple(boundaries)

    @property
    def section_start_elevations_m(self) -> tuple[float, ...]:
        elevations = [0.0]
        elevation = 0.0
        for section in self.sections:
            elevation += section.length_m * section.grade_slope
            elevations.append(elevation)
        return tuple(elevations)

    def _section_at(self, distance_m: float) -> tuple[int, TrackSection, float, float, float]:
        x = min(max(float(distance_m), 0.0), self.length_m)
        boundaries = self.boundaries_m
        elevations = self.section_start_elevations_m
        for index, section in enumerate(self.sections):
            start = boundaries[index]
            end = boundaries[index + 1]
            if x < end or index == len(self.sections) - 1:
                return index, section, start, end, elevations[index]
        raise RuntimeError("track section lookup failed")

    def sample(
        self,
        distance_m: float,
        *,
        vehicle_speed_mps: float = 0.0,
        vehicle_mass_kg: float = 1.0,
        gravity_mps2: float = 9.80665,
    ) -> TrackSample:
        x = min(max(float(distance_m), 0.0), self.length_m)
        index, section, start, end, start_elevation = self._section_at(x)
        local = x - start
        base_elevation = start_elevation + section.grade_slope * local
        context = TrackEvaluationContext(
            distance_m=x,
            vehicle_speed_mps=max(0.0, float(vehicle_speed_mps)),
            vehicle_mass_kg=float(vehicle_mass_kg),
            gravity_mps2=float(gravity_mps2),
        )

        elevation_offset = 0.0
        slope_addition = 0.0
        curvature = 0.0
        bank_angle = 0.0
        friction = section.friction_coefficient
        rolling = section.rolling_resistance_coefficient
        normal_scale = 1.0
        extra_force = 0.0
        surface = section.surface
        active_names: list[str] = []
        active_types: list[str] = []

        for feature in self.features:
            if not feature.is_active(x):
                continue
            effect = feature.evaluate(context)
            elevation_offset += effect.elevation_offset_m
            slope_addition += effect.grade_slope_addition
            curvature += effect.curvature_1_per_m
            bank_angle += effect.bank_angle_degrees
            if effect.friction_coefficient_override is not None:
                friction = effect.friction_coefficient_override
            friction *= effect.friction_multiplier
            if effect.rolling_resistance_override is not None:
                rolling = effect.rolling_resistance_override
            rolling *= effect.rolling_resistance_multiplier
            normal_scale *= effect.normal_load_scale
            extra_force += effect.additional_resistance_force_n
            if effect.surface_override is not None:
                surface = effect.surface_override
            active_names.append(feature.name)
            active_types.append(feature.type_name)

        grade_slope = section.grade_slope + slope_addition
        grade_radians = atan(grade_slope)
        physical_limit: float | None = None
        if abs(curvature) > 1.0e-12 and friction > 0.0 and normal_scale > 0.0:
            beta = radians(bank_angle)
            numerator = gravity_mps2 * max(cos(grade_radians), 0.0) * (
                sin(beta) + friction * normal_scale * cos(beta)
            )
            denominator = abs(curvature) * (
                cos(beta) - friction * normal_scale * sin(beta)
            )
            if numerator <= 0.0:
                physical_limit = 0.0
            elif denominator > 1.0e-12:
                physical_limit = sqrt(numerator / denominator)

        return TrackSample(
            section_index=index,
            section_name=section.name,
            surface=surface,
            section_start_m=start,
            section_end_m=end,
            local_distance_m=local,
            elevation_m=base_elevation + elevation_offset,
            grade_degrees=degrees(grade_radians),
            curvature_1_per_m=curvature,
            bank_angle_degrees=bank_angle,
            friction_coefficient=max(0.0, friction),
            rolling_resistance_coefficient=max(0.0, rolling),
            normal_load_scale=max(0.0, normal_scale),
            additional_resistance_force_n=max(0.0, extra_force),
            physical_corner_speed_limit_mps=physical_limit,
            active_features=tuple(active_names),
            active_feature_types=tuple(active_types),
        )

    def safe_speed_limit_mps(
        self,
        distance_m: float,
        *,
        braking_deceleration_mps2: float,
        gravity_mps2: float = 9.80665,
    ) -> float:
        """Propagate physical curvature limits backward using braking distance.

        Track geometry supplies only the physical corner limit. Braking strength,
        control gain, speed margin, traffic, and future driver disturbances remain
        outside the track definition.
        """

        if braking_deceleration_mps2 <= 0.0:
            raise ValueError("braking_deceleration_mps2 must be positive")
        x = min(max(float(distance_m), 0.0), self.length_m)
        result = float("inf")
        current = self.sample(x, gravity_mps2=gravity_mps2)
        if current.physical_corner_speed_limit_mps is not None:
            result = current.physical_corner_speed_limit_mps

        for feature in self.features:
            if not isinstance(feature, CurvatureSegment) or feature.start_m <= x:
                continue
            sample_inside = self.sample(
                min(feature.start_m + 1.0e-6, self.length_m),
                gravity_mps2=gravity_mps2,
            )
            limit = sample_inside.physical_corner_speed_limit_mps
            if limit is None:
                continue
            safe_now = sqrt(
                limit**2
                + 2.0 * braking_deceleration_mps2 * (feature.start_m - x)
            )
            result = min(result, safe_now)
        return result

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Track":
        sections_raw = raw.get("sections")
        if not isinstance(sections_raw, list):
            raise ValueError("track JSON must contain a 'sections' list")
        sections = tuple(TrackSection(**section) for section in sections_raw)
        feature_types = {
            "surface_patch": SurfacePatch,
            "curvature_segment": CurvatureSegment,
            "log_crossing": LogCrossing,
            "profile_obstacle": ProfileObstacle,
            "rough_patch": RoughPatch,
            "slalom_segment": SlalomSegment,
            "whoop_train": WhoopTrain,
        }
        features: list[TrackFeature] = []
        for raw_feature in raw.get("features", []):
            if not isinstance(raw_feature, dict):
                raise ValueError("each feature must be an object")
            payload = dict(raw_feature)
            type_name = str(payload.pop("type", ""))
            feature_cls = feature_types.get(type_name)
            if feature_cls is None:
                raise ValueError(
                    f"unsupported track feature type {type_name!r}; "
                    f"choose from {sorted(feature_types)}"
                )
            features.append(feature_cls(**payload))
        return cls(
            name=str(raw["name"]),
            notes=str(raw.get("notes", "")),
            sections=sections,
            features=tuple(features),
        )

    @classmethod
    def from_json(cls, path: Path) -> "Track":
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("track JSON root must be an object")
        return cls.from_dict(raw)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "notes": self.notes,
            "length_m": self.length_m,
            "sections": [section.to_dict() for section in self.sections],
            "features": [feature.to_dict() for feature in self.features],
        }


class TrackBuilder:
    """Small fluent builder for code-defined tracks; JSON uses the same objects."""

    def __init__(self, name: str, *, notes: str = "") -> None:
        self._name = name
        self._notes = notes
        self._sections: list[TrackSection] = []
        self._features: list[TrackFeature] = []

    def add_section(self, section: TrackSection) -> "TrackBuilder":
        self._sections.append(section)
        return self

    def add_feature(self, feature: TrackFeature) -> "TrackBuilder":
        self._features.append(feature)
        return self

    def build(self) -> Track:
        return Track(
            name=self._name,
            notes=self._notes,
            sections=tuple(self._sections),
            features=tuple(self._features),
        )


def banked_tire_loads_n(
    *,
    mass_kg: float,
    gravity_mps2: float,
    grade_radians: float,
    speed_mps: float,
    curvature_1_per_m: float,
    bank_angle_degrees: float,
    normal_load_scale: float = 1.0,
) -> tuple[float, float]:
    """Return total road-normal load and signed road-lateral tire demand.

    Positive bank angle assists the active turn regardless of left/right
    direction. Lateral-force sign follows signed curvature.
    """

    beta = radians(bank_angle_degrees)
    curvature_magnitude = abs(curvature_1_per_m)
    gravity_normal = gravity_mps2 * max(cos(grade_radians), 0.0)
    centripetal_acceleration = speed_mps**2 * curvature_magnitude
    normal_per_mass = (
        gravity_normal * cos(beta)
        + centripetal_acceleration * sin(beta)
    )
    lateral_per_mass = (
        centripetal_acceleration * cos(beta)
        - gravity_normal * sin(beta)
    )
    turn_sign = 1.0 if curvature_1_per_m >= 0.0 else -1.0
    return (
        max(0.0, mass_kg * normal_per_mass * normal_load_scale),
        mass_kg * lateral_per_mass * turn_sign,
    )

def normal_load_n(
    *,
    mass_kg: float,
    gravity_mps2: float,
    grade_radians: float,
    normal_load_scale: float = 1.0,
) -> float:
    return max(
        0.0,
        mass_kg * gravity_mps2 * cos(grade_radians) * normal_load_scale,
    )
