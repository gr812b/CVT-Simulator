"""Phase-3 ramp-path domain analysis for the fixed-pivot primary.

The Phase-2 architecture workspace answers a local question: where *could* a
ramp surface point exist?  This module answers a stronger path question.  It
constructs a layered viability graph over primary shift, where one node is a
local contact state ``(q, alpha)`` and one edge is a smooth finite-roller ramp
segment joining two adjacent shift stations.

Phase 3.1 is the local graph: every retained edge is regular over its whole
interval and satisfies packaging.  Phase 3.2 adds complete-path history checks:

* the finite-roller offset curve may not self-intersect at two distinct ramp
  coordinates (one roller pose touching two ramp points simultaneously);
* the physical ramp may not self-intersect non-locally;
* multiple mathematical contact roots at one shift are explicitly allowed;
  the physical branch is selected at the first shift by the lowest-q root and
  then continued by proximity/prediction instead of jumping to a distant root.

The module intentionally has no CINDER import.  CINDER remains the final
mechanics authority for concrete/manufacturing ramps, while this domain kernel
can be tested quickly and independently.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, degrees, hypot, isfinite, pi, sin
from typing import Iterable

import numpy as np
from scipy.optimize import brentq, least_squares
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from .models import ArchitectureDesign, PackagingZone

Q_MIN_RAD = -pi / 6.0
Q_MAX_RAD = 0.5 * pi
_EPS = 1.0e-12


@dataclass(frozen=True, slots=True)
class PathState:
    q_rad: float
    alpha_rad: float
    dq_dx_rad_per_m: float


@dataclass(frozen=True, slots=True)
class EdgeTemplate:
    start_state: int
    end_state: int
    q0_rad: float
    q1_rad: float
    m0_rad_per_m: float
    m1_rad_per_m: float
    strict_active: bool


@dataclass(frozen=True, slots=True)
class LayerEdge:
    layer: int
    template_index: int
    start_state: int
    end_state: int


@dataclass(frozen=True, slots=True)
class PathSegment:
    x0_m: float
    x1_m: float
    q0_rad: float
    q1_rad: float
    m0_rad_per_m: float
    m1_rad_per_m: float


@dataclass(frozen=True, slots=True)
class ContactRoot:
    parameter_m: float
    q_rad: float
    roller_center_x_m: float
    roller_center_r_m: float


@dataclass(frozen=True, slots=True)
class HistoryFailure:
    code: str
    message: str
    shift_m: float | None = None
    first_parameter_m: float | None = None
    second_parameter_m: float | None = None


@dataclass(frozen=True, slots=True)
class HistoryCertification:
    valid: bool
    failure: HistoryFailure | None
    max_contact_root_count: int
    multiple_root_shift_count: int
    branch_trace_shift_m: tuple[float, ...]
    branch_trace_parameter_m: tuple[float, ...]
    branch_trace_q_rad: tuple[float, ...]


class PiecewiseRampPath:
    """One complete smooth path assembled from cubic-Hermite q(x) segments."""

    def __init__(
        self,
        architecture: ArchitectureDesign,
        segments: tuple[PathSegment, ...],
    ) -> None:
        if not segments:
            raise ValueError("a complete path requires at least one segment")
        self.architecture = architecture
        self.segments = segments
        self.x_min_m = segments[0].x0_m
        self.x_max_m = segments[-1].x1_m

    def evaluate(self, x_m: float) -> dict[str, float]:
        segment = self._segment_for(x_m)
        q, dq, ddq = _hermite_q_derivatives(segment, x_m)
        return _geometry_from_q(self.architecture, x_m, q, dq, ddq)

    def sample(self, count: int) -> dict[str, np.ndarray]:
        if count < 2:
            raise ValueError("count must be at least 2")
        xs = np.linspace(self.x_min_m, self.x_max_m, count)
        rows = [self.evaluate(float(x)) for x in xs]
        keys = rows[0].keys()
        result = {"shift_m": xs}
        for key in keys:
            result[key] = np.asarray([row[key] for row in rows], dtype=float)
        return result

    def _segment_for(self, x_m: float) -> PathSegment:
        x = min(max(float(x_m), self.x_min_m), self.x_max_m)
        if x >= self.x_max_m:
            return self.segments[-1]
        lo = 0
        hi = len(self.segments) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            segment = self.segments[mid]
            if x < segment.x0_m:
                hi = mid - 1
            elif x > segment.x1_m:
                lo = mid + 1
            else:
                return segment
        return self.segments[min(max(lo, 0), len(self.segments) - 1)]


def analyze_path_domain(
    architecture: ArchitectureDesign,
    zones: tuple[PackagingZone, ...],
    *,
    shift_station_count: int = 9,
    q_sample_count: int = 61,
    alpha_sample_count: int = 7,
    representative_path_count: int = 5,
    edge_audit_sample_count: int = 65,
    history_trace_sample_count: int = 65,
) -> dict[str, object]:
    """Build the Phase-3.1 viability graph and Phase-3.2 certified path atlas."""

    _validate_inputs(
        architecture,
        shift_station_count,
        q_sample_count,
        alpha_sample_count,
        representative_path_count,
        edge_audit_sample_count,
        history_trace_sample_count,
    )
    zone_geometries = _prepare_zones(zones)

    dx = architecture.required_travel_m / (shift_station_count - 1)
    states = _build_states(architecture, q_sample_count, alpha_sample_count)
    templates = _build_edge_templates(
        architecture,
        states,
        dx,
        edge_audit_sample_count=edge_audit_sample_count,
    )

    layers: list[list[LayerEdge]] = []
    for layer in range(shift_station_count - 1):
        x0 = layer * dx
        layer_edges: list[LayerEdge] = []
        for template_index, template in enumerate(templates):
            segment = PathSegment(
                x0_m=x0,
                x1_m=x0 + dx,
                q0_rad=template.q0_rad,
                q1_rad=template.q1_rad,
                m0_rad_per_m=template.m0_rad_per_m,
                m1_rad_per_m=template.m1_rad_per_m,
            )
            if _segment_satisfies_packaging(
                architecture,
                segment,
                zone_geometries,
            ):
                layer_edges.append(
                    LayerEdge(
                        layer=layer,
                        template_index=template_index,
                        start_state=template.start_state,
                        end_state=template.end_state,
                    )
                )
        layers.append(layer_edges)

    viable_edges, viable_nodes = _forward_backward_viability(
        layers,
        len(states),
        shift_station_count,
    )

    candidate_paths = _extract_candidate_paths(
        viable_edges,
        viable_nodes,
        states,
        shift_station_count,
        max_candidates=max(48, 12 * representative_path_count),
    )

    certified_paths: list[dict[str, object]] = []
    rejected_history: list[dict[str, object]] = []
    seen_signatures: set[tuple[int, ...]] = set()
    for state_path in candidate_paths:
        signature = tuple(state_path)
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        ramp_path = _path_from_state_indices(
            architecture,
            states,
            state_path,
            shift_station_count,
        )
        certification = certify_path_history(
            ramp_path,
            trace_sample_count=history_trace_sample_count,
        )
        if not certification.valid:
            failure = certification.failure
            rejected_history.append(
                {
                    "state_indices": list(state_path),
                    "failure": None
                    if failure is None
                    else {
                        "code": failure.code,
                        "message": failure.message,
                        "shift_m": failure.shift_m,
                        "first_parameter_m": failure.first_parameter_m,
                        "second_parameter_m": failure.second_parameter_m,
                    },
                }
            )
            continue

        certified_paths.append(
            _path_document(
                ramp_path,
                state_path,
                certification,
                sample_count=max(161, 20 * shift_station_count + 1),
            )
        )
        if len(certified_paths) >= representative_path_count:
            break

    station_projection = _station_projection(
        viable_nodes,
        states,
        shift_station_count,
    )

    return {
        "validity": {
            "valid": bool(certified_paths),
            "findings": []
            if certified_paths
            else [
                {
                    "severity": "error",
                    "code": "NO_HISTORY_CERTIFIED_PATH",
                    "message": (
                        "The local viability graph contains no representative "
                        "complete path that also passes the Phase-3.2 history checks."
                    ),
                }
            ],
        },
        "graph": {
            "shift_station_count": shift_station_count,
            "q_sample_count": q_sample_count,
            "alpha_sample_count": alpha_sample_count,
            "state_count": len(states),
            "local_transition_template_count": len(templates),
            "layer_edge_counts": [len(items) for items in layers],
            "viable_layer_edge_counts": [len(items) for items in viable_edges],
            "viable_node_counts": [len(items) for items in viable_nodes],
            "station_projection": station_projection,
        },
        "history": {
            "candidate_complete_path_count": len(candidate_paths),
            "certified_representative_path_count": len(certified_paths),
            "history_rejection_count": len(rejected_history),
            "rejections": rejected_history[:20],
            "selection_rule": (
                "At the first shift choose the lowest-q mathematical contact; "
                "thereafter continue the nearest predicted outward branch. "
                "Other simultaneous mathematical roots are allowed unless two "
                "distinct ramp points share the same roller centre."
            ),
        },
        "representative_paths": certified_paths,
        "deferred_checks": [
            "exact CINDER certification of the final manufacturing spline",
            "C3/C4 manufacturing-spline reconstruction and round-trip certification",
        ],
        "numerics": {
            "edge_audit_sample_count": edge_audit_sample_count,
            "history_trace_sample_count": history_trace_sample_count,
        },
    }


def certify_path_history(
    path: PiecewiseRampPath,
    *,
    trace_sample_count: int = 257,
    broad_phase_samples_per_segment: int = 65,
) -> HistoryCertification:
    """Certify nonlocal geometry and history-selected contact continuation.

    Multiple contact roots at the same shift are legal.  Rejection occurs only
    if the selected branch does not begin at the lowest-q physical root, jumps
    away from the continuous outward branch, or one roller-centre offset point
    corresponds to two distinct physical ramp points.
    """

    if trace_sample_count < 33:
        raise ValueError("trace_sample_count must be at least 33")

    double_event = _first_nonlocal_self_intersection(
        path,
        quantity="roller_center",
        samples_per_segment=broad_phase_samples_per_segment,
    )
    if double_event is not None:
        s1, s2, px, pr = double_event
        selected_shift = min(s1, s2)
        return HistoryCertification(
            valid=False,
            failure=HistoryFailure(
                code="SECOND_SIMULTANEOUS_CONTACT",
                message=(
                    "Two distinct physical ramp coordinates have the same finite-roller "
                    "centre. This is one roller pose with two simultaneous contacts, not "
                    "merely two alternative mathematical contact solutions."
                ),
                shift_m=selected_shift,
                first_parameter_m=s1,
                second_parameter_m=s2,
            ),
            max_contact_root_count=0,
            multiple_root_shift_count=0,
            branch_trace_shift_m=(),
            branch_trace_parameter_m=(),
            branch_trace_q_rad=(),
        )

    ramp_cross = _first_nonlocal_self_intersection(
        path,
        quantity="contact",
        samples_per_segment=broad_phase_samples_per_segment,
    )
    if ramp_cross is not None:
        s1, s2, _px, _pr = ramp_cross
        return HistoryCertification(
            valid=False,
            failure=HistoryFailure(
                code="RAMP_SELF_INTERSECTION",
                message="The complete physical ramp self-intersects non-locally.",
                shift_m=min(s1, s2),
                first_parameter_m=s1,
                second_parameter_m=s2,
            ),
            max_contact_root_count=0,
            multiple_root_shift_count=0,
            branch_trace_shift_m=(),
            branch_trace_parameter_m=(),
            branch_trace_q_rad=(),
        )

    trace = _trace_history_selected_branch(path, trace_sample_count)
    return trace


def _build_states(
    architecture: ArchitectureDesign,
    q_sample_count: int,
    alpha_sample_count: int,
) -> tuple[PathState, ...]:
    q_values = np.linspace(Q_MIN_RAD, Q_MAX_RAD, q_sample_count)
    states: list[PathState] = []
    for raw_q in q_values:
        q = float(raw_q)
        # Leave a small geometric margin from the dead-centre q+alpha=90°.
        max_alpha = min(np.deg2rad(80.0), max(0.0, Q_MAX_RAD - q - np.deg2rad(0.5)))
        if max_alpha <= 1.0e-12:
            alpha_values = (0.0,)
        else:
            alpha_values = tuple(float(v) for v in np.linspace(0.0, max_alpha, alpha_sample_count))
        for alpha in alpha_values:
            dq = _dq_dx_from_q_alpha(architecture, q, alpha)
            if dq is None:
                continue
            states.append(PathState(q_rad=q, alpha_rad=alpha, dq_dx_rad_per_m=dq))
    return tuple(states)


def _dq_dx_from_q_alpha(
    architecture: ArchitectureDesign,
    q: float,
    alpha: float,
) -> float | None:
    d = float(architecture.ramp_axial_direction)
    denominator = architecture.arm_length_m * (
        sin(q) * sin(alpha) + d * cos(q) * cos(alpha)
    )
    if abs(denominator) <= 1.0e-12:
        return None
    dq = -sin(alpha) / denominator
    if not isfinite(dq) or dq < -1.0e-10:
        return None
    return max(0.0, dq)


def _build_edge_templates(
    architecture: ArchitectureDesign,
    states: tuple[PathState, ...],
    dx: float,
    *,
    edge_audit_sample_count: int,
) -> tuple[EdgeTemplate, ...]:
    templates: list[EdgeTemplate] = []
    by_q: dict[float, list[tuple[int, PathState]]] = {}
    for index, state in enumerate(states):
        by_q.setdefault(round(state.q_rad, 14), []).append((index, state))
    ordered_q = sorted(by_q)

    for q0_key in ordered_q:
        for start_index, start in by_q[q0_key]:
            for q1_key in ordered_q:
                if q1_key < q0_key - 1.0e-12:
                    continue
                delta = q1_key - q0_key
                for end_index, end in by_q[q1_key]:
                    if delta <= 1.0e-12:
                        if start.dq_dx_rad_per_m > 1.0e-9 or end.dq_dx_rad_per_m > 1.0e-9:
                            continue
                    else:
                        # Very cheap necessary condition: the Hermite derivative
                        # must remain non-negative over the interval.
                        if not _hermite_monotone(
                            start.q_rad,
                            end.q_rad,
                            start.dq_dx_rad_per_m,
                            end.dq_dx_rad_per_m,
                            dx,
                        ):
                            continue
                    segment = PathSegment(
                        x0_m=0.0,
                        x1_m=dx,
                        q0_rad=start.q_rad,
                        q1_rad=end.q_rad,
                        m0_rad_per_m=start.dq_dx_rad_per_m,
                        m1_rad_per_m=end.dq_dx_rad_per_m,
                    )
                    if not _audit_local_segment(
                        architecture,
                        segment,
                        sample_count=edge_audit_sample_count,
                    ):
                        continue
                    templates.append(
                        EdgeTemplate(
                            start_state=start_index,
                            end_state=end_index,
                            q0_rad=start.q_rad,
                            q1_rad=end.q_rad,
                            m0_rad_per_m=start.dq_dx_rad_per_m,
                            m1_rad_per_m=end.dq_dx_rad_per_m,
                            strict_active=(delta > 1.0e-10),
                        )
                    )
    return tuple(templates)


def _hermite_monotone(q0: float, q1: float, m0: float, m1: float, h: float) -> bool:
    delta = q1 - q0
    if delta < -1.0e-12:
        return False
    if delta <= 1.0e-12:
        return abs(m0) <= 1.0e-9 and abs(m1) <= 1.0e-9
    M0 = h * m0
    M1 = h * m1
    A = 3.0 * delta - 2.0 * M0 - M1
    B = -2.0 * delta + M0 + M1
    # dq/dt = M0 + 2 A t + 3 B t^2.  Check its exact minimum.
    values = [M0, M0 + 2.0 * A + 3.0 * B]
    if abs(B) > 1.0e-16:
        t_vertex = -A / (3.0 * B)
        if 0.0 < t_vertex < 1.0:
            values.append(M0 + 2.0 * A * t_vertex + 3.0 * B * t_vertex * t_vertex)
    return min(values) >= -1.0e-11


def _audit_local_segment(
    architecture: ArchitectureDesign,
    segment: PathSegment,
    *,
    sample_count: int,
) -> bool:
    # Dense bracketing plus explicit local-extremum refinement.  The sample grid
    # is only the bracket finder; acceptance values are evaluated at endpoints
    # and localized extrema.
    ts = np.linspace(segment.x0_m, segment.x1_m, sample_count)
    rows = [_segment_constraint_row(architecture, segment, float(x)) for x in ts]
    if any(row is None for row in rows):
        return False
    matrix = np.asarray(rows, dtype=float)

    # columns: qdot, direction*Rx', offset factor, tangent margin
    if np.min(matrix[:, 0]) < -1.0e-9:
        return False
    if np.min(matrix[:, 1]) <= 1.0e-8:
        return False
    if np.min(matrix[:, 2]) <= 2.0e-5:
        return False
    if np.min(matrix[:, 3]) <= 0.0:
        return False

    # Refine suspicious minima between brackets.  This is conservative: if a
    # localized minimization fails, reject the edge rather than admitting it.
    from scipy.optimize import minimize_scalar

    for column in (1, 2, 3):
        vals = matrix[:, column]
        candidate_indices = [
            i
            for i in range(1, len(vals) - 1)
            if vals[i] <= vals[i - 1] and vals[i] <= vals[i + 1]
        ]
        for index in candidate_indices:
            left = float(ts[index - 1])
            right = float(ts[index + 1])
            try:
                result = minimize_scalar(
                    lambda x: _segment_constraint_row(architecture, segment, float(x))[column],
                    bounds=(left, right),
                    method="bounded",
                    options={"xatol": 1.0e-12},
                )
            except Exception:
                return False
            if not result.success:
                return False
            threshold = 1.0e-8 if column == 1 else (2.0e-5 if column == 2 else 0.0)
            if float(result.fun) <= threshold:
                return False
    return True


def _segment_constraint_row(
    architecture: ArchitectureDesign,
    segment: PathSegment,
    x_m: float,
) -> tuple[float, float, float, float] | None:
    q, dq, ddq = _hermite_q_derivatives(segment, x_m)
    geometry = _geometry_from_q(architecture, x_m, q, dq, ddq)
    if not all(isfinite(value) for value in geometry.values()):
        return None
    direction = float(architecture.ramp_axial_direction)
    tangent_deg = geometry["ramp_tangent_deg"]
    return (
        dq,
        direction * geometry["roller_center_dx_dx"],
        geometry["offset_factor"],
        88.5 - tangent_deg,
    )


def _geometry_from_q(
    architecture: ArchitectureDesign,
    x_m: float,
    q: float,
    dq: float,
    ddq: float,
) -> dict[str, float]:
    L = architecture.arm_length_m
    rr = architecture.roller_radius_m
    side = float(architecture.roller_side_sign)
    direction = float(architecture.ramp_axial_direction)

    px = architecture.pivot_axial_position_m - x_m
    pr = architecture.pivot_radius_m
    rx = px + L * cos(q)
    radial = pr + L * sin(q)
    vx = -1.0 - L * sin(q) * dq
    vr = L * cos(q) * dq
    ax = -L * (cos(q) * dq * dq + sin(q) * ddq)
    ar = L * (-sin(q) * dq * dq + cos(q) * ddq)
    speed = hypot(vx, vr)
    if speed <= 1.0e-14:
        return {
            "q_rad": q,
            "dq_dx_rad_per_m": dq,
            "roller_center_x_m": rx,
            "roller_center_r_m": radial,
            "roller_center_dx_dx": vx,
            "roller_center_dr_dx": vr,
            "contact_x_m": float("nan"),
            "contact_r_m": float("nan"),
            "ramp_tangent_deg": float("nan"),
            "offset_factor": float("nan"),
        }
    tx = vx / speed
    tr = vr / speed
    # left normal of the oriented centre curve; C = R - r * side * n_left
    nx = -side * tr
    nr = side * tx
    cx = rx - rr * nx
    cr = radial - rr * nr
    cross = vx * ar - vr * ax
    curvature = cross / (speed * speed * speed)
    offset_factor = 1.0 + rr * side * curvature
    tangent = atan2(max(0.0, tr), max(1.0e-16, direction * tx))
    return {
        "q_rad": q,
        "dq_dx_rad_per_m": dq,
        "roller_center_x_m": rx,
        "roller_center_r_m": radial,
        "roller_center_dx_dx": vx,
        "roller_center_dr_dx": vr,
        "contact_x_m": cx,
        "contact_r_m": cr,
        "ramp_tangent_deg": degrees(tangent),
        "offset_factor": offset_factor,
    }


def _hermite_q_derivatives(segment: PathSegment, x_m: float) -> tuple[float, float, float]:
    h = segment.x1_m - segment.x0_m
    t = (x_m - segment.x0_m) / h
    t = min(max(t, 0.0), 1.0)
    delta = segment.q1_rad - segment.q0_rad
    M0 = h * segment.m0_rad_per_m
    M1 = h * segment.m1_rad_per_m
    A = 3.0 * delta - 2.0 * M0 - M1
    B = -2.0 * delta + M0 + M1
    q = segment.q0_rad + M0 * t + A * t * t + B * t * t * t
    qt = M0 + 2.0 * A * t + 3.0 * B * t * t
    qtt = 2.0 * A + 6.0 * B * t
    return q, qt / h, qtt / (h * h)


def _prepare_zones(zones: tuple[PackagingZone, ...]) -> tuple[tuple[Polygon, PackagingZone], ...]:
    prepared: list[tuple[Polygon, PackagingZone]] = []
    ids: set[str] = set()
    for zone in zones:
        if zone.id in ids:
            raise ValueError("packaging zone ids must be unique")
        ids.add(zone.id)
        polygon = Polygon(zone.polygon_m)
        if polygon.is_empty or not polygon.is_valid or polygon.area <= 0.0:
            raise ValueError(f"packaging zone {zone.label!r} is invalid")
        prepared.append((polygon, zone))
    return tuple(prepared)


def _segment_satisfies_packaging(
    architecture: ArchitectureDesign,
    segment: PathSegment,
    zone_geometries: tuple[tuple[Polygon, PackagingZone], ...],
) -> bool:
    if not zone_geometries:
        return True
    xs = np.linspace(segment.x0_m, segment.x1_m, 33)
    rows = [
        _geometry_from_q(architecture, float(x), *_hermite_q_derivatives(segment, float(x)))
        for x in xs
    ]
    ramp_line = LineString([(row["contact_x_m"], row["contact_r_m"]) for row in rows])

    flyweight_geometries = []
    for x, row in zip(xs, rows, strict=True):
        px = architecture.pivot_axial_position_m - float(x)
        pr = architecture.pivot_radius_m
        roller = Point(row["roller_center_x_m"], row["roller_center_r_m"]).buffer(
            architecture.roller_radius_m, quad_segs=8
        )
        arm = LineString(((px, pr), (row["roller_center_x_m"], row["roller_center_r_m"])))
        flyweight_geometries.append(unary_union((arm, roller)))

    for polygon, zone in zone_geometries:
        if zone.subject == "ramp":
            subject = ramp_line
        else:
            subject = unary_union(tuple(flyweight_geometries))
        if zone.rule == "forbid":
            barrier = polygon.buffer(zone.clearance_m, quad_segs=8)
            if subject.intersects(barrier):
                return False
        else:
            allowed = polygon.buffer(-zone.clearance_m, quad_segs=8)
            if allowed.is_empty or not allowed.covers(subject):
                return False
    return True


def _forward_backward_viability(
    layers: list[list[LayerEdge]],
    state_count: int,
    station_count: int,
) -> tuple[list[list[LayerEdge]], list[set[int]]]:
    forward: list[set[int]] = [set() for _ in range(station_count)]
    backward: list[set[int]] = [set() for _ in range(station_count)]

    if layers:
        forward[0] = {edge.start_state for edge in layers[0]}
    for layer_index, edges in enumerate(layers):
        reachable = forward[layer_index]
        forward[layer_index + 1] = {
            edge.end_state for edge in edges if edge.start_state in reachable
        }

    if layers:
        backward[-1] = {edge.end_state for edge in layers[-1]}
    for layer_index in range(len(layers) - 1, -1, -1):
        coreachable = backward[layer_index + 1]
        backward[layer_index] = {
            edge.start_state
            for edge in layers[layer_index]
            if edge.end_state in coreachable
        }

    viable_nodes = [forward[i] & backward[i] for i in range(station_count)]
    viable_edges: list[list[LayerEdge]] = []
    for layer_index, edges in enumerate(layers):
        viable_edges.append(
            [
                edge
                for edge in edges
                if edge.start_state in viable_nodes[layer_index]
                and edge.end_state in viable_nodes[layer_index + 1]
            ]
        )
    return viable_edges, viable_nodes


def _extract_candidate_paths(
    viable_edges: list[list[LayerEdge]],
    viable_nodes: list[set[int]],
    states: tuple[PathState, ...],
    station_count: int,
    *,
    max_candidates: int,
) -> list[list[int]]:
    if not viable_edges or not viable_nodes[0] or not viable_nodes[-1]:
        return []
    outgoing: list[dict[int, list[int]]] = []
    for edges in viable_edges:
        mapping: dict[int, list[int]] = {}
        for edge in edges:
            mapping.setdefault(edge.start_state, []).append(edge.end_state)
        for values in mapping.values():
            values.sort(key=lambda i: (states[i].q_rad, states[i].alpha_rad))
        outgoing.append(mapping)

    starts = sorted(viable_nodes[0], key=lambda i: (states[i].q_rad, states[i].alpha_rad))
    active_starts = [
        index
        for index in starts
        if any(
            states[end].q_rad > states[index].q_rad + 1.0e-10
            for end in outgoing[0].get(index, [])
        )
    ]
    if active_starts:
        starts = active_starts
    if len(starts) > 16:
        pick = np.linspace(0, len(starts) - 1, 16).round().astype(int)
        starts = [starts[int(i)] for i in pick]

    candidates: list[list[int]] = []
    target_fractions = (0.0, 0.25, 0.5, 0.75, 1.0)
    for start in starts:
        for fraction in target_fractions:
            path = [start]
            current = start
            ok = True
            for layer in range(station_count - 1):
                choices = outgoing[layer].get(current, [])
                if not choices:
                    ok = False
                    break
                active_choices = [
                    end
                    for end in choices
                    if states[end].q_rad > states[current].q_rad + 1.0e-10
                ]
                if active_choices:
                    choices = active_choices
                # Pick a deterministic quantile of the legal continuations. This
                # yields mechanically diverse complete paths without enumerating
                # the combinatorial path set.
                index = int(round(fraction * (len(choices) - 1)))
                current = choices[index]
                path.append(current)
            if ok:
                candidates.append(path)
                if len(candidates) >= max_candidates:
                    return candidates
    return candidates


def _path_from_state_indices(
    architecture: ArchitectureDesign,
    states: tuple[PathState, ...],
    state_path: list[int],
    station_count: int,
) -> PiecewiseRampPath:
    dx = architecture.required_travel_m / (station_count - 1)
    segments: list[PathSegment] = []
    for layer, (left_index, right_index) in enumerate(zip(state_path[:-1], state_path[1:], strict=True)):
        left = states[left_index]
        right = states[right_index]
        x0 = layer * dx
        segments.append(
            PathSegment(
                x0_m=x0,
                x1_m=x0 + dx,
                q0_rad=left.q_rad,
                q1_rad=right.q_rad,
                m0_rad_per_m=left.dq_dx_rad_per_m,
                m1_rad_per_m=right.dq_dx_rad_per_m,
            )
        )
    return PiecewiseRampPath(architecture, tuple(segments))


def _trace_history_selected_branch(
    path: PiecewiseRampPath,
    trace_sample_count: int,
) -> HistoryCertification:
    xs = np.linspace(path.x_min_m, path.x_max_m, trace_sample_count)
    selected_s: list[float] = []
    selected_q: list[float] = []
    max_roots = 0
    multiple_count = 0
    previous_s: float | None = None
    previous_q: float | None = None
    previous_previous_s: float | None = None

    for index, raw_x in enumerate(xs):
        x = float(raw_x)
        roots = _contact_roots_at_shift(path, x)
        max_roots = max(max_roots, len(roots))
        if len(roots) > 1:
            multiple_count += 1
        if not roots:
            return HistoryCertification(
                valid=False,
                failure=HistoryFailure(
                    code="CONTACT_BRANCH_LOST",
                    message="No finite-roller contact root exists on the complete ramp.",
                    shift_m=x,
                ),
                max_contact_root_count=max_roots,
                multiple_root_shift_count=multiple_count,
                branch_trace_shift_m=tuple(float(v) for v in xs[:index]),
                branch_trace_parameter_m=tuple(selected_s),
                branch_trace_q_rad=tuple(selected_q),
            )

        if index == 0:
            # This is the physical branch-selection rule: if several contacts
            # exist initially, deployment starts at the smallest arm angle.
            chosen = min(roots, key=lambda root: (root.q_rad, root.parameter_m))
            intended = path.evaluate(x)
            intended_q = intended["q_rad"]
            if abs(chosen.parameter_m - x) > 2.0e-5 or abs(chosen.q_rad - intended_q) > np.deg2rad(0.08):
                return HistoryCertification(
                    valid=False,
                    failure=HistoryFailure(
                        code="INITIAL_BRANCH_NOT_SELECTED",
                        message=(
                            "The designed contact is not the lowest-q initial physical root; "
                            "the mechanism would engage a different branch first."
                        ),
                        shift_m=x,
                        first_parameter_m=chosen.parameter_m,
                        second_parameter_m=x,
                    ),
                    max_contact_root_count=max_roots,
                    multiple_root_shift_count=multiple_count,
                    branch_trace_shift_m=(),
                    branch_trace_parameter_m=(),
                    branch_trace_q_rad=(),
                )
        else:
            assert previous_s is not None and previous_q is not None
            if previous_previous_s is None:
                predicted_s = previous_s + (x - float(xs[index - 1]))
            else:
                dx_prev = float(xs[index - 1] - xs[index - 2])
                ds_prev = previous_s - previous_previous_s
                predicted_s = previous_s + ds_prev * ((x - float(xs[index - 1])) / max(dx_prev, _EPS))
            outward = [root for root in roots if root.q_rad >= previous_q - np.deg2rad(0.08)]
            pool = outward if outward else roots
            chosen = min(
                pool,
                key=lambda root: (
                    abs(root.parameter_m - predicted_s),
                    abs(root.q_rad - previous_q),
                ),
            )
            intended = path.evaluate(x)
            intended_q = intended["q_rad"]
            # A distinct mathematical root is harmless. What is not harmless is
            # history jumping from the designed continuous branch to that root.
            parameter_tolerance = max(3.0e-5, 0.35 * (path.x_max_m - path.x_min_m) / (trace_sample_count - 1))
            if abs(chosen.parameter_m - x) > parameter_tolerance or abs(chosen.q_rad - intended_q) > np.deg2rad(0.12):
                return HistoryCertification(
                    valid=False,
                    failure=HistoryFailure(
                        code="CONTACT_BRANCH_JUMP",
                        message=(
                            "History-selected continuation leaves the designed branch and "
                            "would jump to a disconnected mathematical contact solution."
                        ),
                        shift_m=x,
                        first_parameter_m=previous_s,
                        second_parameter_m=chosen.parameter_m,
                    ),
                    max_contact_root_count=max_roots,
                    multiple_root_shift_count=multiple_count,
                    branch_trace_shift_m=tuple(float(v) for v in xs[:index]),
                    branch_trace_parameter_m=tuple(selected_s),
                    branch_trace_q_rad=tuple(selected_q),
                )

        previous_previous_s = previous_s
        previous_s = chosen.parameter_m
        previous_q = chosen.q_rad
        selected_s.append(chosen.parameter_m)
        selected_q.append(chosen.q_rad)

    return HistoryCertification(
        valid=True,
        failure=None,
        max_contact_root_count=max_roots,
        multiple_root_shift_count=multiple_count,
        branch_trace_shift_m=tuple(float(v) for v in xs),
        branch_trace_parameter_m=tuple(selected_s),
        branch_trace_q_rad=tuple(selected_q),
    )


def _contact_roots_at_shift(path: PiecewiseRampPath, shift_m: float) -> list[ContactRoot]:
    """Return every arm-circle/contact root at one actual sheave shift.

    For a Phase-3 path the finite-roller centre associated with ramp parameter
    ``s`` is

        E(s) = [P0 - s + L cos q(s), Pr + L sin q(s)].

    Intersecting that offset curve with the arm circle centred at
    ``P(shift)`` factorizes exactly:

        |E(s)-P(x)|^2 - L^2
          = (x-s) [x-s + 2 L cos q(s)].

    The designed branch ``s=x`` is therefore an exact root by construction;
    alternative mathematical contacts are roots of the second scalar factor.
    Using this identity is both faster and more reliable than repeatedly
    solving a generic circle-distance equation.
    """

    architecture = path.architecture
    L = architecture.arm_length_m
    x = float(shift_m)

    roots: list[float] = []
    if path.x_min_m - 1.0e-12 <= x <= path.x_max_m + 1.0e-12:
        roots.append(min(max(x, path.x_min_m), path.x_max_m))

    def alternate_factor(s: float) -> float:
        row = path.evaluate(float(s))
        return x - float(s) + 2.0 * L * cos(row["q_rad"])

    # The second factor is cheap. A moderately dense bracket grid plus local
    # minimization catches both sign-changing and tangential alternative roots.
    sample_count = max(257, 48 * len(path.segments) + 1)
    ss = np.linspace(path.x_min_m, path.x_max_m, sample_count)
    values = np.asarray([alternate_factor(float(s)) for s in ss])
    scale_tol = max(2.0e-10, 1.0e-8 * max(L, path.x_max_m - path.x_min_m))

    for i in range(sample_count - 1):
        a = float(ss[i])
        b = float(ss[i + 1])
        fa = float(values[i])
        fb = float(values[i + 1])
        if abs(fa) <= scale_tol:
            roots.append(a)
        if fa * fb < 0.0:
            try:
                roots.append(float(brentq(alternate_factor, a, b, xtol=1.0e-13, rtol=1.0e-12, maxiter=100)))
            except ValueError:
                pass
    if abs(float(values[-1])) <= scale_tol:
        roots.append(float(ss[-1]))

    from scipy.optimize import minimize_scalar

    absolute = np.abs(values)
    for i in range(1, sample_count - 1):
        if absolute[i] <= absolute[i - 1] and absolute[i] <= absolute[i + 1] and absolute[i] <= 50.0 * scale_tol:
            result = minimize_scalar(
                lambda s: abs(alternate_factor(float(s))),
                bounds=(float(ss[i - 1]), float(ss[i + 1])),
                method="bounded",
                options={"xatol": 1.0e-13},
            )
            if result.success and float(result.fun) <= 5.0 * scale_tol:
                roots.append(float(result.x))

    deduped: list[float] = []
    for root in sorted(roots):
        if not deduped or abs(root - deduped[-1]) > 2.0e-7:
            deduped.append(root)

    px = architecture.pivot_axial_position_m - x
    pr = architecture.pivot_radius_m
    result: list[ContactRoot] = []
    for s in deduped:
        row = path.evaluate(s)
        q = atan2(row["roller_center_r_m"] - pr, row["roller_center_x_m"] - px)
        if q < Q_MIN_RAD - np.deg2rad(0.2) or q > Q_MAX_RAD + np.deg2rad(0.2):
            continue
        result.append(
            ContactRoot(
                parameter_m=s,
                q_rad=q,
                roller_center_x_m=row["roller_center_x_m"],
                roller_center_r_m=row["roller_center_r_m"],
            )
        )
    return result


def _first_nonlocal_self_intersection(
    path: PiecewiseRampPath,
    *,
    quantity: str,
    samples_per_segment: int,
) -> tuple[float, float, float, float] | None:
    """Find the earliest refined nonlocal intersection of R(s) or C(s)."""

    if quantity not in ("roller_center", "contact"):
        raise ValueError("quantity must be 'roller_center' or 'contact'")
    samples_per_segment = max(17, samples_per_segment)
    points: list[tuple[float, float, float]] = []
    for segment_index, segment in enumerate(path.segments):
        xs = np.linspace(segment.x0_m, segment.x1_m, samples_per_segment)
        if segment_index:
            xs = xs[1:]
        for raw_x in xs:
            x = float(raw_x)
            row = path.evaluate(x)
            if quantity == "roller_center":
                points.append((x, row["roller_center_x_m"], row["roller_center_r_m"]))
            else:
                points.append((x, row["contact_x_m"], row["contact_r_m"]))

    # Broad phase: compare non-neighbouring polyline segments.  Bounds prune
    # almost all pairs.  Candidate intersections are then refined against the
    # continuous piecewise-Hermite geometry.
    candidates: list[tuple[float, float]] = []
    for i in range(len(points) - 1):
        s0, x0, r0 = points[i]
        s1, x1, r1 = points[i + 1]
        minx1, maxx1 = sorted((x0, x1))
        minr1, maxr1 = sorted((r0, r1))
        for j in range(i + 2, len(points) - 1):
            # Segments sharing a vertex are local continuity, not double contact.
            if j <= i + 1:
                continue
            t0, y0, u0 = points[j]
            t1, y1, u1 = points[j + 1]
            if abs(t0 - s1) <= 1.0e-10:
                continue
            minx2, maxx2 = sorted((y0, y1))
            minr2, maxr2 = sorted((u0, u1))
            tol = 2.0e-8
            if maxx1 + tol < minx2 or maxx2 + tol < minx1:
                continue
            if maxr1 + tol < minr2 or maxr2 + tol < minr1:
                continue
            line1 = LineString(((x0, r0), (x1, r1)))
            line2 = LineString(((y0, u0), (y1, u1)))
            if line1.distance(line2) <= 5.0e-7:
                candidates.append((0.5 * (s0 + s1), 0.5 * (t0 + t1)))

    if not candidates:
        return None

    events: list[tuple[float, float, float, float]] = []
    min_separation = max(5.0e-6, 0.002 * (path.x_max_m - path.x_min_m))

    def point_at(s: float) -> tuple[float, float]:
        row = path.evaluate(float(s))
        if quantity == "roller_center":
            return row["roller_center_x_m"], row["roller_center_r_m"]
        return row["contact_x_m"], row["contact_r_m"]

    for guess1, guess2 in candidates:
        if abs(guess2 - guess1) <= min_separation:
            continue
        span = (path.x_max_m - path.x_min_m) / max(1, len(points) - 1) * 2.5
        lower = np.array([
            max(path.x_min_m, guess1 - span),
            max(path.x_min_m, guess2 - span),
        ])
        upper = np.array([
            min(path.x_max_m, guess1 + span),
            min(path.x_max_m, guess2 + span),
        ])
        if lower[0] >= upper[0] or lower[1] >= upper[1]:
            continue

        def residual(z: np.ndarray) -> np.ndarray:
            a = point_at(float(z[0]))
            b = point_at(float(z[1]))
            return np.asarray([a[0] - b[0], a[1] - b[1]])

        result = least_squares(
            residual,
            x0=np.asarray([guess1, guess2]),
            bounds=(lower, upper),
            xtol=1.0e-13,
            ftol=1.0e-13,
            gtol=1.0e-13,
            max_nfev=200,
        )
        if not result.success:
            continue
        s1 = float(result.x[0])
        s2 = float(result.x[1])
        if abs(s2 - s1) <= min_separation:
            continue
        p1 = point_at(s1)
        p2 = point_at(s2)
        if hypot(p1[0] - p2[0], p1[1] - p2[1]) > 2.0e-7:
            continue
        first, second = sorted((s1, s2))
        if any(abs(first - e[0]) < 2.0e-6 and abs(second - e[1]) < 2.0e-6 for e in events):
            continue
        px, pr = point_at(first)
        events.append((first, second, px, pr))

    return min(events, key=lambda item: item[0]) if events else None


def _path_document(
    path: PiecewiseRampPath,
    state_path: list[int],
    certification: HistoryCertification,
    *,
    sample_count: int,
) -> dict[str, object]:
    data = path.sample(sample_count)
    return {
        "state_indices": list(state_path),
        "shift_m": [float(v) for v in data["shift_m"]],
        "q_deg": [degrees(float(v)) for v in data["q_rad"]],
        "ramp_tangent_deg": [float(v) for v in data["ramp_tangent_deg"]],
        "roller_center": {
            "x_m": [float(v) for v in data["roller_center_x_m"]],
            "r_m": [float(v) for v in data["roller_center_r_m"]],
        },
        "ramp_surface": {
            "x_m": [float(v) for v in data["contact_x_m"]],
            "r_m": [float(v) for v in data["contact_r_m"]],
        },
        "history": {
            "max_contact_root_count": certification.max_contact_root_count,
            "multiple_root_shift_count": certification.multiple_root_shift_count,
            "trace_shift_m": list(certification.branch_trace_shift_m),
            "trace_parameter_m": list(certification.branch_trace_parameter_m),
            "trace_q_deg": [degrees(v) for v in certification.branch_trace_q_rad],
        },
    }


def _station_projection(
    viable_nodes: list[set[int]],
    states: tuple[PathState, ...],
    station_count: int,
) -> list[dict[str, float | int | None]]:
    result: list[dict[str, float | int | None]] = []
    for station in range(station_count):
        indices = viable_nodes[station]
        active = [states[i] for i in indices if states[i].dq_dx_rad_per_m > 1.0e-8]
        all_states = [states[i] for i in indices]
        result.append(
            {
                "station": station,
                "viable_state_count": len(indices),
                "q_min_deg": min((degrees(s.q_rad) for s in all_states), default=None),
                "q_max_deg": max((degrees(s.q_rad) for s in all_states), default=None),
                "active_q_min_deg": min((degrees(s.q_rad) for s in active), default=None),
                "active_q_max_deg": max((degrees(s.q_rad) for s in active), default=None),
            }
        )
    return result


def _validate_inputs(
    architecture: ArchitectureDesign,
    shift_station_count: int,
    q_sample_count: int,
    alpha_sample_count: int,
    representative_path_count: int,
    edge_audit_sample_count: int,
    history_trace_sample_count: int,
) -> None:
    if architecture.arm_length_m <= 0.0 or architecture.roller_radius_m <= 0.0:
        raise ValueError("arm and roller radii must be positive")
    if architecture.required_travel_m <= 0.0:
        raise ValueError("required_travel_m must be positive")
    if architecture.ramp_axial_direction not in (-1, 1):
        raise ValueError("ramp_axial_direction must be -1 or +1")
    if architecture.roller_side_sign not in (-1, 1):
        raise ValueError("roller_side_sign must be -1 or +1")
    if shift_station_count < 3:
        raise ValueError("shift_station_count must be at least 3")
    if q_sample_count < 9:
        raise ValueError("q_sample_count must be at least 9")
    if alpha_sample_count < 3:
        raise ValueError("alpha_sample_count must be at least 3")
    if representative_path_count < 1:
        raise ValueError("representative_path_count must be positive")
    if edge_audit_sample_count < 33:
        raise ValueError("edge_audit_sample_count must be at least 33")
    if history_trace_sample_count < 33:
        raise ValueError("history_trace_sample_count must be at least 33")
