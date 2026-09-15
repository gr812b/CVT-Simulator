"""Packaging/workspace analysis for the fixed-pivot primary architecture.

This module intentionally contains no CINDER imports.  The service supplies the
requested physical ramp sampled by the CINDER adapter; this module owns only the
engineering-design geometry around it: reach, swept envelopes, polygonal
packaging constraints, and viewport data for the frontend.
"""

from __future__ import annotations

from math import cos, pi, sin

import numpy as np
from shapely.geometry import GeometryCollection, LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .models import ArchitectureDesign, PackagingZone

HALF_PI = 0.5 * pi


def analyze_architecture_workspace(
    architecture: ArchitectureDesign,
    zones: tuple[PackagingZone, ...],
    *,
    ramp_surface_open_x_m: tuple[float, ...],
    ramp_surface_open_r_m: tuple[float, ...],
    reach_sample_count: int = 361,
) -> dict[str, object]:
    """Return a frontend-ready architecture/packaging workspace.

    The flyweight envelope deliberately treats the arm as an infinitesimally
    thin rigid member and the roller at its true finite radius.  Zone clearance
    supplies the manufacturing/body margin without inventing an arm thickness.
    """

    _validate_architecture(architecture)
    if reach_sample_count < 91:
        raise ValueError("reach_sample_count must be at least 91.")
    if len(ramp_surface_open_x_m) != len(ramp_surface_open_r_m):
        raise ValueError("ramp surface x/r arrays must have the same length.")
    if len(ramp_surface_open_x_m) < 2:
        raise ValueError("ramp surface must contain at least two points.")

    zone_ids = [zone.id for zone in zones]
    if len(set(zone_ids)) != len(zone_ids):
        raise ValueError("packaging zone ids must be unique.")
    zone_geometries = tuple((_zone_polygon(zone), zone) for zone in zones)

    q_values = np.linspace(0.0, HALF_PI, reach_sample_count)
    center_x = np.asarray(
        [architecture.pivot_axial_position_m + architecture.arm_length_m * cos(float(q)) for q in q_values],
        dtype=float,
    )
    center_r = np.asarray(
        [architecture.pivot_radius_m + architecture.arm_length_m * sin(float(q)) for q in q_values],
        dtype=float,
    )

    flyweight_zones = tuple((polygon, zone) for polygon, zone in zone_geometries if zone.subject == "flyweight")

    def pose_valid(q: float) -> bool:
        pose = _flyweight_pose_geometry(architecture, q)
        return _subject_satisfies_zone_set(pose, flyweight_zones)

    admissible = tuple(bool(pose_valid(float(q))) for q in q_values)
    admissible_intervals = _admissible_intervals(tuple(float(q) for q in q_values), admissible, pose_valid)

    reach_line = LineString(tuple(zip(center_x.tolist(), center_r.tolist(), strict=True)))
    sector = Polygon(
        [
            (architecture.pivot_axial_position_m, architecture.pivot_radius_m),
            *tuple(zip(center_x.tolist(), center_r.tolist(), strict=True)),
            (architecture.pivot_axial_position_m, architecture.pivot_radius_m),
        ]
    )
    roller_sweep = reach_line.buffer(architecture.roller_radius_m, quad_segs=16)
    flyweight_sweep = unary_union((sector, roller_sweep))

    ramp_open = LineString(tuple(zip(ramp_surface_open_x_m, ramp_surface_open_r_m, strict=True)))
    ramp_full_points = tuple(
        (x + architecture.required_travel_m, r)
        for x, r in zip(ramp_surface_open_x_m, ramp_surface_open_r_m, strict=True)
    )
    ramp_full = LineString(ramp_full_points)
    ramp_sweep_polygon = Polygon(
        [
            *tuple(zip(ramp_surface_open_x_m, ramp_surface_open_r_m, strict=True)),
            *tuple(reversed(ramp_full_points)),
        ]
    )
    if not ramp_sweep_polygon.is_valid:
        ramp_sweep_polygon = ramp_sweep_polygon.buffer(0)
    ramp_subject: BaseGeometry = unary_union((ramp_open, ramp_full, ramp_sweep_polygon))

    zone_diagnostics: list[dict[str, object]] = []
    ramp_zones = tuple((polygon, zone) for polygon, zone in zone_geometries if zone.subject == "ramp")
    ramp_zones_valid = _subject_satisfies_zone_set(ramp_subject, ramp_zones)
    for polygon, zone in zone_geometries:
        if zone.subject == "flyweight":
            single_valid = tuple(
                _subject_satisfies_zone(
                    _flyweight_pose_geometry(architecture, float(q)),
                    polygon,
                    zone,
                )
                for q in q_values
            )
            intervals = _admissible_intervals(
                tuple(float(q) for q in q_values),
                single_valid,
                lambda q, poly=polygon, item=zone: _subject_satisfies_zone(
                    _flyweight_pose_geometry(architecture, q), poly, item
                ),
            )
            if all(single_valid):
                status = "pass"
            elif any(single_valid):
                status = "restricts"
            else:
                status = "blocks"
            zone_diagnostics.append(
                {
                    "zone_id": zone.id,
                    "label": zone.label,
                    "subject": zone.subject,
                    "rule": zone.rule,
                    "status": status,
                    "admissible_intervals_deg": [
                        [interval[0] * 180.0 / pi, interval[1] * 180.0 / pi]
                        for interval in intervals
                    ],
                }
            )
        else:
            satisfied = _subject_satisfies_zone(ramp_subject, polygon, zone)
            zone_diagnostics.append(
                {
                    "zone_id": zone.id,
                    "label": zone.label,
                    "subject": zone.subject,
                    "rule": zone.rule,
                    "status": "pass" if satisfied else "violation",
                    "admissible_intervals_deg": [],
                }
            )

    findings: list[dict[str, object]] = []
    if not any(admissible):
        findings.append(
            {
                "severity": "error",
                "code": "NO_ADMISSIBLE_FLYWEIGHT_POSE",
                "message": "Packaging zones exclude every flyweight pose between q = 0° and q = 90°.",
            }
        )
    if not ramp_zones_valid:
        findings.append(
            {
                "severity": "warning",
                "code": "CURRENT_RAMP_PACKAGING_VIOLATION",
                "message": "The currently overlaid ramp sweep violates at least one ramp packaging zone.",
            }
        )

    viewport_geometry = unary_union(
        tuple(
            geometry
            for geometry in (
                flyweight_sweep,
                ramp_subject,
                *(polygon for polygon, _zone in zone_geometries),
            )
            if not geometry.is_empty
        )
    )
    min_x, min_r, max_x, max_r = viewport_geometry.bounds
    span = max(max_x - min_x, max_r - min_r, 0.050)
    pad = max(0.010, 0.12 * span)

    manipulator_q = pi / 4.0
    manipulator_endpoint = (
        architecture.pivot_axial_position_m + architecture.arm_length_m * cos(manipulator_q),
        architecture.pivot_radius_m + architecture.arm_length_m * sin(manipulator_q),
    )
    q90_endpoint = (
        architecture.pivot_axial_position_m,
        architecture.pivot_radius_m + architecture.arm_length_m,
    )

    return {
        "validity": {
            "valid": any(admissible),
            "current_ramp_packaging_valid": ramp_zones_valid,
            "findings": findings,
        },
        "reach": {
            "q_deg": [float(q * 180.0 / pi) for q in q_values],
            "roller_center_x_m": center_x.tolist(),
            "roller_center_r_m": center_r.tolist(),
            "admissible": list(admissible),
            "admissible_intervals_deg": [
                [interval[0] * 180.0 / pi, interval[1] * 180.0 / pi]
                for interval in admissible_intervals
            ],
        },
        "envelopes": {
            "flyweight_swept": _geometry_polygons(flyweight_sweep),
            "ramp_swept": _geometry_polygons(ramp_sweep_polygon),
        },
        "ramp_surface": {
            "open": {
                "x_m": list(ramp_surface_open_x_m),
                "r_m": list(ramp_surface_open_r_m),
            },
            "full_shift": {
                "x_m": [point[0] for point in ramp_full_points],
                "r_m": [point[1] for point in ramp_full_points],
            },
        },
        "zone_diagnostics": zone_diagnostics,
        "manipulators": {
            "arm_endpoint_x_m": manipulator_endpoint[0],
            "arm_endpoint_r_m": manipulator_endpoint[1],
            "arm_direction_x": cos(manipulator_q),
            "arm_direction_r": sin(manipulator_q),
            "q90_endpoint_x_m": q90_endpoint[0],
            "q90_endpoint_r_m": q90_endpoint[1],
        },
        "viewport": {
            "x_min_m": min_x - pad,
            "x_max_m": max_x + pad,
            "r_min_m": max(0.0, min_r - pad),
            "r_max_m": max_r + pad,
        },
        "summary": {
            "admissible_fraction": sum(1 for item in admissible if item) / len(admissible),
            "admissible_interval_count": len(admissible_intervals),
            "zone_count": len(zones),
            "ramp_zone_count": sum(1 for zone in zones if zone.subject == "ramp"),
            "flyweight_zone_count": sum(1 for zone in zones if zone.subject == "flyweight"),
        },
    }


