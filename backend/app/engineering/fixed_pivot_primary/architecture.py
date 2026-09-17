"""Architecture-level workspace analysis for the fixed-pivot primary.

No CINDER imports live here.  This module answers the purely architectural
question: given the fixed pivot, arm, roller, required sheave travel and
packaging zones, where can the roller centre and a possible physical ramp
surface exist before any concrete ramp law is chosen?

The moving-ramp/sheave frame is used throughout.  At zero shift the pivot is at
``pivot_axial_position_m``.  As the sheave closes by ``x``, that stationary
pivot appears at ``pivot_axial_position_m - x`` in this frame.  The architecture
angle range is intentionally broader than the normal operating range:
``-30 deg <= q <= 90 deg``.  The lower limit is a packaging/design bound; the
90 degree upper limit is the hard flyweight deployment limit.
"""

from __future__ import annotations

from math import cos, pi, sin

import numpy as np
from shapely import affinity
from shapely.geometry import GeometryCollection, LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .models import ArchitectureDesign, PackagingZone

Q_MIN_RAD = -pi / 6.0
Q_MAX_RAD = 0.5 * pi
Q_MIN_DEG = -30.0
Q_MAX_DEG = 90.0


def analyze_architecture_workspace(
    architecture: ArchitectureDesign,
    zones: tuple[PackagingZone, ...],
    *,
    reach_sample_count: int = 361,
    shift_sample_count: int = 41,
) -> dict[str, object]:
    """Return the full-travel architecture and packaging workspace.

    The result deliberately contains no concrete ramp.  The potential ramp
    surface workspace is the one-sided finite-roller offset of the complete
    roller-centre workspace for positive ramp tangents (0..90 deg), using the
    same roller side and axial-direction convention as the CINDER mechanism.
    It is a geometric opportunity region, not yet the Phase-3 CINDER-admissible
    ramp corridor.
    """

    _validate_architecture(architecture)
    if reach_sample_count < 91:
        raise ValueError("reach_sample_count must be at least 91.")
    if shift_sample_count < 9:
        raise ValueError("shift_sample_count must be at least 9.")

    zone_ids = [zone.id for zone in zones]
    if len(set(zone_ids)) != len(zone_ids):
        raise ValueError("packaging zone ids must be unique.")
    zone_geometries = tuple((_zone_polygon(zone), zone) for zone in zones)
    flyweight_zones = tuple(
        (polygon, zone) for polygon, zone in zone_geometries if zone.subject == "flyweight"
    )
    ramp_zones = tuple(
        (polygon, zone) for polygon, zone in zone_geometries if zone.subject == "ramp"
    )

    q_values = np.linspace(Q_MIN_RAD, Q_MAX_RAD, reach_sample_count)
    shift_values = np.linspace(0.0, architecture.required_travel_m, shift_sample_count)

    # Two arm arcs bound the full roller-centre workspace in the moving-sheave
    # frame.  Sweeping q across the interval and shift across [0, X] fills the
    # region between these arcs.
    open_arc = _roller_center_arc(architecture, q_values, shift_m=0.0)
    full_arc = _roller_center_arc(
        architecture,
        q_values,
        shift_m=architecture.required_travel_m,
    )
    roller_center_workspace = Polygon([*open_arc, *tuple(reversed(full_arc))])
    if not roller_center_workspace.is_valid:
        roller_center_workspace = roller_center_workspace.buffer(0)

    # The possible physical ramp surface at one shift is the image of two
    # independent continuous parameters: flyweight angle q and local ramp
    # tangent angle alpha.  That image can fold over itself, so constructing a
    # polygon from only the mapped outer parameter boundary is incorrect: a
    # self-intersection can make polygon repair discard a legitimate lobe
    # (most visibly the region approaching q = 90 deg).  Tessellate the
    # parameter domain instead and union the mapped cells.
    open_ramp_slice = _ramp_surface_slice_workspace(architecture, q_values, shift_m=0.0)
    potential_ramp_workspace = _sweep_geometry_x(open_ramp_slice, -architecture.required_travel_m)
    feasible_ramp_workspace = _clip_subject_workspace(
        potential_ramp_workspace,
        ramp_zones,
    )

    # Flyweight packaging is still audited across the full q x travel domain,
    # but the architecture UI no longer exposes a single-shift slice view.
    admitted_pose_count = 0
    total_pose_count = len(q_values) * len(shift_values)
    for raw_shift in shift_values:
        shift = float(raw_shift)
        admitted_pose_count += sum(
            1
            for q in q_values
            if _subject_satisfies_zone_set(
                _flyweight_pose_geometry(architecture, float(q), shift),
                flyweight_zones,
            )
        )

    zone_diagnostics = _zone_diagnostics(
        architecture,
        q_values,
        shift_values,
        zone_geometries,
        potential_ramp_workspace,
    )

    findings: list[dict[str, object]] = []
    if admitted_pose_count == 0:
        findings.append(
            {
                "severity": "error",
                "code": "NO_ADMISSIBLE_FLYWEIGHT_POSE",
                "message": (
                    "Packaging zones exclude every sampled flyweight pose over "
                    "the full -30° to 90° architecture range and required travel."
                ),
            }
        )
    if feasible_ramp_workspace.is_empty:
        findings.append(
            {
                "severity": "error",
                "code": "NO_PACKAGING_FEASIBLE_RAMP_WORKSPACE",
                "message": (
                    "Ramp packaging zones remove the entire geometrically "
                    "reachable ramp-surface workspace."
                ),
            }
        )

    q_min_flat = _flat_limit_line(architecture, Q_MIN_RAD)
    q_max_flat = _flat_limit_line(architecture, Q_MAX_RAD)

    viewport_geometry = unary_union(
        tuple(
            geometry
            for geometry in (
                potential_ramp_workspace,
                roller_center_workspace,
                *(polygon for polygon, _zone in zone_geometries),
            )
            if not geometry.is_empty
        )
    )
    min_x, min_r, max_x, max_r = viewport_geometry.bounds
    span = max(max_x - min_x, max_r - min_r, 0.050)
    pad = max(0.010, 0.12 * span)

    full_shift_pivot_x = architecture.pivot_axial_position_m - architecture.required_travel_m

    ramp_fraction = (
        feasible_ramp_workspace.area / potential_ramp_workspace.area
        if potential_ramp_workspace.area > 0.0
        else 0.0
    )

    return {
        "validity": {
            "valid": not any(item["severity"] == "error" for item in findings),
            "findings": findings,
        },
        "limits": {
            "q_min_deg": Q_MIN_DEG,
            "q_max_deg": Q_MAX_DEG,
        },
        "workspace": {
            "roller_center": _geometry_polygons(roller_center_workspace),
            "potential_ramp_surface": _geometry_polygons(potential_ramp_workspace),
            "packaging_feasible_ramp_surface": _geometry_polygons(feasible_ramp_workspace),
            "open_roller_arc": _polyline_document(open_arc),
            "full_shift_roller_arc": _polyline_document(full_arc),
        },
        "boundaries": {
            "q_min_flat_ramp": _polyline_document(q_min_flat),
            "q_max_flat_ramp": _polyline_document(q_max_flat),
            "pivot_travel": {
                "x_m": [
                    architecture.pivot_axial_position_m,
                    full_shift_pivot_x,
                ],
                "r_m": [architecture.pivot_radius_m, architecture.pivot_radius_m],
            },
        },
        "zone_diagnostics": zone_diagnostics,
        "viewport": {
            "x_min_m": min_x - pad,
            "x_max_m": max_x + pad,
            "r_min_m": max(0.0, min_r - pad),
            "r_max_m": max_r + pad,
        },
        "summary": {
            "admissible_pose_fraction": admitted_pose_count / total_pose_count,
            "ramp_workspace_fraction": ramp_fraction,
            "zone_count": len(zones),
            "ramp_zone_count": sum(1 for zone in zones if zone.subject == "ramp"),
            "flyweight_zone_count": sum(1 for zone in zones if zone.subject == "flyweight"),
            "shift_sample_count": len(shift_values),
            "q_sample_count": len(q_values),
        },
    }


