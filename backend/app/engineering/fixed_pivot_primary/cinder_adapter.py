"""Exact CINDER-facing mechanics for the fixed-pivot primary design tool.

This module is the only part of the feature that imports CINDER mechanics.
The requested ramp is always materialized first. Exact contact is then traced
for as much of the requested travel as the mechanism admits. A failed physical
branch therefore still produces a useful design response and drawable ramp.

The production ``PivotedRollerFollowerFlyweightMap`` is compiled as a separate
runtime-compatibility check. Its spline fit is not used as the design tool's
source of truth: the concrete explorer samples the exact CINDER contact branch
and uses CINDER's real ``FixedPivotFlyweightForce`` for load evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, degrees, hypot, isfinite, pi, radians, sin, sqrt

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial import cKDTree

from cinder.model.cvt.actuation import (
    FixedPivotFlyweightForce,
    FixedPivotFlyweightForceSpec,
    FixedPivotFlyweightSample,
    FlyweightMassGeometry,
    PivotedRollerContactSample,
    PivotedRollerFollowerFlyweightMap,
    PivotedRollerFollowerGeometry,
    PivotedRollerFollowerGeometrySpec,
    PulleyActuationContext,
)
from cinder.model.cvt.closure import AffineClosureScalar, ClosureUnknowns
from cinder.model.cvt.profiles import (
    C3TransitionSegment,
    CircularSegment,
    LinearSegment,
    PiecewiseRamp,
)

from .models import ArchitectureDesign, OperatingCondition, RampDesign

HALF_PI = 0.5 * pi


@dataclass(frozen=True, slots=True)
class GeometryPoint:
    shift_m: float
    angle_rad: float
    angle_gradient_rad_per_m: float
    angle_curvature_rad_per_m2: float
    contact_coordinate_m: float
    contact_x_m: float
    contact_r_m: float
    roller_center_x_m: float
    roller_center_r_m: float
    ramp_tangent_deg: float
    ramp_normal_x: float
    ramp_normal_r: float


@dataclass(frozen=True, slots=True)
class DoubleContactEvent:
    shift_m: float
    angle_rad: float
    roller_center_x_m: float
    roller_center_r_m: float
    contact_coordinate_1_m: float
    contact_x_1_m: float
    contact_r_1_m: float
    contact_coordinate_2_m: float
    contact_x_2_m: float
    contact_r_2_m: float


@dataclass(frozen=True, slots=True)
class GeometryAnalysis:
    architecture: ArchitectureDesign
    ramp_design: RampDesign
    ramp: PiecewiseRamp
    geometry_spec: PivotedRollerFollowerGeometrySpec
    points: tuple[GeometryPoint, ...]
    requested_travel_m: float
    contact_valid_travel_m: float
    contact_range_complete: bool
    failure_code: str | None
    failure_message: str | None
    failure_shift_m: float | None
    double_contact_event: DoubleContactEvent | None
    runtime_map_compiled: bool
    runtime_map_compile_error: str | None
    ramp_surface_open_x_m: tuple[float, ...]
    ramp_surface_open_r_m: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class _SingleSampleMap:
    """Minimal structural implementation of CINDER's FixedPivotFlyweightMap."""

    sample: FixedPivotFlyweightSample
    axial_position_min: float = 0.0
    axial_position_max: float = 1.0

    def evaluate(self, axial_position: float) -> FixedPivotFlyweightSample:
        del axial_position
        return self.sample


def build_ramp(design: RampDesign) -> PiecewiseRamp:
    _validate_ramp_design(design)
    if design.kind == "constant":
        return PiecewiseRamp(
            (
                LinearSegment(
                    length=design.constant_length_m,
                    angle_degrees=design.linear_angle_deg,
                ),
            )
        )

    linear = LinearSegment(
        length=design.linear_length_m,
        angle_degrees=design.linear_angle_deg,
    )
    circular = CircularSegment(
        length=design.circular_length_m,
        angle_start_degrees=design.circular_start_angle_deg,
        angle_end_degrees=design.circular_end_angle_deg,
        quadrant=2,
    )
    blend = C3TransitionSegment.between_segments(
        left=linear,
        right=circular,
        length=design.blend_length_m,
    )
    ramp = PiecewiseRamp((linear, blend, circular))
    ramp.require_continuity(order=3)
    return ramp


