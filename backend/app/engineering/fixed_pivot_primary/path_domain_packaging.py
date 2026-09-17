"""Cached packaging masks for the fixed-pivot path-domain graph.

The expensive local Hermite mechanics do not depend on user packaging zones.
This module therefore caches the no-zone base graph for one architecture and
applies packaging as an edge mask afterwards.  The packaging predicate keeps
exactly the same sampled-geometry semantics as the original implementation but
avoids repeated unary unions of dozens of arm/roller geometries.
"""

from __future__ import annotations

from copy import deepcopy
from math import isfinite

import numpy as np
from shapely.geometry import LineString, Point, Polygon

from .models import ArchitectureDesign, PackagingZone
from .path_domain import (
    CompiledPathDomain,
    LayerEdge,
    PathSegment,
    _forward_backward_viability,
    _geometry_from_q,
    _hermite_q_derivatives,
    _physical_domain_projection,
    _station_projection,
    compile_path_domain,
)

_BASE_GRAPH_CACHE: dict[tuple[object, ...], CompiledPathDomain] = {}
_PACKAGED_GRAPH_CACHE: dict[tuple[object, ...], CompiledPathDomain] = {}


def _architecture_key(value: ArchitectureDesign) -> tuple[object, ...]:
    return (
        round(value.pivot_axial_position_m, 12),
        round(value.pivot_radius_m, 12),
        round(value.arm_length_m, 12),
        round(value.roller_radius_m, 12),
        round(value.required_travel_m, 12),
        int(value.number_of_flyweights),
        round(value.arm_mass_per_flyweight_kg, 12),
        int(value.ramp_axial_direction),
        int(value.roller_side_sign),
        round(value.max_tip_mass_per_flyweight_kg, 12),
    )


def _zone_key(zones: tuple[PackagingZone, ...]) -> tuple[object, ...]:
    return tuple(
        (
            zone.id,
            zone.subject,
            zone.rule,
            round(zone.clearance_m, 12),
            tuple((round(x, 12), round(r, 12)) for x, r in zone.polygon_m),
        )
        for zone in zones
    )


def compile_path_domain_cached_packaging(
    architecture: ArchitectureDesign,
    zones: tuple[PackagingZone, ...],
    *,
    shift_station_count: int = 9,
    q_sample_count: int = 61,
    alpha_sample_count: int = 7,
    representative_path_count: int = 8,
    edge_audit_sample_count: int = 65,
    history_trace_sample_count: int = 65,
) -> CompiledPathDomain:
    """Compile once without zones, then apply zones as a cached edge mask."""

    numeric_key = (
        _architecture_key(architecture),
        int(shift_station_count),
        int(q_sample_count),
        int(alpha_sample_count),
        int(representative_path_count),
        int(edge_audit_sample_count),
        int(history_trace_sample_count),
    )
    base = _BASE_GRAPH_CACHE.get(numeric_key)
    if base is None:
        base = compile_path_domain(
            architecture,
            (),
            shift_station_count=shift_station_count,
            q_sample_count=q_sample_count,
            alpha_sample_count=alpha_sample_count,
            representative_path_count=representative_path_count,
            edge_audit_sample_count=edge_audit_sample_count,
            history_trace_sample_count=history_trace_sample_count,
        )
        _BASE_GRAPH_CACHE[numeric_key] = base

    if not zones:
        return base

    packaged_key = numeric_key + (_zone_key(zones),)
    cached = _PACKAGED_GRAPH_CACHE.get(packaged_key)
    if cached is not None:
        return cached

    prepared = _prepare_fast_zones(zones, architecture.roller_radius_m)
    dx = architecture.required_travel_m / (shift_station_count - 1)
    masked_layers: list[list[LayerEdge]] = []
    for layer_index, edges in enumerate(base.viable_edges):
        x0 = layer_index * dx
        kept: list[LayerEdge] = []
        for edge in edges:
            template = base.templates[edge.template_index]
            segment = PathSegment(
                x0_m=x0,
                x1_m=x0 + dx,
                q0_rad=template.q0_rad,
                q1_rad=template.q1_rad,
                m0_rad_per_m=template.m0_rad_per_m,
                m1_rad_per_m=template.m1_rad_per_m,
            )
            if _segment_satisfies_packaging_fast(architecture, segment, prepared):
                kept.append(edge)
        masked_layers.append(kept)

    viable_edges, viable_nodes = _forward_backward_viability(
        masked_layers,
        len(base.states),
        shift_station_count,
    )
    document = deepcopy(base.document)
    document["validity"] = {
        "valid": bool(viable_nodes and viable_nodes[0]),
        "findings": (
            []
            if viable_nodes and viable_nodes[0]
            else [
                {
                    "severity": "error",
                    "code": "NO_COMPLETE_PATH",
                    "message": "The packaging mask removes every complete start-to-finish path.",
                }
            ]
        ),
    }
    graph = document.get("graph")
    if isinstance(graph, dict):
        graph["layer_edge_counts"] = [len(row) for row in masked_layers]
        graph["viable_layer_edge_counts"] = [len(row) for row in viable_edges]
        graph["viable_node_counts"] = [len(row) for row in viable_nodes]
        graph["station_projection"] = _station_projection(
            viable_nodes, base.states, shift_station_count
        )
        graph["packaging_reused_base_graph"] = True
    document["representative_paths"] = []
    document["domain_projection"] = _physical_domain_projection(
        architecture,
        viable_nodes,
        base.states,
        shift_station_count,
        q_sample_count=q_sample_count,
        alpha_sample_count=alpha_sample_count,
    )
    numerics = document.get("numerics")
    if isinstance(numerics, dict):
        # The copied base document may already have refined-view cache markers.
        # Packaging changed the graph, so those views must be rebuilt once for
        # this mask before they can be cached again.
        numerics.pop("refined_views_representative_count", None)
        numerics.pop("capability_samples_per_layer", None)
        numerics["packaging_edge_mask_cached"] = True
        numerics["packaging_pose_samples"] = 33

    surviving_representative_paths: list[tuple[int, ...]] = []
    surviving_representative_documents: list[dict[str, object]] = []
    edge_pairs = [{(edge.start_state, edge.end_state) for edge in row} for row in viable_edges]
    for state_path, representative_document in zip(
        base.representative_state_paths,
        base.representative_documents,
        strict=True,
    ):
        if all(
            (state_path[layer], state_path[layer + 1]) in edge_pairs[layer]
            for layer in range(shift_station_count - 1)
        ):
            surviving_representative_paths.append(tuple(state_path))
            surviving_representative_documents.append(representative_document)

    compiled = CompiledPathDomain(
        architecture=architecture,
        zones=zones,
        states=base.states,
        templates=base.templates,
        viable_edges=tuple(tuple(row) for row in viable_edges),
        viable_nodes=tuple(frozenset(row) for row in viable_nodes),
        shift_station_count=shift_station_count,
        q_sample_count=q_sample_count,
        alpha_sample_count=alpha_sample_count,
        edge_audit_sample_count=edge_audit_sample_count,
        history_trace_sample_count=history_trace_sample_count,
        representative_state_paths=tuple(surviving_representative_paths),
        representative_documents=tuple(surviving_representative_documents),
        document=document,
    )
    _PACKAGED_GRAPH_CACHE[packaged_key] = compiled
    return compiled


