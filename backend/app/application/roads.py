"""Resolve editable road intent once for both the preview and CINDER input.

Distance is signed vehicle travel along the road, not horizontal map distance.
Linear elevation in that coordinate gives asin(dz/ds), a constant grade.
"""

import math

from app.core.errors import ApiProblem
from app.core.settings import Settings
from app.schemas.experiments import (
    ExperimentLimits,
    ExperimentMetadata,
    RoadResolution,
    ScenarioDocument,
    SpatialRoad,
)


def feature_templates():
    return [
        {"id": "flat", "kind": "flat", "length_m": 20},
        {
            "id": "climb",
            "kind": "slope",
            "name": "Climb",
            "length_m": 20,
            "angle_rad": math.radians(10),
        },
        {
            "id": "descent",
            "kind": "slope",
            "name": "Descent",
            "length_m": 20,
            "angle_rad": math.radians(-10),
        },
        {"id": "crest", "kind": "crest", "length_m": 20, "height_m": 2},
        {"id": "dip", "kind": "dip", "length_m": 20, "height_m": 2},
        {"id": "whoops", "kind": "whoops", "height_m": 0.4, "spacing_m": 6, "count": 5},
        {
            "id": "points",
            "kind": "points",
            "points": [
                {"distance_m": 0, "elevation_m": 0},
                {"distance_m": 20, "elevation_m": 0},
            ],
        },
    ]


def default_scenario():
    return ScenarioDocument(
        kind="scenarios",
        name="Flat road",
        road=SpatialRoad(features=[feature_templates()[0]]),
    )


def metadata(settings: Settings):
    return ExperimentMetadata(
        limits=ExperimentLimits(
            max_duration_s=settings.run_max_duration_seconds,
            max_features=settings.road_max_features,
            max_segments=settings.road_max_segments,
            max_distance_m=settings.road_max_distance_m,
            max_grade_degrees=settings.road_max_grade_degrees,
            max_report_samples=settings.run_max_report_samples,
            wall_timeout_s=settings.run_timeout_seconds,
        ),
        scenario_template=default_scenario(),
        feature_templates=feature_templates(),
        conventions=[
            "Distance means travel along the road, not horizontal map distance. Elevation is relative to the route start.",
            "Sections join continuously. Reordering or resizing a section shifts every later section.",
            "The preview's straight segments are exactly the constant-grade segments sent to CINDER; no hidden smoothing.",
            "Rounded features use eight segments per cycle; triangular features use two. Before the route start, the first grade extends backwards.",
            "Road features change grade load only: this is not suspension, tire lift, or airborne dynamics.",
        ],
    )


def _local_points(feature):
    if feature.kind == "points":
        return [(p.distance_m, p.elevation_m) for p in feature.points]
    if feature.kind in {"flat", "slope"}:
        return [
            (0, 0),
            (
                feature.length_m,
                feature.length_m * math.sin(feature.angle_rad)
                if feature.kind == "slope"
                else 0,
            ),
        ]
    count = feature.count if feature.kind == "whoops" else 1
    length = feature.spacing_m if feature.kind == "whoops" else feature.length_m
    height = feature.height_m * (-1 if feature.kind == "dip" else 1)
    samples = 8 if feature.shape == "rounded" else 2
    return [
        (i * length / samples, height * (1 - math.cos(2 * math.pi * i / samples)) / 2)
        for i in range(count * samples + 1)
    ]


def resolve_road(road: SpatialRoad, settings: Settings) -> RoadResolution:
    points, sections, segments = [], [], []
    distance, elevation = 0.0, 0.0
    if len(road.features) > settings.road_max_features:
        raise ApiProblem(422, "road_limit", "Too many road sections.")
    for feature in road.features:
        local = _local_points(feature)
        sections.append(
            {
                "feature_id": feature.id,
                "start_distance_m": distance,
                "start_elevation_m": elevation,
                "points": [{"distance_m": x, "elevation_m": y} for x, y in local],
            }
        )
        for (x, y), (nx, ny) in zip(local, local[1:]):
            ratio = (ny - y) / (nx - x)
            if abs(ratio) > math.sin(math.radians(settings.road_max_grade_degrees)):
                raise ApiProblem(
                    422,
                    "road_grade",
                    f"Section {feature.name or feature.kind} exceeds the {settings.road_max_grade_degrees:g}° grade limit.",
                )
            segments.append(
                {"start_distance_m": distance + x, "grade_angle_rad": math.asin(ratio)}
            )
            points.append({"distance_m": distance + x, "elevation_m": elevation + y})
        distance += local[-1][0]
        elevation += local[-1][1]
    points.append({"distance_m": distance, "elevation_m": elevation})
    if road.endpoint == "flat":
        segments.append({"start_distance_m": distance, "grade_angle_rad": 0})
    if (
        len(segments) > settings.road_max_segments
        or distance > settings.road_max_distance_m
    ):
        raise ApiProblem(
            422, "road_limit", "Road exceeds the configured segment or distance limit."
        )
    return RoadResolution(
        profile={"segments": segments},
        points=points,
        sections=sections,
        length_m=distance,
        minimum_elevation_m=min(p["elevation_m"] for p in points),
        maximum_elevation_m=max(p["elevation_m"] for p in points),
        maximum_absolute_grade_rad=max(abs(p["grade_angle_rad"]) for p in segments),
        warnings=[
            "Grade changes are abrupt at point joins. Use a sufficiently small maximum solver step for short features.",
            "After the route end: "
            + ("flat road." if road.endpoint == "flat" else "last grade continues."),
        ],
    )


def validate_scenario(scenario: ScenarioDocument, settings: Settings):
    if scenario.duration_s > settings.run_max_duration_seconds:
        raise ApiProblem(
            422,
            "duration_limit",
            f"Duration must not exceed {settings.run_max_duration_seconds:g} seconds.",
        )
    if (
        math.ceil(scenario.duration_s / scenario.execution.reporting_step_s) + 1
        > settings.run_max_report_samples
    ):
        raise ApiProblem(
            422, "report_limit", "Increase the reporting step or shorten the duration."
        )
    road = resolve_road(scenario.road, settings)
    if (
        scenario.stops.mode == "course"
        and scenario.initial.vehicle_distance_m >= road.length_m
    ):
        raise ApiProblem(
            422,
            "course_start",
            "Initial road distance must be before the course finish.",
        )
    return road


def apply_scenario(case, scenario: ScenarioDocument, settings: Settings):
    road = validate_scenario(scenario, settings)
    secondary = case["shaft_boundaries"]["secondary"]
    secondary["road_profile"] = road.profile.model_dump()
    # CINDER's rigid vehicle boundary derives distance from the secondary shaft.
    drive = secondary["final_drive"]
    case["host"] = {
        "kind": "secondary_shaft_angle",
        "initial_state": {
            "secondary_shaft_angle_rad": scenario.initial.vehicle_distance_m
            * drive["reduction_ratio"]
            / drive["wheel_radius_m"]
        },
    }
    case["scenario"] = {
        "time_span_s": [0, scenario.duration_s],
        "initial_cvt_state": scenario.initial.model_dump(
            exclude={"vehicle_distance_m"}
        ),
    }
    controls = scenario.execution
    case["execution"]["integrator"].update(
        relative_tolerance=controls.relative_tolerance,
        absolute_tolerance=controls.absolute_tolerance,
        max_step=controls.maximum_step_s,
        maximum_transitions=controls.maximum_transitions,
        retain_dense_output=False,
    )
    case["execution"]["reporting"]["grid"] = {
        "kind": "uniform_time_step",
        "step_seconds": controls.reporting_step_s,
        "count": None,
    }
    return road