def requested_ramp_surface(
    architecture: ArchitectureDesign,
    ramp_design: RampDesign,
    *,
    sample_count: int = 241,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Return the requested physical ramp surface at zero local shift.

    This helper remains useful for concrete-design visualization. Architecture
    mode is deliberately ramp-independent as of Phase 2.1.
    """

    _validate_architecture(architecture)
    if sample_count < 2:
        raise ValueError("sample_count must be at least 2.")
    ramp = build_ramp(ramp_design)
    spec = _geometry_spec(
        architecture,
        ramp_design,
        ramp,
        axial_position_max=architecture.required_travel_m,
    )
    return _sample_ramp_surface(spec, ramp, sample_count)


def analyze_geometry(
    architecture: ArchitectureDesign,
    ramp_design: RampDesign,
    *,
    sample_count: int,
) -> GeometryAnalysis:
    """Analyze one requested physical ramp without hiding rejected geometry.

    Input/profile construction errors still raise. Physical inadmissibility does
    not: the returned analysis contains the requested ramp, the exact valid
    contact prefix (possibly empty), and a structured failure reason/location.
    """

    _validate_architecture(architecture)
    if sample_count < 3:
        raise ValueError("sample_count must be at least 3.")

    ramp = build_ramp(ramp_design)
    requested_max = architecture.required_travel_m
    full_spec = _geometry_spec(
        architecture,
        ramp_design,
        ramp,
        axial_position_max=requested_max,
    )
    provisional = PivotedRollerFollowerGeometry(full_spec)

    open_x, open_r = _sample_ramp_surface(full_spec, ramp, max(161, sample_count))

    probe_count = max(2049, 12 * sample_count + 1)
    probe = np.linspace(0.0, requested_max, probe_count)

    branch_error: str | None = None
    try:
        provisional.trace_contact_branch(probe, require_complete=True)
    except (TypeError, ValueError, RuntimeError) as error:
        branch_error = str(error)

    try:
        probe_trace = provisional.trace_contact_branch(probe, require_complete=False)
    except (TypeError, ValueError, RuntimeError) as error:
        if branch_error is None:
            branch_error = str(error)
        probe_trace = ()

    complete = len(probe_trace) == len(probe)
    if probe_trace:
        valid_max = float(probe[len(probe_trace) - 1])
    else:
        valid_max = 0.0

    failure_code: str | None = None
    failure_message: str | None = None
    failure_shift: float | None = None
    if not complete:
        failure_code, failure_message = _classify_branch_failure(branch_error)
        failed_index = min(len(probe_trace), len(probe) - 1)
        failure_shift = float(probe[failed_index])

    # A two-point roller contact can be an isolated event in shift, so a
    # discrete branch trace may step across it and only notice a later
    # penetration/contact-loss failure. Detect the event from the geometry
    # itself: two distinct ramp coordinates have the same finite-radius roller
    # centre exactly when CINDER's roller-centre offset curve self-intersects.
    # Candidate intersections are refined as continuous roots and then checked
    # against the history-selected CINDER contact branch.
    double_contact_event = _first_selected_double_contact_event(
        provisional,
        full_spec,
        ramp,
        requested_travel_m=requested_max,
    )
    if double_contact_event is not None and (
        failure_shift is None or double_contact_event.shift_m < failure_shift
    ):
        complete = False
        valid_max = double_contact_event.shift_m
        failure_code = "SECOND_CONTACT"
        failure_message = (
            "The roller reaches two distinct points on the physical ramp at "
            "the same instant; the continuous single-contact branch ends here."
        )
        failure_shift = double_contact_event.shift_m

    points = _sample_exact_geometry_points(
        provisional,
        full_spec,
        ramp,
        contact_valid_travel_m=valid_max,
        contact_range_complete=complete,
        requested_travel_m=requested_max,
        sample_count=sample_count,
    )

    runtime_map_compiled = False
    runtime_map_compile_error: str | None = None
    if complete and points and all(point.angle_rad <= HALF_PI + 1.0e-10 for point in points):
        try:
            _build_production_map(
                architecture,
                ramp_design,
                ramp,
                axial_position_max=requested_max,
                compilation_points=max(129, min(513, 2 * sample_count + 1)),
            )
            runtime_map_compiled = True
        except (TypeError, ValueError, RuntimeError) as error:
            # This is intentionally not folded into physical geometry validity.
            # In particular, CINDER's clamped cubic runtime interpolation can
            # overshoot between perfectly admissible exact samples and produce a
            # non-positive spline dq/dx. The design tool keeps showing/evaluating
            # the exact branch while reporting that runtime-compatibility issue.
            runtime_map_compile_error = str(error)

    return GeometryAnalysis(
        architecture=architecture,
        ramp_design=ramp_design,
        ramp=ramp,
        geometry_spec=full_spec,
        points=points,
        requested_travel_m=requested_max,
        contact_valid_travel_m=(requested_max if complete else valid_max),
        contact_range_complete=complete,
        failure_code=failure_code,
        failure_message=failure_message,
        failure_shift_m=failure_shift,
        double_contact_event=double_contact_event if failure_code == "SECOND_CONTACT" else None,
        runtime_map_compiled=runtime_map_compiled,
        runtime_map_compile_error=runtime_map_compile_error,
        ramp_surface_open_x_m=open_x,
        ramp_surface_open_r_m=open_r,
    )


def evaluate_response(
    analysis: GeometryAnalysis,
    operating: OperatingCondition,
) -> dict[str, list[float | bool | None]]:
    """Evaluate one operating condition over the exact admitted geometry path."""
    if operating.tip_mass_per_flyweight_kg < 0.0:
        raise ValueError("tip mass per flyweight must be non-negative.")

    architecture = analysis.architecture
    mass = FlyweightMassGeometry.uniform_arm_with_end_mass(
        number_of_flyweights=architecture.number_of_flyweights,
        arm_length=architecture.arm_length_m,
        arm_mass_per_flyweight=architecture.arm_mass_per_flyweight_kg,
        end_mass_per_flyweight=operating.tip_mass_per_flyweight_kg,
        second_moment_z_per_flyweight=0.0,
    )
    unknowns = ClosureUnknowns.zeros()

    output: dict[str, list[float | bool | None]] = {
        "flyweight_centrifugal_force_N": [],
        "flyweight_axial_inertia_force_N": [],
        "flyweight_curvature_force_N": [],
        "flyweight_total_closing_force_N": [],
        "ramp_force_normal_N": [],
        "ramp_force_axial_N": [],
        "ramp_force_radial_N": [],
        "ramp_moment_about_anchor_Nm": [],
        "com_x_m": [],
        "com_r_m": [],
        "equivalent_centrifugal_force_N": [],
        "pivot_reaction_axial_N": [],
        "pivot_reaction_radial_N": [],
        "pivot_reaction_tangential_N": [],
        "pivot_reaction_resultant_N": [],
        "compressive_contact": [],
    }

    for point in analysis.points:
        if point.angle_rad > HALF_PI + 1.0e-10:
            _append_invalid_load_point(output)
            continue

        d_j_d_q = mass.shaft_inertia_angle_gradient(
            angle=point.angle_rad,
            pivot_radius=architecture.pivot_radius_m,
        )
        sample = FixedPivotFlyweightSample(
            angle=point.angle_rad,
            angle_gradient=point.angle_gradient_rad_per_m,
            angle_curvature=point.angle_curvature_rad_per_m2,
            shaft_inertia=mass.shaft_inertia(
                angle=point.angle_rad,
                pivot_radius=architecture.pivot_radius_m,
            ),
            shaft_inertia_gradient=(d_j_d_q * point.angle_gradient_rad_per_m),
            pivot_inertia=mass.pivot_inertia,
        )
        law = FixedPivotFlyweightForce(
            FixedPivotFlyweightForceSpec(mechanism_map=_SingleSampleMap(sample))
        )
        context = PulleyActuationContext(
            time=0.0,
            axial_position=point.shift_m,
            axial_speed=operating.shift_speed_m_s,
            shaft_speed=operating.shaft_speed_rad_s,
            shift_speed=operating.shift_speed_m_s,
            axial_acceleration=AffineClosureScalar.constant(operating.shift_acceleration_m_s2),
        )
        contributions = {
            contribution.key: contribution.relation.evaluate(unknowns)
            for contribution in law.inspect(context)
        }
        total = law.evaluate(context).evaluate(unknowns)

        count = architecture.number_of_flyweights
        per_ramp_axial = total / count
        if abs(point.ramp_normal_x) <= 1.0e-10:
            normal_force = None
            per_ramp_radial = None
            moment = None
        else:
            normal_force = per_ramp_axial / point.ramp_normal_x
            per_ramp_radial = normal_force * point.ramp_normal_r
            anchor_x = analysis.geometry_spec.ramp_reference_axial_position + point.shift_m
            anchor_r = analysis.geometry_spec.ramp_reference_radius
            dx = point.contact_x_m - anchor_x
            dr = point.contact_r_m - anchor_r
            moment = dx * per_ramp_radial - dr * per_ramp_axial

        m = mass.mass_per_flyweight
        u_bar = mass.first_moment_u / m
        v_bar = mass.first_moment_v / m
        q = point.angle_rad
        x_rel = u_bar * cos(q) - v_bar * sin(q)
        r_rel = u_bar * sin(q) + v_bar * cos(q)
        com_x = architecture.pivot_axial_position_m + x_rel
        com_r = architecture.pivot_radius_m + r_rel

        q_dot = point.angle_gradient_rad_per_m * operating.shift_speed_m_s
        q_ddot = (
            point.angle_gradient_rad_per_m * operating.shift_acceleration_m_s2
            + point.angle_curvature_rad_per_m2 * operating.shift_speed_m_s**2
        )
        dx_dq = -r_rel
        d2x_dq2 = -x_rel
        dr_dq = x_rel
        d2r_dq2 = -r_rel
        com_x_accel = dx_dq * q_ddot + d2x_dq2 * q_dot**2
        com_r_dot = dr_dq * q_dot
        com_r_accel = dr_dq * q_ddot + d2r_dq2 * q_dot**2 - com_r * operating.shaft_speed_rad_s**2
        com_theta_accel = 2.0 * com_r_dot * operating.shaft_speed_rad_s

        if per_ramp_radial is None:
            pivot_x = None
            pivot_r = None
            pivot_theta = None
            pivot_resultant = None
        else:
            pivot_x = m * com_x_accel + per_ramp_axial
            pivot_r = m * com_r_accel + per_ramp_radial
            pivot_theta = m * com_theta_accel
            pivot_resultant = sqrt(pivot_x**2 + pivot_r**2 + pivot_theta**2)

        equivalent_centrifugal = m * operating.shaft_speed_rad_s**2 * com_r

        output["flyweight_centrifugal_force_N"].append(
            float(contributions["fixed_pivot_flyweight_centrifugal"])
        )
        output["flyweight_axial_inertia_force_N"].append(
            float(contributions["fixed_pivot_flyweight_axial_inertia"])
        )
        output["flyweight_curvature_force_N"].append(
            float(contributions["fixed_pivot_flyweight_motion_ratio_curvature"])
        )
        output["flyweight_total_closing_force_N"].append(float(total))
        output["ramp_force_normal_N"].append(None if normal_force is None else float(normal_force))
        output["ramp_force_axial_N"].append(float(per_ramp_axial))
        output["ramp_force_radial_N"].append(
            None if per_ramp_radial is None else float(per_ramp_radial)
        )
        output["ramp_moment_about_anchor_Nm"].append(None if moment is None else float(moment))
        output["com_x_m"].append(float(com_x))
        output["com_r_m"].append(float(com_r))
        output["equivalent_centrifugal_force_N"].append(float(equivalent_centrifugal))
        output["pivot_reaction_axial_N"].append(None if pivot_x is None else float(pivot_x))
        output["pivot_reaction_radial_N"].append(None if pivot_r is None else float(pivot_r))
        output["pivot_reaction_tangential_N"].append(
            None if pivot_theta is None else float(pivot_theta)
        )
        output["pivot_reaction_resultant_N"].append(
            None if pivot_resultant is None else float(pivot_resultant)
        )
        output["compressive_contact"].append(bool(normal_force is not None and normal_force >= 0.0))

    return output


def _append_invalid_load_point(
    output: dict[str, list[float | bool | None]],
) -> None:
    for key, values in output.items():
        values.append(False if key == "compressive_contact" else None)


def _sample_exact_geometry_points(
    geometry: PivotedRollerFollowerGeometry,
    spec: PivotedRollerFollowerGeometrySpec,
    ramp: PiecewiseRamp,
    *,
    contact_valid_travel_m: float,
    contact_range_complete: bool,
    requested_travel_m: float,
    sample_count: int,
) -> tuple[GeometryPoint, ...]:
    end = requested_travel_m if contact_range_complete else contact_valid_travel_m
    if end <= 0.0:
        positions = np.asarray([0.0], dtype=float)
    else:
        positions = np.linspace(0.0, end, sample_count)
    try:
        trace = geometry.trace_contact_branch(positions, require_complete=False)
    except (TypeError, ValueError, RuntimeError):
        return ()

    return tuple(
        _geometry_point_from_contact(
            spec,
            ramp,
            float(positions[index]),
            contact,
        )
        for index, contact in enumerate(trace)
    )


def _sample_ramp_surface(
    spec: PivotedRollerFollowerGeometrySpec,
    ramp: PiecewiseRamp,
    sample_count: int,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    coordinates = np.linspace(ramp.x_min, ramp.x_max, sample_count)
    xs: list[float] = []
    rs: list[float] = []
    for coordinate in coordinates:
        profile = ramp.evaluate(float(coordinate))
        xs.append(
            spec.ramp_reference_axial_position + spec.ramp_axial_direction * float(coordinate)
        )
        rs.append(spec.ramp_reference_radius + profile.value)
    return tuple(xs), tuple(rs)


def _first_selected_double_contact_event(
    geometry: PivotedRollerFollowerGeometry,
    spec: PivotedRollerFollowerGeometrySpec,
    ramp: PiecewiseRamp,
    *,
    requested_travel_m: float,
) -> DoubleContactEvent | None:
    """Return the earliest exact two-point contact on the selected branch.

    The moving ramp translates rigidly in the axial direction. Consequently,
    two distinct physical ramp points can touch one finite-radius roller at the
    same instant only if their zero-shift roller-centre offset points coincide.
    This routine therefore finds self-intersections of CINDER's exact offset
    curve, converts each intersection into the fixed-arm shift(s) that can reach
    it, and asks CINDER's existing branch/non-interference logic whether that
    event belongs to the history-selected physical branch.

    A private CINDER offset-curve primitive is used here deliberately because
    CINDER does not yet expose this design/event query publicly. Keeping that
    dependency isolated in the adapter makes it straightforward to replace with
    a public CINDER API later without leaking mechanics into the service/UI.
    """

    intersections = _offset_curve_self_intersections(geometry, spec, ramp)
    events: list[DoubleContactEvent] = []
    for xi_1, xi_2, center_x_zero, center_r in intersections:
        radial = center_r - spec.pivot_radius
        radicand = spec.arm_length**2 - radial**2
        reach_tolerance = max(
            128.0 * spec.coordinate_tolerance * max(spec.arm_length, 1.0),
            1.0e-14,
        )
        if radicand < -reach_tolerance:
            continue
        axial_magnitude = sqrt(max(0.0, radicand))

        for signed_axial in (-axial_magnitude, axial_magnitude):
            shift = spec.pivot_axial_position + signed_axial - center_x_zero
            if (
                shift < spec.axial_position_min - spec.coordinate_tolerance
                or shift > requested_travel_m + spec.coordinate_tolerance
            ):
                continue
            shift = min(requested_travel_m, max(spec.axial_position_min, shift))
            angle = atan2(radial, signed_axial)
            if not _cinder_confirms_selected_double_contact(
                geometry,
                shift_m=shift,
            ):
                continue

            contact_1_x, contact_1_r = geometry.ramp_surface_point(
                contact_coordinate=xi_1,
                axial_position=shift,
            )
            contact_2_x, contact_2_r = geometry.ramp_surface_point(
                contact_coordinate=xi_2,
                axial_position=shift,
            )
            events.append(
                DoubleContactEvent(
                    shift_m=float(shift),
                    angle_rad=float(angle),
                    roller_center_x_m=float(center_x_zero + shift),
                    roller_center_r_m=float(center_r),
                    contact_coordinate_1_m=float(xi_1),
                    contact_x_1_m=float(contact_1_x),
                    contact_r_1_m=float(contact_1_r),
                    contact_coordinate_2_m=float(xi_2),
                    contact_x_2_m=float(contact_2_x),
                    contact_r_2_m=float(contact_2_r),
                )
            )

    if not events:
        return None
    return min(events, key=lambda event: event.shift_m)


def _offset_curve_self_intersections(
    geometry: PivotedRollerFollowerGeometry,
    spec: PivotedRollerFollowerGeometrySpec,
    ramp: PiecewiseRamp,
) -> tuple[tuple[float, float, float, float], ...]:
    """Find exact distinct-coordinate self-intersections of the offset curve.

    A deterministic geometric discretization is used only to seed candidate
    roots. Acceptance is based on the continuous two-equation root

        C(xi_1) - C(xi_2) = 0,  xi_1 != xi_2,

    evaluated with CINDER's exact offset geometry. Therefore the detected event
    location does not depend on the concrete-design shift sampling grid or on a
    heuristic 'large contact-coordinate jump'.
    """

    if ramp.x_max <= ramp.x_min:
        return ()

    # Preserve piece boundaries in the seed mesh. Transverse crossings are
    # caught by chord/chord intersections; near-tangent self-touches are also
    # seeded from spatially-near nonlocal samples. Root refinement below is the
    # authority in both cases.
    coordinates: list[float] = []
    start = ramp.x_min
    for segment in ramp.segments:
        end = start + segment.length
        local = np.linspace(start, end, 257)
        if coordinates:
            local = local[1:]
        coordinates.extend(float(value) for value in local)
        start = end

    center_rows: list[tuple[float, float]] = []
    for xi in coordinates:
        curve = geometry._offset_curve(xi=xi, axial_position=0.0)
        center_rows.append((curve.x, curve.radius))
    centers = np.asarray(center_rows, dtype=float)
    xis = np.asarray(coordinates, dtype=float)
    seeds: list[tuple[float, float]] = []
    seed_keys: set[tuple[int, int]] = set()
    seed_resolution = max((ramp.x_max - ramp.x_min) / 1024.0, 1.0e-8)

    def add_seed(value_1: float, value_2: float) -> None:
        xi_1, xi_2 = sorted((float(value_1), float(value_2)))
        key = (
            int(round((xi_1 - ramp.x_min) / seed_resolution)),
            int(round((xi_2 - ramp.x_min) / seed_resolution)),
        )
        if key in seed_keys:
            return
        seed_keys.add(key)
        seeds.append((xi_1, xi_2))

    def cross_2d(a: np.ndarray, b: np.ndarray) -> float:
        return float(a[0] * b[1] - a[1] * b[0])

    # Exact crossings of the seed chords. Adjacent parameter intervals describe
    # the same local branch and are intentionally ignored.
    chord_count = len(xis) - 1
    for i in range(chord_count):
        p = centers[i]
        r = centers[i + 1] - p
        for j in range(i + 2, chord_count):
            if j == i + 1:
                continue
            q = centers[j]
            s = centers[j + 1] - q
            denominator = cross_2d(r, s)
            scale = max(float(np.linalg.norm(r) * np.linalg.norm(s)), 1.0e-30)
            if abs(denominator) <= 1.0e-12 * scale:
                continue
            delta = q - p
            t = cross_2d(delta, s) / denominator
            u = cross_2d(delta, r) / denominator
            if -1.0e-12 <= t <= 1.0 + 1.0e-12 and -1.0e-12 <= u <= 1.0 + 1.0e-12:
                seed_1 = xis[i] + min(1.0, max(0.0, t)) * (xis[i + 1] - xis[i])
                seed_2 = xis[j] + min(1.0, max(0.0, u)) * (xis[j + 1] - xis[j])
                add_seed(float(seed_1), float(seed_2))

    # A tangential self-touch need not make two chords cross. Search only for
    # spatially-near *nonlocal* samples to provide additional root seeds. The
    # radius is derived from the geometric seed spacing and is not an event
    # acceptance threshold.
    if len(centers) >= 3:
        chord_lengths = np.linalg.norm(np.diff(centers, axis=0), axis=1)
        finite_lengths = chord_lengths[np.isfinite(chord_lengths)]
        if finite_lengths.size:
            seed_radius = max(8.0 * float(np.max(finite_lengths)), 1.0e-8)
            tree = cKDTree(centers)
            neighbor_count = min(24, len(centers))
            distances, neighbors = tree.query(centers, k=neighbor_count)
            distances = np.atleast_2d(distances)
            neighbors = np.atleast_2d(neighbors)
            for i in range(len(centers)):
                for distance, raw_j in zip(distances[i], neighbors[i], strict=True):
                    j = int(raw_j)
                    if j <= i or abs(i - j) <= 12:
                        continue
                    if not isfinite(float(distance)) or float(distance) > seed_radius:
                        continue
                    add_seed(float(xis[i]), float(xis[j]))

    if not seeds:
        return ()

    separation_tolerance = max(
        256.0 * spec.coordinate_tolerance,
        1.0e-10,
    )
    center_tolerance = max(
        256.0 * spec.coordinate_tolerance,
        5.0e-11,
    )

    def residual(values: np.ndarray) -> np.ndarray:
        xi_1 = float(values[0])
        xi_2 = float(values[1])
        c1 = geometry._offset_curve(xi=xi_1, axial_position=0.0)
        c2 = geometry._offset_curve(xi=xi_2, axial_position=0.0)
        return np.asarray([c1.x - c2.x, c1.radius - c2.radius], dtype=float)

    def jacobian(values: np.ndarray) -> np.ndarray:
        xi_1 = float(values[0])
        xi_2 = float(values[1])
        c1 = geometry._offset_curve(xi=xi_1, axial_position=0.0)
        c2 = geometry._offset_curve(xi=xi_2, axial_position=0.0)
        return np.asarray(
            [
                [c1.dx_dxi, -c2.dx_dxi],
                [c1.dr_dxi, -c2.dr_dxi],
            ],
            dtype=float,
        )

    roots: list[tuple[float, float, float, float]] = []
    for raw_seed_1, raw_seed_2 in seeds:
        seed_1, seed_2 = sorted((raw_seed_1, raw_seed_2))
        if seed_2 - seed_1 <= separation_tolerance:
            continue
        try:
            solved = least_squares(
                residual,
                np.asarray([seed_1, seed_2], dtype=float),
                jac=jacobian,
                bounds=(
                    np.asarray([ramp.x_min, ramp.x_min], dtype=float),
                    np.asarray([ramp.x_max, ramp.x_max], dtype=float),
                ),
                xtol=1.0e-14,
                ftol=1.0e-14,
                gtol=1.0e-14,
                max_nfev=200,
            )
        except (TypeError, ValueError, RuntimeError):
            continue
        xi_1, xi_2 = sorted((float(solved.x[0]), float(solved.x[1])))
        if xi_2 - xi_1 <= separation_tolerance:
            continue
        delta = residual(np.asarray([xi_1, xi_2], dtype=float))
        if not np.all(np.isfinite(delta)) or float(np.linalg.norm(delta)) > center_tolerance:
            continue
        c1 = geometry._offset_curve(xi=xi_1, axial_position=0.0)
        c2 = geometry._offset_curve(xi=xi_2, axial_position=0.0)
        center_x = 0.5 * (c1.x + c2.x)
        center_r = 0.5 * (c1.radius + c2.radius)
        if not (isfinite(center_x) and isfinite(center_r)):
            continue

        duplicate = any(
            abs(xi_1 - existing[0]) <= 32.0 * separation_tolerance
            and abs(xi_2 - existing[1]) <= 32.0 * separation_tolerance
            for existing in roots
        )
        if not duplicate:
            roots.append((xi_1, xi_2, float(center_x), float(center_r)))

    roots.sort(key=lambda item: (item[0], item[1]))
    return tuple(roots)


def _cinder_confirms_selected_double_contact(
    geometry: PivotedRollerFollowerGeometry,
    *,
    shift_m: float,
) -> bool:
    """Use CINDER's existing physical non-interference check as confirmation."""

    if shift_m < geometry.spec.axial_position_min:
        return False
    if shift_m == geometry.spec.axial_position_min:
        positions = np.asarray([shift_m], dtype=float)
    else:
        positions = np.linspace(
            geometry.spec.axial_position_min,
            shift_m,
            1025,
        )
    try:
        geometry.trace_contact_branch(positions, require_complete=True)
    except (TypeError, ValueError, RuntimeError) as error:
        detail = str(error).lower()
        return "second simultaneous physical ramp contact" in detail
    return False


def _classify_branch_failure(error_message: str | None) -> tuple[str, str]:
    detail = (error_message or "").lower()
    if "no roller/ramp contact exists at the beginning" in detail:
        return (
            "NO_INITIAL_CONTACT",
            "No roller/ramp contact exists at the fully-open position.",
        )
    if "no mathematical contact exists" in detail:
        return (
            "CONTACT_LOST",
            "The continuous roller/ramp contact branch ends before the required travel is complete.",
        )
    if "second simultaneous physical ramp contact" in detail:
        return (
            "SECOND_CONTACT",
            "The roller reaches a second simultaneous physical contact with the ramp.",
        )
    if "penetrates another portion" in detail:
        return (
            "RAMP_INTERFERENCE",
            "The selected roller configuration intersects another portion of the physical ramp.",
        )
    if "jumping to a disconnected" in detail:
        return (
            "CONTACT_BRANCH_DISCONTINUITY",
            "The selected contact branch would have to jump to a disconnected mathematical solution.",
        )
    if "fold or dead-centre" in detail:
        return (
            "SINGULAR_CONTACT_KINEMATICS",
            "The roller/ramp branch reaches a fold or dead-centre, so q is no longer a regular function of shift.",
        )
    if "positive outward rotation" in detail:
        return (
            "NON_OUTWARD_ARM_MOTION",
            "The selected contact branch no longer produces finite positive outward flyweight rotation with closure.",
        )
    return (
        "CONTACT_BRANCH_INVALID",
        "The selected roller/ramp contact branch cannot be continued through the requested travel.",
    )


def _build_production_map(
    architecture: ArchitectureDesign,
    ramp_design: RampDesign,
    ramp: PiecewiseRamp,
    *,
    axial_position_max: float,
    compilation_points: int,
) -> PivotedRollerFollowerFlyweightMap:
    # Mass has no effect on q(x). Use the real arm mass and a harmless tiny end
    # mass if necessary so this production map can compile geometry once.
    arm_mass = architecture.arm_mass_per_flyweight_kg
    end_mass = 0.0 if arm_mass > 0.0 else 1.0e-9
    mass = FlyweightMassGeometry.uniform_arm_with_end_mass(
        number_of_flyweights=architecture.number_of_flyweights,
        arm_length=architecture.arm_length_m,
        arm_mass_per_flyweight=arm_mass,
        end_mass_per_flyweight=end_mass,
        second_moment_z_per_flyweight=0.0,
    )
    return PivotedRollerFollowerFlyweightMap(
        geometry_spec=_geometry_spec(
            architecture,
            ramp_design,
            ramp,
            axial_position_max=axial_position_max,
        ),
        mass_geometry=mass,
        compilation_points=compilation_points,
    )


def _ramp_reference_from_initial_angle(
    architecture: ArchitectureDesign,
    ramp_design: RampDesign,
    ramp: PiecewiseRamp,
) -> tuple[float, float]:
    """Place profile coordinate zero at the requested initial roller contact.

    At zero sheave shift the roller centre is fixed by the architecture and the
    requested initial flyweight angle.  The local tangent of the first ramp
    point fixes CINDER's finite-roller contact normal, so the physical surface
    point follows directly.  This removes the old arbitrary Point-A axial and
    radial placement parameters.
    """

    q = radians(ramp_design.initial_flyweight_angle_deg)
    center_x = architecture.pivot_axial_position_m + architecture.arm_length_m * cos(q)
    center_r = architecture.pivot_radius_m + architecture.arm_length_m * sin(q)

    initial = ramp.evaluate(ramp.x_min)
    slope = initial.first_derivative
    norm = sqrt(1.0 + slope * slope)
    sign = float(architecture.roller_side_sign)
    direction = float(architecture.ramp_axial_direction)
    normal_x = -sign * slope / norm
    normal_r = sign * direction / norm

    return (
        center_x - architecture.roller_radius_m * normal_x,
        center_r - architecture.roller_radius_m * normal_r,
    )


def _geometry_spec(
    architecture: ArchitectureDesign,
    ramp_design: RampDesign,
    ramp: PiecewiseRamp,
    *,
    axial_position_max: float,
) -> PivotedRollerFollowerGeometrySpec:
    ramp_reference_x, ramp_reference_r = _ramp_reference_from_initial_angle(
        architecture, ramp_design, ramp
    )
    return PivotedRollerFollowerGeometrySpec(
        pivot_axial_position=architecture.pivot_axial_position_m,
        pivot_radius=architecture.pivot_radius_m,
        arm_length=architecture.arm_length_m,
        roller_radius=architecture.roller_radius_m,
        ramp_reference_axial_position=ramp_reference_x,
        ramp_reference_radius=ramp_reference_r,
        ramp_profile=ramp,
        ramp_axial_direction=architecture.ramp_axial_direction,
        axial_position_min=0.0,
        axial_position_max=axial_position_max,
        roller_side_sign=architecture.roller_side_sign,
        root_scan_points=513,
        validation_positions=129,
    )


def _geometry_point_from_contact(
    spec: PivotedRollerFollowerGeometrySpec,
    ramp: PiecewiseRamp,
    shift_m: float,
    contact: PivotedRollerContactSample,
) -> GeometryPoint:
    profile = ramp.evaluate(contact.contact_coordinate)
    contact_x = (
        spec.ramp_reference_axial_position
        + shift_m
        + spec.ramp_axial_direction * contact.contact_coordinate
    )
    contact_r = spec.ramp_reference_radius + profile.value

    dx = contact.roller_center_axial_position - contact_x
    dr = contact.roller_center_radius - contact_r
    length = hypot(dx, dr)
    if length <= 1.0e-14:
        raise RuntimeError("Roller/ramp contact normal is singular.")
    normal_on_ramp_x = -dx / length
    normal_on_ramp_r = -dr / length

    tangent_angle = degrees(atan2(abs(profile.first_derivative), 1.0))
    return GeometryPoint(
        shift_m=shift_m,
        angle_rad=contact.angle,
        angle_gradient_rad_per_m=contact.angle_gradient,
        angle_curvature_rad_per_m2=contact.angle_curvature,
        contact_coordinate_m=contact.contact_coordinate,
        contact_x_m=contact_x,
        contact_r_m=contact_r,
        roller_center_x_m=contact.roller_center_axial_position,
        roller_center_r_m=contact.roller_center_radius,
        ramp_tangent_deg=tangent_angle,
        ramp_normal_x=normal_on_ramp_x,
        ramp_normal_r=normal_on_ramp_r,
    )


def _validate_architecture(architecture: ArchitectureDesign) -> None:
    positive = {
        "pivot_radius_m": architecture.pivot_radius_m,
        "arm_length_m": architecture.arm_length_m,
        "roller_radius_m": architecture.roller_radius_m,
        "required_travel_m": architecture.required_travel_m,
    }
    for name, value in positive.items():
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


def _validate_ramp_design(design: RampDesign) -> None:
    if not -30.0 <= design.initial_flyweight_angle_deg < 90.0:
        raise ValueError(
            "initial_flyweight_angle_deg must lie in the architecture range [-30, 90)."
        )
    if not 0.0 < design.linear_angle_deg < 90.0:
        raise ValueError("linear_angle_deg must lie strictly between 0 and 90 degrees.")
    if design.kind == "constant":
        if design.constant_length_m <= 0.0:
            raise ValueError("constant_length_m must be positive for a constant ramp.")
        return
    if not 0.0 < design.circular_start_angle_deg < 90.0:
        raise ValueError("circular_start_angle_deg must lie strictly between 0 and 90 degrees.")
    if not 0.0 < design.circular_end_angle_deg < 90.0:
        raise ValueError("circular_end_angle_deg must lie strictly between 0 and 90 degrees.")
    if design.circular_start_angle_deg <= design.circular_end_angle_deg:
        raise ValueError(
            "The Q2 circular section requires circular_start_angle_deg > " "circular_end_angle_deg."
        )
    if design.linear_length_m <= 0.0:
        raise ValueError("linear_length_m must be positive for a progressive ramp.")
    if design.blend_length_m <= 0.0:
        raise ValueError("blend_length_m must be positive for a progressive ramp.")
    if design.circular_length_m <= 0.0:
        raise ValueError("circular_length_m must be positive for a progressive ramp.")