def _roller_center(
    architecture: ArchitectureDesign,
    q: float,
    *,
    shift_m: float,
) -> tuple[float, float]:
    pivot_x = architecture.pivot_axial_position_m - shift_m
    return (
        pivot_x + architecture.arm_length_m * cos(q),
        architecture.pivot_radius_m + architecture.arm_length_m * sin(q),
    )


def _roller_center_arc(
    architecture: ArchitectureDesign,
    q_values: np.ndarray,
    shift_m: float,
) -> tuple[tuple[float, float], ...]:
    return tuple(_roller_center(architecture, float(q), shift_m=shift_m) for q in q_values)


def _flyweight_pose_geometry(
    architecture: ArchitectureDesign,
    q: float,
    shift_m: float,
) -> BaseGeometry:
    px = architecture.pivot_axial_position_m - shift_m
    pr = architecture.pivot_radius_m
    rx, rr = _roller_center(architecture, q, shift_m=shift_m)
    arm = LineString(((px, pr), (rx, rr)))
    roller = Point(rx, rr).buffer(architecture.roller_radius_m, quad_segs=16)
    return unary_union((arm, roller))


def _ramp_surface_slice_workspace(
    architecture: ArchitectureDesign,
    q_values: np.ndarray,
    *,
    shift_m: float,
) -> BaseGeometry:
    """Return every geometrically reachable physical ramp-surface point.

    At a fixed shift the finite roller centre follows the arm arc ``q``. For
    any positive physical ramp tangent, ``alpha in [0, pi/2]``, the contact
    point is one roller radius away on the CINDER-selected roller side. The
    map ``(q, alpha) -> contact point`` can fold over itself, so its image must
    not be reconstructed from only the mapped perimeter.

    Tessellating the compact parameter domain and unioning the mapped cells
    preserves both exact endpoint limits, including the q = 90 degree flat
    ramp boundary. This is architecture geometry only; Phase 3 still decides
    which complete ramp curves are mechanically admissible.
    """

    q_count = min(max(121, int(q_values.size)), 181)
    q_mesh = np.linspace(float(q_values[0]), float(q_values[-1]), q_count)
    alpha_mesh = np.linspace(0.0, 0.5 * pi, 41)

    sign = float(architecture.roller_side_sign)
    direction = float(architecture.ramp_axial_direction)
    roller = architecture.roller_radius_m

    rows: list[list[tuple[float, float]]] = []
    for raw_q in q_mesh:
        center_x, center_r = _roller_center(architecture, float(raw_q), shift_m=shift_m)
        row: list[tuple[float, float]] = []
        for raw_alpha in alpha_mesh:
            alpha = float(raw_alpha)
            # CINDER: roller centre = surface + R*n, with
            # n=(-sign*sin(alpha), sign*direction*cos(alpha)).
            row.append(
                (
                    center_x + sign * roller * sin(alpha),
                    center_r - sign * direction * roller * cos(alpha),
                )
            )
        rows.append(row)

    cells: list[BaseGeometry] = []
    for q_index in range(len(rows) - 1):
        lower = rows[q_index]
        upper = rows[q_index + 1]
        for alpha_index in range(len(alpha_mesh) - 1):
            cell = Polygon(
                (
                    lower[alpha_index],
                    upper[alpha_index],
                    upper[alpha_index + 1],
                    lower[alpha_index + 1],
                )
            )
            if not cell.is_valid:
                cell = cell.buffer(0)
            if not cell.is_empty and cell.area > 1.0e-18:
                cells.append(cell)

    if not cells:
        return GeometryCollection()
    return unary_union(tuple(cells)).buffer(0)