def _flyweight_pose_geometry(architecture: ArchitectureDesign, q: float) -> BaseGeometry:
    px = architecture.pivot_axial_position_m
    pr = architecture.pivot_radius_m
    rx = px + architecture.arm_length_m * cos(q)
    rr = pr + architecture.arm_length_m * sin(q)
    arm = LineString(((px, pr), (rx, rr)))
    roller = Point(rx, rr).buffer(architecture.roller_radius_m, quad_segs=16)
    return unary_union((arm, roller))


def _subject_satisfies_zone_set(
    subject: BaseGeometry,
    zone_geometries: tuple[tuple[Polygon, PackagingZone], ...],
) -> bool:
    """Apply keep-outs conjunctively and allowed regions as one union.

    Multiple allowed polygons for one subject describe alternative pockets in
    the package, not an impossible requirement to live inside every polygon at
    once.  Each zone's clearance is applied before the allowed union is built.
    """

    forbid = tuple((polygon, zone) for polygon, zone in zone_geometries if zone.rule == "forbid")
    for polygon, zone in forbid:
        barrier = polygon.buffer(zone.clearance_m, quad_segs=12)
        if subject.intersects(barrier):
            return False

    allowed_parts: list[BaseGeometry] = []
    for polygon, zone in zone_geometries:
        if zone.rule != "contain":
            continue
        allowed = polygon.buffer(-zone.clearance_m, quad_segs=12)
        if not allowed.is_empty:
            allowed_parts.append(allowed)
    if not allowed_parts:
        return not any(zone.rule == "contain" for _polygon, zone in zone_geometries)
    return unary_union(tuple(allowed_parts)).covers(subject)


