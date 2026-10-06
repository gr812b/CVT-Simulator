"""Presentation projection of a run's frozen road profile."""

from typing import Literal

from app.schemas.common import ApiModel


class CoursePoint(ApiModel):
    distance_m: float
    elevation_m: float


class CourseProfile(ApiModel):
    points: list[CoursePoint]
    distance_column_key: Literal["vehicle.distance"]
    name: str