def _sweep_geometry_x(geometry: BaseGeometry, delta_x: float) -> BaseGeometry:
    """Exact union of a polygonal geometry translated continuously in x."""

    if geometry.is_empty or abs(delta_x) <= 1.0e-15:
        return geometry
    if geometry.geom_type == "Polygon":
        polygons = (geometry,)
    elif geometry.geom_type == "MultiPolygon":
        polygons = tuple(geometry.geoms)
    else:
        polygons = tuple(
            item for item in getattr(geometry, "geoms", ()) if item.geom_type == "Polygon"
        )
    swept = [_sweep_polygon_x(polygon, delta_x) for polygon in polygons]
    return unary_union(tuple(swept)) if swept else GeometryCollection()


def _sweep_polygon_x(polygon: Polygon, delta_x: float) -> BaseGeometry:
    moved = affinity.translate(polygon, xoff=delta_x, yoff=0.0)
    pieces: list[BaseGeometry] = [polygon, moved]
    coordinates = list(polygon.exterior.coords)
    for first, second in zip(coordinates[:-1], coordinates[1:], strict=True):
        strip = Polygon(
            (
                first,
                second,
                (second[0] + delta_x, second[1]),
                (first[0] + delta_x, first[1]),
            )
        )
        if not strip.is_empty and strip.area > 0.0:
            pieces.append(strip)
    return unary_union(tuple(pieces)).buffer(0)