def _subject_satisfies_zone(subject: BaseGeometry, polygon: Polygon, zone: PackagingZone) -> bool:
    if zone.rule == "forbid":
        barrier: BaseGeometry = polygon.buffer(zone.clearance_m, quad_segs=12)
        return not subject.intersects(barrier)

    allowed: BaseGeometry = polygon.buffer(-zone.clearance_m, quad_segs=12)
    return (not allowed.is_empty) and allowed.covers(subject)


def _admissible_intervals(
    q_values: tuple[float, ...],
    mask: tuple[bool, ...],
    predicate,
) -> tuple[tuple[float, float], ...]:
    if len(q_values) != len(mask) or not q_values:
        return ()

    boundaries: list[tuple[float, bool]] = [(q_values[0], mask[0])]
    for left_q, right_q, left_ok, right_ok in zip(
        q_values[:-1], q_values[1:], mask[:-1], mask[1:], strict=True
    ):
        if left_ok == right_ok:
            continue
        lo = left_q
        hi = right_q
        lo_ok = left_ok
        for _ in range(48):
            mid = 0.5 * (lo + hi)
            mid_ok = bool(predicate(mid))
            if mid_ok == lo_ok:
                lo = mid
            else:
                hi = mid
        boundary = 0.5 * (lo + hi)
        boundaries.append((boundary, right_ok))
    boundaries.append((q_values[-1], mask[-1]))

    intervals: list[tuple[float, float]] = []
    current_start: float | None = q_values[0] if mask[0] else None
    for q, becomes_ok in boundaries[1:-1]:
        if becomes_ok:
            current_start = q
        elif current_start is not None:
            intervals.append((current_start, q))
            current_start = None
    if current_start is not None:
        intervals.append((current_start, q_values[-1]))
    return tuple(intervals)


