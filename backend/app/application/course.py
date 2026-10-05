"""Render frozen grade intent as elevation versus signed distance along road.

This is a display projection, not a second dynamics model. Segment boundaries
and extrapolation follow CINDER's distance-indexed road-profile contract.
"""

import math
from bisect import bisect_right

from app.schemas.course import CoursePoint, CourseProfile


def course_profile(case: dict, result: dict, provenance: dict | None = None):
    secondary = case.get("shaft_boundaries", {}).get("secondary", {})
    profile = secondary.get("road_profile")
    if not profile:
        return None
    if profile["kind"] == "constant_grade":
        segments = [
            {"start_distance_m": 0.0, "grade_angle_rad": profile["grade_angle_rad"]}
        ]
    elif profile["kind"] == "piecewise_constant_grade":
        segments = profile["segments"]
    else:
        return None
    distances = next(
        (
            column["values"]
            for column in result["report_table"]["columns"]
            if column["key"] == "vehicle.distance"
        ),
        [],
    )
    finite = [x for x in distances if x is not None and math.isfinite(x)]
    starts = [segment["start_distance_m"] for segment in segments]
    provenance = provenance or {}
    route_length = provenance.get("resolved_road", {}).get("length_m", 0)
    lower = min([0, *finite])
    upper = max([route_length, *starts, *finite, 1.0])
    nodes = sorted({lower, 0.0, upper, *starts})
    heights = [0.0]
    for left, right in zip(nodes, nodes[1:]):
        index = max(0, bisect_right(starts, left) - 1)
        heights.append(
            heights[-1] + (right - left) * math.sin(segments[index]["grade_angle_rad"])
        )
    origin = heights[nodes.index(0.0)]
    return CourseProfile(
        distance_column_key="vehicle.distance",
        name=provenance.get("scenario", {}).get("name", "Recorded road profile"),
        points=[
            CoursePoint(distance_m=x, elevation_m=y - origin)
            for x, y in zip(nodes, heights)
        ],
    )