def _flat_limit_line(
    architecture: ArchitectureDesign,
    q: float,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Physical flat-ramp limiting line at one fixed flyweight angle."""

    sign = float(architecture.roller_side_sign)
    direction = float(architecture.ramp_axial_direction)
    radial_offset = -sign * direction * architecture.roller_radius_m
    open_center = _roller_center(architecture, q, shift_m=0.0)
    full_center = _roller_center(
        architecture,
        q,
        shift_m=architecture.required_travel_m,
    )
    return (
        (open_center[0], open_center[1] + radial_offset),
        (full_center[0], full_center[1] + radial_offset),
    )


def _clip_subject_workspace(
    workspace: BaseGeometry,
    zone_geometries: tuple[tuple[Polygon, PackagingZone], ...],
) -> BaseGeometry:
    result = workspace
    for polygon, zone in zone_geometries:
        if zone.rule != "forbid":
            continue
        result = result.difference(polygon.buffer(zone.clearance_m, quad_segs=12))

    allowed_parts: list[BaseGeometry] = []
    has_contain = False
    for polygon, zone in zone_geometries:
        if zone.rule != "contain":
            continue
        has_contain = True
        allowed = polygon.buffer(-zone.clearance_m, quad_segs=12)
        if not allowed.is_empty:
            allowed_parts.append(allowed)
    if has_contain:
        if not allowed_parts:
            return GeometryCollection()
        result = result.intersection(unary_union(tuple(allowed_parts)))
    return result.buffer(0) if not result.is_empty else result


def _subject_satisfies_zone_set(
    subject: BaseGeometry,
    zone_geometries: tuple[tuple[Polygon, PackagingZone], ...],
) -> bool:
    for polygon, zone in zone_geometries:
        if zone.rule == "forbid":
            barrier = polygon.buffer(zone.clearance_m, quad_segs=12)
            if subject.intersects(barrier):
                return False

    allowed_parts: list[BaseGeometry] = []
    has_contain = False
    for polygon, zone in zone_geometries:
        if zone.rule != "contain":
            continue
        has_contain = True
        allowed = polygon.buffer(-zone.clearance_m, quad_segs=12)
        if not allowed.is_empty:
            allowed_parts.append(allowed)
    if not has_contain:
        return True
    if not allowed_parts:
        return False
    return unary_union(tuple(allowed_parts)).covers(subject)


def _subject_satisfies_zone(
    subject: BaseGeometry,
    polygon: Polygon,
    zone: PackagingZone,
) -> bool:
    if zone.rule == "forbid":
        return not subject.intersects(polygon.buffer(zone.clearance_m, quad_segs=12))
    allowed = polygon.buffer(-zone.clearance_m, quad_segs=12)
    return (not allowed.is_empty) and allowed.covers(subject)


def _zone_diagnostics(
    architecture: ArchitectureDesign,
    q_values: np.ndarray,
    shift_values: np.ndarray,
    zone_geometries: tuple[tuple[Polygon, PackagingZone], ...],
    potential_ramp_workspace: BaseGeometry,
) -> list[dict[str, object]]:
    diagnostics: list[dict[str, object]] = []
    for polygon, zone in zone_geometries:
        if zone.subject == "flyweight":
            checks = [
                _subject_satisfies_zone(
                    _flyweight_pose_geometry(architecture, float(q), float(shift)),
                    polygon,
                    zone,
                )
                for shift in shift_values
                for q in q_values
            ]
            if all(checks):
                status = "pass"
            elif any(checks):
                status = "restricts"
            else:
                status = "blocks"
            diagnostics.append(
                {
                    "zone_id": zone.id,
                    "label": zone.label,
                    "subject": zone.subject,
                    "rule": zone.rule,
                    "status": status,
                    "retained_fraction": sum(1 for ok in checks if ok) / len(checks),
                }
            )
            continue

        clipped = _clip_subject_workspace(potential_ramp_workspace, ((polygon, zone),))
        base_area = potential_ramp_workspace.area
        fraction = clipped.area / base_area if base_area > 0.0 else 0.0
        if fraction >= 1.0 - 1.0e-9:
            status = "pass"
        elif fraction > 1.0e-12:
            status = "restricts"
        else:
            status = "blocks"
        diagnostics.append(
            {
                "zone_id": zone.id,
                "label": zone.label,
                "subject": zone.subject,
                "rule": zone.rule,
                "status": status,
                "retained_fraction": fraction,
            }
        )
    return diagnostics


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


def _polyline_document(points: tuple[tuple[float, float], ...]) -> dict[str, list[float]]:
    return {
        "x_m": [float(point[0]) for point in points],
        "r_m": [float(point[1]) for point in points],
    }


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
        if buffered.geom_type == "Polygon":
            polygons = (buffered,)
        elif buffered.geom_type == "MultiPolygon":
            polygons = tuple(buffered.geoms)
        else:
            polygons = ()

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
    if architecture.ramp_axial_direction not in (-1, 1):
        raise ValueError("ramp_axial_direction must be -1 or +1.")
    if architecture.roller_side_sign not in (-1, 1):
        raise ValueError("roller_side_sign must be -1 or +1.")
