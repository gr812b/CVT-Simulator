"""Resolve the small geometry form into the canonical CINDER study request."""

from math import atan, tan

from app.application.physical_contracts import baseline_case
from app.core.errors import ApiProblem
from app.schemas.studies import (
    EndpointRadiiGeometryStudyRequest,
    SimpleGeometryRequest,
)


def template():
    geometry = baseline_case()["assembly"]["geometry"]
    return SimpleGeometryRequest(
        **{
            key: geometry[key]
            for key in (
                "belt_outer_length_m",
                "primary_outer_radius_at_zero_shift_m",
                "secondary_outer_radius_at_zero_shift_m",
                "sheave_half_angle_rad",
                "deadzone_shift_m",
            )
        },
        belt_height_m=geometry["belt"]["height_m"],
        belt_outer_width_m=geometry["belt"]["outer_width_m"],
        cord_depth_from_outer_m=geometry["belt"]["cord_depth_from_outer_m"],
    )


def resolve(request):
    inner = request.measured_inner_width_m
    if request.section_mode == "matching_angle":
        inner = request.belt_outer_width_m - 2 * request.belt_height_m * tan(
            request.sheave_half_angle_rad
        )
    if inner is None or not 0 < inner < request.belt_outer_width_m:
        raise ApiProblem(
            422,
            "belt_section",
            "These dimensions must give a positive bottom width smaller than the top width.",
        )
    active = request.active_travel_limit_m if request.active_travel_limit_m is not None else inner
    if active > inner:
        raise ApiProblem(
            422,
            "travel_limit",
            "The mechanical travel limit cannot exceed the bottom-width travel assumed by this study.",
        )
    return EndpointRadiiGeometryStudyRequest(
        context={
            "belt": {
                "height_m": request.belt_height_m,
                "outer_width_m": request.belt_outer_width_m,
                "inner_width_m": inner,
                "cord_depth_from_outer_m": request.cord_depth_from_outer_m,
            },
            "belt_outer_length_m": request.belt_outer_length_m,
            "sheave_half_angle_rad": atan(
                (request.belt_outer_width_m - inner) / (2 * request.belt_height_m)
            ),
            "deadzone_shift_m": request.deadzone_shift_m,
            "max_shift_m": request.deadzone_shift_m + active,
        },
        primary_outer_radius_at_zero_shift_m=request.primary_outer_radius_at_zero_shift_m,
        secondary_outer_radius_at_zero_shift_m=request.secondary_outer_radius_at_zero_shift_m,
        sample_count=101,
    )