def _prepare_fast_zones(
    zones: tuple[PackagingZone, ...],
    roller_radius_m: float,
) -> tuple[dict[str, object], ...]:
    prepared: list[dict[str, object]] = []
    for zone in zones:
        polygon = Polygon(zone.polygon_m)
        if polygon.is_empty or not polygon.is_valid or polygon.area <= 0.0:
            raise ValueError(f"packaging zone {zone.label!r} is invalid")
        if zone.rule == "forbid":
            barrier = polygon.buffer(zone.clearance_m, quad_segs=8)
            prepared.append(
                {
                    "zone": zone,
                    "surface": barrier,
                    "roller_surface": barrier,
                    "bounds": barrier.bounds,
                }
            )
        else:
            allowed = polygon.buffer(-zone.clearance_m, quad_segs=8)
            roller_allowed = (
                allowed.buffer(-roller_radius_m, quad_segs=8) if not allowed.is_empty else allowed
            )
            prepared.append(
                {
                    "zone": zone,
                    "surface": allowed,
                    "roller_surface": roller_allowed,
                    "bounds": allowed.bounds if not allowed.is_empty else (0.0, 0.0, 0.0, 0.0),
                }
            )
    return tuple(prepared)


def _bbox_disjoint(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float], pad: float = 0.0
) -> bool:
    return a[2] + pad < b[0] or b[2] + pad < a[0] or a[3] + pad < b[1] or b[3] + pad < a[1]