def _zone_polygon(zone: PackagingZone) -> Polygon:
    if not zone.id.strip():
        raise ValueError("packaging zone id must be non-empty.")
    if not zone.label.strip():
        raise ValueError("packaging zone label must be non-empty.")
    if zone.subject not in ("flyweight", "ramp"):
        raise ValueError("packaging zone subject must be 'flyweight' or 'ramp'.")
    if zone.rule not in ("forbid", "contain"):
        raise ValueError("packaging zone rule must be 'forbid' or 'contain'.")
    if zone.clearance_m < 0.0:
        raise ValueError("packaging zone clearance_m must be non-negative.")
    if len(zone.polygon_m) < 3:
        raise ValueError(f"packaging zone {zone.label!r} needs at least three vertices.")
    polygon = Polygon(zone.polygon_m)
    if polygon.is_empty or polygon.area <= 0.0:
        raise ValueError(f"packaging zone {zone.label!r} has zero area.")
    if not polygon.is_valid:
        raise ValueError(
            f"packaging zone {zone.label!r} is self-intersecting or otherwise invalid."
        )
    return polygon


def _geometry_polygons(geometry: BaseGeometry) -> list[dict[str, list[float]]]:
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Polygon":
        polygons = (geometry,)
    elif geometry.geom_type == "MultiPolygon":
        polygons = tuple(geometry.geoms)
    elif isinstance(geometry, GeometryCollection):
        polygons = tuple(item for item in geometry.geoms if item.geom_type == "Polygon")
    else:
        buffered = geometry.buffer(1.0e-9)
        polygons = (buffered,) if buffered.geom_type == "Polygon" else tuple(buffered.geoms)

    result: list[dict[str, list[float]]] = []
    for polygon in polygons:
        coordinates = list(polygon.exterior.coords)
        result.append(
            {
                "x_m": [float(point[0]) for point in coordinates],
                "r_m": [float(point[1]) for point in coordinates],
            }
        )
    return result


def _validate_architecture(architecture: ArchitectureDesign) -> None:
    for name, value in (
        ("pivot_radius_m", architecture.pivot_radius_m),
        ("arm_length_m", architecture.arm_length_m),
        ("roller_radius_m", architecture.roller_radius_m),
        ("required_travel_m", architecture.required_travel_m),
    ):
        if value <= 0.0:
            raise ValueError(f"{name} must be positive.")
    if architecture.number_of_flyweights <= 0:
        raise ValueError("number_of_flyweights must be positive.")
    if architecture.arm_mass_per_flyweight_kg < 0.0:
        raise ValueError("arm_mass_per_flyweight_kg must be non-negative.")
    if architecture.max_tip_mass_per_flyweight_kg < 0.0:
        raise ValueError("max_tip_mass_per_flyweight_kg must be non-negative.")