def _segment_subject_bounds(
    architecture: ArchitectureDesign,
    segment: PathSegment,
) -> tuple[tuple[float, float, float, float], tuple[float, float, float, float]]:
    """Conservative ramp/flyweight bounds without sampling the finite-roller path.

    Every retained local graph edge already has monotone q and a monotone
    roller-centre axial coordinate.  Over q in [-30, 90) the radial centre
    coordinate is monotone as well.  Endpoint centre coordinates therefore
    bound the complete centre path.  The physical contact point lies exactly
    one roller radius from that path, so expanding the centre box by R_roll is
    conservative for the ramp.  The flyweight subject is bounded by the two
    pivot endpoints, the centre box, and the roller-radius expansion.
    """

    x0 = segment.x0_m
    x1 = segment.x1_m
    q0 = segment.q0_rad
    q1 = segment.q1_rad
    L = architecture.arm_length_m
    rr = architecture.roller_radius_m
    px0 = architecture.pivot_axial_position_m - x0
    px1 = architecture.pivot_axial_position_m - x1
    pr = architecture.pivot_radius_m
    cx0 = px0 + L * np.cos(q0)
    cx1 = px1 + L * np.cos(q1)
    cr0 = pr + L * np.sin(q0)
    cr1 = pr + L * np.sin(q1)

    centre = (
        float(min(cx0, cx1)),
        float(min(cr0, cr1)),
        float(max(cx0, cx1)),
        float(max(cr0, cr1)),
    )
    ramp = (
        centre[0] - rr,
        centre[1] - rr,
        centre[2] + rr,
        centre[3] + rr,
    )
    flyweight = (
        min(px0, px1, centre[0] - rr),
        min(pr, centre[1] - rr),
        max(px0, px1, centre[2] + rr),
        max(pr, centre[3] + rr),
    )
    return ramp, tuple(float(value) for value in flyweight)


def _bbox_contains(
    outer: tuple[float, float, float, float], inner: tuple[float, float, float, float]
) -> bool:
    return (
        outer[0] <= inner[0] + 1.0e-12
        and outer[1] <= inner[1] + 1.0e-12
        and outer[2] >= inner[2] - 1.0e-12
        and outer[3] >= inner[3] - 1.0e-12
    )


def _segment_satisfies_packaging_fast(
    architecture: ArchitectureDesign,
    segment: PathSegment,
    zones: tuple[dict[str, object], ...],
) -> bool:
    if not zones:
        return True

    ramp_subject_bounds, flyweight_subject_bounds = _segment_subject_bounds(architecture, segment)
    active_zones: list[dict[str, object]] = []
    for item in zones:
        zone = item["zone"]
        assert isinstance(zone, PackagingZone)
        bounds = item["bounds"]
        assert isinstance(bounds, tuple)
        subject_bounds = ramp_subject_bounds if zone.subject == "ramp" else flyweight_subject_bounds
        if zone.rule == "forbid":
            # Exact-safe broad phase: if the conservative subject box is
            # disjoint from the buffered keep-out, no sampled geometry or
            # Shapely construction is needed for this edge.
            if _bbox_disjoint(subject_bounds, bounds):
                continue
        else:
            # Containment requires the full check, but a failed bounding-box
            # containment is already sufficient to reject the edge.
            if not _bbox_contains(bounds, subject_bounds):
                return False
        active_zones.append(item)

    if not active_zones:
        return True

    xs = np.linspace(segment.x0_m, segment.x1_m, 33)
    rows = [
        _geometry_from_q(architecture, float(x), *_hermite_q_derivatives(segment, float(x)))
        for x in xs
    ]
    if any(not all(isfinite(float(value)) for value in row.values()) for row in rows):
        return False

    ramp_points = [(row["contact_x_m"], row["contact_r_m"]) for row in rows]
    ramp_line = LineString(ramp_points)
    ramp_bounds = ramp_line.bounds
    centre_points = [(row["roller_center_x_m"], row["roller_center_r_m"]) for row in rows]

    for item in active_zones:
        zone = item["zone"]
        assert isinstance(zone, PackagingZone)
        surface = item["surface"]
        roller_surface = item["roller_surface"]
        assert isinstance(surface, Polygon) or hasattr(surface, "covers")
        bounds = item["bounds"]
        assert isinstance(bounds, tuple)

        if zone.subject == "ramp":
            if zone.rule == "forbid":
                if _bbox_disjoint(ramp_bounds, bounds):
                    continue
                if ramp_line.intersects(surface):
                    return False
            else:
                if surface.is_empty or not surface.covers(ramp_line):
                    return False
            continue

        if zone.rule == "forbid":
            # The original code built a union of 33 arms and 33 roller disks.
            # Checking each sampled pose independently is set-theoretically
            # equivalent, while avoiding the very expensive unary_union.
            for x, (cx, cr) in zip(xs, centre_points, strict=True):
                point = Point(cx, cr)
                if surface.distance(point) <= architecture.roller_radius_m + 1.0e-12:
                    return False
                px = architecture.pivot_axial_position_m - float(x)
                arm = LineString(((px, architecture.pivot_radius_m), (cx, cr)))
                if arm.intersects(surface):
                    return False
        else:
            if surface.is_empty or roller_surface.is_empty:
                return False
            for x, (cx, cr) in zip(xs, centre_points, strict=True):
                point = Point(cx, cr)
                if not roller_surface.covers(point):
                    return False
                px = architecture.pivot_axial_position_m - float(x)
                arm = LineString(((px, architecture.pivot_radius_m), (cx, cr)))
                if not surface.covers(arm):
                    return False
    return True
