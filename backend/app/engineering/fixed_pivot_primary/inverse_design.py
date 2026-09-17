"""Continuous force-to-ramp inverse design for the fixed-pivot primary.

The inverse uses the static limit of the Appendix-D flyweight force law.  For
one constant tip mass per flyweight,

    F / omega^2 = 1/2 dJ_f,p / dx

and the present uniform-arm + concentrated-tip mass model makes the integral of
that relation analytic in sin(q).  A requested force curve therefore determines
q(x) directly once the assembly angle q(0) and tip mass are chosen.  The
physical finite-radius ramp is then reconstructed from the roller-centre path,
not selected from the discrete path-domain graph.

The discrete graph remains useful for capability exploration and initial visual
context, but it is deliberately not part of this inverse solve.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, degrees, isfinite, pi, sin, sqrt
from typing import Iterable

import numpy as np
from scipy.interpolate import PchipInterpolator, make_interp_spline
from shapely.geometry import LineString, Point, Polygon

from .models import ArchitectureDesign, PackagingZone
from .path_domain import (
    PathSegment,
    PiecewiseRampPath,
    _geometry_from_q,
    certify_path_history,
)

Q_MIN = -pi / 6.0
Q_MAX = 0.5 * pi
Q_MAX_DESIGN = np.deg2rad(89.25)
_TANGENT_LIMIT_DEG = 88.5
_OFFSET_MIN = 2.0e-5
_EPS = 1.0e-12


@dataclass(frozen=True, slots=True)
class ForceTargetPoint:
    shift_m: float
    force_N: float


@dataclass(frozen=True, slots=True)
class _MassMoments:
    Mu: float
    Su: float


@dataclass(slots=True)
class _Candidate:
    q0_rad: float
    mass_kg: float
    shift_m: np.ndarray
    target_force_N: np.ndarray
    recovered_force_N: np.ndarray
    q_rad: np.ndarray
    q_prime: np.ndarray
    q_second: np.ndarray
    roller_x: np.ndarray
    roller_r: np.ndarray
    contact_x: np.ndarray
    contact_r: np.ndarray
    tangent_deg: np.ndarray
    offset_factor: np.ndarray
    direction_margin: np.ndarray
    rms_error_N: float
    max_error_N: float
    q_margin_deg: float
    tangent_margin_deg: float
    offset_margin: float
    direction_min: float
    packaging_margin_m: float | None
    score: float
    history: dict[str, object] | None = None


def inverse_design_force_curve(
    architecture: ArchitectureDesign,
    zones: tuple[PackagingZone, ...],
    target_points: tuple[ForceTargetPoint, ...],
    *,
    shaft_speed_rad_s: float,
    max_tip_mass_per_flyweight_kg: float,
    fixed_tip_mass_per_flyweight_kg: float | None = None,
    solution_count: int = 8,
    sample_count: int = 181,
) -> dict[str, object]:
    """Generate physical ramps that reproduce a requested static closing-force curve.

    The requested force is flyweight closing force F_p,fly in the static design
    limit (xdot = xddot = 0).  Dynamic CINDER validation remains a downstream
    step once a concrete ramp is selected.
    """

    if shaft_speed_rad_s <= 0.0:
        raise ValueError("shaft speed must be positive")
    if max_tip_mass_per_flyweight_kg < 0.0:
        raise ValueError("maximum tip mass must be non-negative")
    if max_tip_mass_per_flyweight_kg > architecture.max_tip_mass_per_flyweight_kg + 1e-12:
        raise ValueError("maximum tip mass cannot exceed the architecture limit")
    if fixed_tip_mass_per_flyweight_kg is not None:
        if fixed_tip_mass_per_flyweight_kg < 0.0:
            raise ValueError("fixed tip mass must be non-negative")
        if fixed_tip_mass_per_flyweight_kg > max_tip_mass_per_flyweight_kg + 1e-12:
            raise ValueError("fixed tip mass cannot exceed the inverse-design mass limit")
    if not target_points:
        raise ValueError("at least one force-curve point is required")
    if solution_count < 1:
        raise ValueError("solution_count must be at least one")
    if sample_count < 81:
        raise ValueError("sample_count must be at least 81")

    travel = architecture.required_travel_m
    if travel <= 0.0:
        raise ValueError("required travel must be positive")

    target = _build_target(target_points, travel)
    dense_x = np.linspace(0.0, travel, sample_count)
    dense_target = np.asarray(target(dense_x), dtype=float)
    if np.any(~np.isfinite(dense_target)) or np.any(dense_target < -1e-9):
        raise ValueError("target force must remain finite and non-negative")
    dense_target = np.maximum(dense_target, 0.0)

    antiderivative = target.antiderivative()
    cumulative = (np.asarray(antiderivative(dense_x), dtype=float) - float(antiderivative(0.0))) / (
        shaft_speed_rad_s * shaft_speed_rad_s
    )

    total_force_area = float(np.trapezoid(dense_target, dense_x))
    capacity = _integrated_force_capacity(
        architecture,
        max_tip_mass_per_flyweight_kg,
        shaft_speed_rad_s,
    )

    if fixed_tip_mass_per_flyweight_kg is None:
        mass_grid = _mass_grid(max_tip_mass_per_flyweight_kg, 23)
    else:
        mass_grid = np.asarray([fixed_tip_mass_per_flyweight_kg], dtype=float)

    # The exact inverse leaves q(0) free.  A broad assembly-angle scan is cheap
    # because q(x) itself is algebraic; geometry is only evaluated after this
    # first feasibility screen.
    q0_grid = np.deg2rad(np.linspace(-28.0, 80.0, 55))
    cheap: list[tuple[float, float, float]] = []
    failure_counts: dict[str, int] = {}
    failure_examples: dict[str, dict[str, object]] = {}

    for mass in mass_grid:
        moments = _mass_moments(architecture, float(mass))
        if moments.Su <= _EPS and abs(architecture.pivot_radius_m * moments.Mu) <= _EPS:
            _record_failure(failure_counts, failure_examples, "ZERO_MASS_LEVERAGE", None, None)
            continue
        for q0 in q0_grid:
            q_exact, failure = _inverse_q_profile(
                architecture,
                moments,
                float(q0),
                cumulative,
            )
            if failure is not None:
                _record_failure(failure_counts, failure_examples, failure[0], failure[1], failure[2])
                continue
            assert q_exact is not None
            q_margin = min(float(np.min(q_exact) - Q_MIN), float(Q_MAX_DESIGN - np.max(q_exact)))
            if q_margin <= 0.0:
                _record_failure(failure_counts, failure_examples, "Q_RANGE_EXCEEDED", None, None)
                continue
            cheap.append((float(q0), float(mass), q_margin))

    # Prefer candidates with room on both sides of the q range, but keep broad
    # q0/mass coverage so packaging or finite-roller constraints can choose a
    # different branch without requiring another solve.
    cheap.sort(key=lambda item: item[2], reverse=True)
    # Do not trim the feasible q0/mass cloud by q-margin before diversity
    # selection. Packaging can make a lower-margin branch the only useful one.
    # The analytic inverse is cheap enough that broad coverage here is far more
    # valuable than the old graph-style candidate pruning.
    broad = _diverse_pairs(cheap, max_count=112, max_mass=max_tip_mass_per_flyweight_kg)

    candidates: list[_Candidate] = []
    for q0, mass, _ in broad:
        candidate, failure = _evaluate_candidate(
            architecture,
            zones,
            target,
            shaft_speed_rad_s,
            q0,
            mass,
            sample_count,
        )
        if candidate is None:
            assert failure is not None
            _record_failure(failure_counts, failure_examples, failure[0], failure[1], failure[2])
            continue
        candidates.append(candidate)

    candidates.sort(key=lambda c: (c.rms_error_N, -c.score, c.max_error_N))

    # History certification is the expensive nonlocal test.  Only certify the
    # best/diverse continuous inverse candidates; unlike the old graph workflow,
    # this never runs while the user is merely drawing the target curve.
    certified: list[_Candidate] = []
    for candidate in _diverse_candidates(candidates, max_count=max(24, 4 * solution_count)):
        path = _piecewise_path_from_candidate(architecture, candidate, node_count=25)
        certification = certify_path_history(
            path,
            trace_sample_count=129,
            broad_phase_samples_per_segment=25,
        )
        if not certification.valid:
            failure = certification.failure
            _record_failure(
                failure_counts,
                failure_examples,
                failure.code if failure is not None else "HISTORY_REJECTED",
                failure.shift_m if failure is not None else None,
                failure.message if failure is not None else None,
            )
            continue
        candidate.history = {
            "valid": True,
            "max_contact_root_count": certification.max_contact_root_count,
            "multiple_root_shift_count": certification.multiple_root_shift_count,
        }
        certified.append(candidate)
        if len(certified) >= solution_count:
            break

    solutions = [_candidate_document(candidate) for candidate in certified]
    diagnostics = _diagnostic_documents(failure_counts, failure_examples)

    if total_force_area > capacity["maximum_integrated_force_Nm"] + 1e-9:
        diagnostics.insert(0, {
            "severity": "error" if not solutions else "warning",
            "code": "INTEGRATED_FORCE_CAPACITY_EXCEEDED",
            "message": (
                "The area under the requested force curve exceeds the complete q-range centrifugal "
                "capacity at the allowed maximum tip mass. Reduce the force level, increase speed/mass, "
                "or change the architecture."
            ),
            "target_integrated_force_Nm": total_force_area,
            **capacity,
        })

    if not solutions:
        diagnostics.insert(0, {
            "severity": "error",
            "code": "NO_ADMISSIBLE_CONTINUOUS_INVERSE",
            "message": (
                "The static force curve can be inverted algebraically, but no scanned assembly-angle / "
                "tip-mass realization survived the finite-roller, packaging, and history checks. The "
                "diagnostics below identify the dominant boundaries."
            ),
        })

    return {
        "target": {
            "shaft_speed_rad_s": shaft_speed_rad_s,
            "shift_m": dense_x.tolist(),
            "force_N": dense_target.tolist(),
            "input_points": [
                {"shift_m": float(point.shift_m), "force_N": float(point.force_N)}
                for point in sorted(target_points, key=lambda p: p.shift_m)
            ],
        },
        "solutions": solutions,
        "diagnostics": diagnostics,
        "summary": {
            "method": "analytic_static_inverse_plus_finite_roller_reconstruction",
            "candidate_pair_count": len(cheap),
            "geometry_candidate_count": len(candidates),
            "certified_solution_count": len(solutions),
            "best_rms_error_N": solutions[0]["metrics"]["rms_force_error_N"] if solutions else None,
            "best_max_error_N": solutions[0]["metrics"]["max_force_error_N"] if solutions else None,
            "target_integrated_force_Nm": total_force_area,
            **capacity,
            "fixed_tip_mass_per_flyweight_kg": fixed_tip_mass_per_flyweight_kg,
            "max_tip_mass_per_flyweight_kg": max_tip_mass_per_flyweight_kg,
            "force_definition": (
                "Static flyweight closing force F_p,fly = 0.5 * omega_p^2 * dJ_f,p/dx_p. "
                "Dynamic xdot/xddot flyweight inertia terms are intentionally zero in this design inverse."
            ),
        },
    }


def _build_target(points: tuple[ForceTargetPoint, ...], travel: float) -> PchipInterpolator:
    rows = sorted((float(point.shift_m), float(point.force_N)) for point in points)
    merged: list[tuple[float, float]] = []
    for x, force in rows:
        if x < -1e-12 or x > travel + 1e-12:
            raise ValueError("target point lies outside the required travel")
        x = min(max(x, 0.0), travel)
        if force < 0.0 or not isfinite(force):
            raise ValueError("target forces must be finite and non-negative")
        if merged and abs(merged[-1][0] - x) <= 1e-12:
            merged[-1] = (x, force)
        else:
            merged.append((x, force))
    if len(merged) == 1:
        merged = [(0.0, merged[0][1]), (travel, merged[0][1])]
    else:
        if merged[0][0] > 0.0:
            merged.insert(0, (0.0, merged[0][1]))
        if merged[-1][0] < travel:
            merged.append((travel, merged[-1][1]))
    xs = np.asarray([row[0] for row in merged], dtype=float)
    ys = np.asarray([row[1] for row in merged], dtype=float)
    return PchipInterpolator(xs, ys, extrapolate=False)


def _mass_grid(max_mass: float, count: int) -> np.ndarray:
    if max_mass <= 0.0:
        return np.asarray([0.0], dtype=float)
    # Slightly denser at low masses while retaining both exact endpoints.
    u = np.linspace(0.0, 1.0, count)
    return max_mass * (0.55 * u + 0.45 * u * u)


def _mass_moments(architecture: ArchitectureDesign, tip_mass_kg: float) -> _MassMoments:
    ma = architecture.arm_mass_per_flyweight_kg
    L = architecture.arm_length_m
    return _MassMoments(
        Mu=ma * L / 2.0 + tip_mass_kg * L,
        Su=ma * L * L / 3.0 + tip_mass_kg * L * L,
    )


def _potential(architecture: ArchitectureDesign, moments: _MassMoments, q: float | np.ndarray) -> np.ndarray:
    s = np.sin(q)
    return architecture.number_of_flyweights * (
        architecture.pivot_radius_m * moments.Mu * s + 0.5 * moments.Su * s * s
    )


def _inverse_q_profile(
    architecture: ArchitectureDesign,
    moments: _MassMoments,
    q0: float,
    cumulative_force_over_omega2: np.ndarray,
) -> tuple[np.ndarray | None, tuple[str, float | None, str | None] | None]:
    nf = float(architecture.number_of_flyweights)
    B = architecture.pivot_radius_m * moments.Mu
    S = moments.Su
    u0 = float(_potential(architecture, moments, q0))
    y = u0 + cumulative_force_over_omega2

    if S <= _EPS:
        if abs(B) <= _EPS:
            return None, ("ZERO_MASS_LEVERAGE", None, "The flyweight mass model produces no centrifugal leverage.")
        s = y / (nf * B)
    else:
        disc = B * B + 2.0 * S * y / nf
        if np.any(disc < -1e-11):
            index = int(np.argmin(disc))
            return None, ("INVERSE_BRANCH_LOST", None, f"The analytic sin(q) discriminant becomes negative near sample {index}.")
        disc = np.maximum(disc, 0.0)
        s = (-B + np.sqrt(disc)) / S

    bad = np.where((s < sin(Q_MIN) - 1e-9) | (s > sin(Q_MAX_DESIGN) + 1e-9))[0]
    if bad.size:
        return None, ("Q_RANGE_EXCEEDED", None, "The requested integrated force drives q outside the allowed fixed-pivot range.")
    s = np.clip(s, sin(Q_MIN), sin(Q_MAX_DESIGN))
    q = np.arcsin(s)
    if np.any(np.diff(q) < -1e-9):
        return None, ("MOTION_RATIO_REVERSED", None, "The inverse solution reverses flyweight motion during primary closure.")
    return q, None


def _force_denominator(
    architecture: ArchitectureDesign,
    moments: _MassMoments,
    q: np.ndarray,
) -> np.ndarray:
    return architecture.number_of_flyweights * np.cos(q) * (
        architecture.pivot_radius_m * moments.Mu + moments.Su * np.sin(q)
    )


def _evaluate_candidate(
    architecture: ArchitectureDesign,
    zones: tuple[PackagingZone, ...],
    target: PchipInterpolator,
    omega: float,
    q0: float,
    mass: float,
    sample_count: int,
) -> tuple[_Candidate | None, tuple[str, float | None, str | None] | None]:
    travel = architecture.required_travel_m
    fit_x = np.linspace(0.0, travel, 65)
    target_fit = np.maximum(np.asarray(target(fit_x), dtype=float), 0.0)
    anti = target.antiderivative()
    cumulative = (np.asarray(anti(fit_x), dtype=float) - float(anti(0.0))) / (omega * omega)
    moments = _mass_moments(architecture, mass)
    q_exact, failure = _inverse_q_profile(architecture, moments, q0, cumulative)
    if q_exact is None:
        return None, failure

    try:
        spline = make_interp_spline(fit_x, q_exact, k=5)
    except Exception as error:
        return None, ("PRODUCTION_SPLINE_FAILED", None, str(error))

    xs = np.linspace(0.0, travel, sample_count)
    q = np.asarray(spline(xs), dtype=float)
    qp = np.asarray(spline.derivative(1)(xs), dtype=float)
    qpp = np.asarray(spline.derivative(2)(xs), dtype=float)
    if np.any(~np.isfinite(q)) or np.any(~np.isfinite(qp)) or np.any(~np.isfinite(qpp)):
        return None, ("NONFINITE_PRODUCTION_SPLINE", None, "The C4 production q(x) spline contains non-finite values.")
    bad_qp = np.where(qp <= 1.0e-8)[0]
    if bad_qp.size:
        return None, ("MOTION_RATIO_NONPOSITIVE", float(xs[int(bad_qp[0])]), "The generated q'(x) reaches zero or reverses.")
    if np.min(q) < Q_MIN - 1e-8 or np.max(q) > Q_MAX_DESIGN + 1e-8:
        return None, ("Q_RANGE_EXCEEDED_AFTER_SMOOTHING", None, "C4 production smoothing leaves the admissible q range.")

    H = _force_denominator(architecture, moments, q)
    if np.any(H <= 1e-14):
        index = int(np.argmin(H))
        return None, ("CENTRIFUGAL_LEVERAGE_SINGULAR", float(xs[index]), "dJ/dq loses positive leverage.")
    recovered = omega * omega * H * qp
    target_force = np.maximum(np.asarray(target(xs), dtype=float), 0.0)

    rows = [_geometry_from_q(architecture, float(x), float(a), float(b), float(c)) for x, a, b, c in zip(xs, q, qp, qpp, strict=True)]
    for index, row in enumerate(rows):
        if not all(isfinite(float(value)) for value in row.values()):
            return None, ("NONFINITE_FINITE_ROLLER_GEOMETRY", float(xs[index]), "Finite-roller reconstruction became non-finite.")

    tangent = np.asarray([row["ramp_tangent_deg"] for row in rows], dtype=float)
    offset = np.asarray([row["offset_factor"] for row in rows], dtype=float)
    direction_margin = np.asarray([
        architecture.ramp_axial_direction * row["roller_center_dx_dx"] for row in rows
    ], dtype=float)
    bad = np.where(direction_margin <= 1.0e-8)[0]
    if bad.size:
        return None, ("ROLLER_CENTER_DIRECTION_REVERSAL", float(xs[int(bad[0])]), "The roller-centre locus ceases to progress along the declared ramp direction.")
    bad = np.where(offset <= _OFFSET_MIN)[0]
    if bad.size:
        return None, ("FINITE_ROLLER_OFFSET_SINGULAR", float(xs[int(bad[0])]), "The finite-radius normal offset approaches its curvature singularity.")
    bad = np.where(tangent >= _TANGENT_LIMIT_DEG)[0]
    if bad.size:
        return None, ("RAMP_TANGENT_LIMIT", float(xs[int(bad[0])]), "The generated ramp becomes too close to radial/dead-centre geometry.")

    roller_x = np.asarray([row["roller_center_x_m"] for row in rows], dtype=float)
    roller_r = np.asarray([row["roller_center_r_m"] for row in rows], dtype=float)
    contact_x = np.asarray([row["contact_x_m"] for row in rows], dtype=float)
    contact_r = np.asarray([row["contact_r_m"] for row in rows], dtype=float)

    packaging_ok, packaging_margin, packaging_failure = _check_generated_packaging(
        architecture,
        zones,
        xs,
        roller_x,
        roller_r,
        contact_x,
        contact_r,
    )
    if not packaging_ok:
        return None, packaging_failure

    error = recovered - target_force
    rms = float(np.sqrt(np.mean(error * error)))
    max_error = float(np.max(np.abs(error)))
    q_margin_deg = degrees(min(float(np.min(q) - Q_MIN), float(Q_MAX_DESIGN - np.max(q))))
    tangent_margin = float(_TANGENT_LIMIT_DEG - np.max(tangent))
    offset_margin = float(np.min(offset))
    direction_min = float(np.min(direction_margin))

    # Robustness score only breaks ties between force-faithful solutions.  It is
    # intentionally not a generic smoothness penalty: the requested force shape
    # remains the design objective.
    score = (
        min(q_margin_deg / 12.0, 2.0)
        + min(tangent_margin / 12.0, 2.0)
        + min(offset_margin / 0.25, 2.0)
        + min(direction_min / 0.25, 2.0)
    )
    if packaging_margin is not None and np.isfinite(packaging_margin):
        score += min(max(packaging_margin, 0.0) / 0.003, 1.0)

    return _Candidate(
        q0_rad=q0,
        mass_kg=mass,
        shift_m=xs,
        target_force_N=target_force,
        recovered_force_N=recovered,
        q_rad=q,
        q_prime=qp,
        q_second=qpp,
        roller_x=roller_x,
        roller_r=roller_r,
        contact_x=contact_x,
        contact_r=contact_r,
        tangent_deg=tangent,
        offset_factor=offset,
        direction_margin=direction_margin,
        rms_error_N=rms,
        max_error_N=max_error,
        q_margin_deg=q_margin_deg,
        tangent_margin_deg=tangent_margin,
        offset_margin=offset_margin,
        direction_min=direction_min,
        packaging_margin_m=packaging_margin,
        score=score,
    ), None


def _check_generated_packaging(
    architecture: ArchitectureDesign,
    zones: tuple[PackagingZone, ...],
    xs: np.ndarray,
    roller_x: np.ndarray,
    roller_r: np.ndarray,
    contact_x: np.ndarray,
    contact_r: np.ndarray,
) -> tuple[bool, float | None, tuple[str, float | None, str | None] | None]:
    if not zones:
        return True, None, None
    ramp_line = LineString(list(zip(contact_x, contact_r, strict=True)))
    best_margin = float("inf")

    # 41 poses are enough for packaging screening because the final history
    # certification remains continuous-path focused and the zone check is not
    # used to construct the force inverse itself.
    indices = np.unique(np.linspace(0, len(xs) - 1, min(41, len(xs))).round().astype(int))
    for zone in zones:
        polygon = Polygon(zone.polygon_m)
        if polygon.is_empty or not polygon.is_valid or polygon.area <= 0.0:
            return False, None, ("INVALID_PACKAGING_ZONE", None, f"Packaging zone {zone.label!r} is invalid.")
        if zone.rule == "forbid":
            surface = polygon.buffer(zone.clearance_m, quad_segs=8)
            if zone.subject == "ramp":
                distance = float(ramp_line.distance(surface))
                best_margin = min(best_margin, distance)
                if ramp_line.intersects(surface):
                    return False, 0.0, ("PACKAGING_RAMP_KEEP_OUT", None, f"Generated ramp enters keep-out zone {zone.label!r}.")
                continue
            for index in indices:
                x = float(xs[index])
                cx = float(roller_x[index])
                cr = float(roller_r[index])
                point = Point(cx, cr)
                roller_clearance = float(surface.distance(point) - architecture.roller_radius_m)
                px = architecture.pivot_axial_position_m - x
                arm = LineString(((px, architecture.pivot_radius_m), (cx, cr)))
                arm_clearance = float(arm.distance(surface))
                best_margin = min(best_margin, roller_clearance, arm_clearance)
                if roller_clearance <= 1e-12 or arm.intersects(surface):
                    return False, max(0.0, min(roller_clearance, arm_clearance)), (
                        "PACKAGING_FLYWEIGHT_KEEP_OUT",
                        x,
                        f"Flyweight arm/roller enters keep-out zone {zone.label!r}.",
                    )
        else:
            allowed = polygon.buffer(-zone.clearance_m, quad_segs=8)
            if allowed.is_empty:
                return False, 0.0, ("PACKAGING_CONTAINMENT_EMPTY", None, f"Clearance removes all of containment zone {zone.label!r}.")
            if zone.subject == "ramp":
                if not allowed.covers(ramp_line):
                    return False, 0.0, ("PACKAGING_RAMP_CONTAINMENT", None, f"Generated ramp leaves containment zone {zone.label!r}.")
                continue
            roller_allowed = allowed.buffer(-architecture.roller_radius_m, quad_segs=8)
            if roller_allowed.is_empty:
                return False, 0.0, ("PACKAGING_ROLLER_CONTAINMENT_EMPTY", None, f"Roller cannot fit inside containment zone {zone.label!r}.")
            for index in indices:
                x = float(xs[index])
                cx = float(roller_x[index])
                cr = float(roller_r[index])
                px = architecture.pivot_axial_position_m - x
                point = Point(cx, cr)
                arm = LineString(((px, architecture.pivot_radius_m), (cx, cr)))
                if not roller_allowed.covers(point) or not allowed.covers(arm):
                    return False, 0.0, ("PACKAGING_FLYWEIGHT_CONTAINMENT", x, f"Flyweight leaves containment zone {zone.label!r}.")
                best_margin = min(best_margin, float(point.distance(roller_allowed.boundary)), float(arm.distance(allowed.boundary)))

    return True, (best_margin if np.isfinite(best_margin) else None), None


def _piecewise_path_from_candidate(
    architecture: ArchitectureDesign,
    candidate: _Candidate,
    *,
    node_count: int,
) -> PiecewiseRampPath:
    node_x = np.linspace(0.0, architecture.required_travel_m, node_count)
    q_spline = make_interp_spline(candidate.shift_m, candidate.q_rad, k=5)
    q = np.asarray(q_spline(node_x), dtype=float)
    qp = np.asarray(q_spline.derivative(1)(node_x), dtype=float)
    segments: list[PathSegment] = []
    for index in range(node_count - 1):
        segments.append(PathSegment(
            x0_m=float(node_x[index]),
            x1_m=float(node_x[index + 1]),
            q0_rad=float(q[index]),
            q1_rad=float(q[index + 1]),
            m0_rad_per_m=float(qp[index]),
            m1_rad_per_m=float(qp[index + 1]),
        ))
    return PiecewiseRampPath(architecture, tuple(segments))


def _candidate_document(candidate: _Candidate) -> dict[str, object]:
    return {
        "tip_mass_per_flyweight_kg": candidate.mass_kg,
        "initial_q_deg": degrees(candidate.q0_rad),
        "shift_m": candidate.shift_m.tolist(),
        "q_deg": np.degrees(candidate.q_rad).tolist(),
        "q_prime_rad_per_m": candidate.q_prime.tolist(),
        "q_second_rad_per_m2": candidate.q_second.tolist(),
        "ramp_tangent_deg": candidate.tangent_deg.tolist(),
        "roller_center": {"x_m": candidate.roller_x.tolist(), "r_m": candidate.roller_r.tolist()},
        "ramp_surface": {"x_m": candidate.contact_x.tolist(), "r_m": candidate.contact_r.tolist()},
        "force": {
            "target_N": candidate.target_force_N.tolist(),
            "recovered_N": candidate.recovered_force_N.tolist(),
        },
        "metrics": {
            "rms_force_error_N": candidate.rms_error_N,
            "max_force_error_N": candidate.max_error_N,
            "q_margin_deg": candidate.q_margin_deg,
            "ramp_tangent_margin_deg": candidate.tangent_margin_deg,
            "minimum_offset_factor": candidate.offset_margin,
            "minimum_roller_direction_margin": candidate.direction_min,
            "minimum_packaging_margin_m": candidate.packaging_margin_m,
            "robustness_score": candidate.score,
        },
        "history": candidate.history or {"valid": False},
    }


def _integrated_force_capacity(
    architecture: ArchitectureDesign,
    mass: float,
    omega: float,
) -> dict[str, float]:
    moments = _mass_moments(architecture, mass)
    delta_u = float(_potential(architecture, moments, Q_MAX_DESIGN) - _potential(architecture, moments, Q_MIN))
    return {
        "maximum_integrated_force_Nm": max(0.0, omega * omega * delta_u),
        "capacity_q_min_deg": degrees(Q_MIN),
        "capacity_q_max_deg": degrees(Q_MAX_DESIGN),
    }


def _diverse_pairs(
    rows: list[tuple[float, float, float]],
    *,
    max_count: int,
    max_mass: float,
) -> list[tuple[float, float, float]]:
    if len(rows) <= max_count:
        return rows
    selected = [rows[0]]
    remaining = rows[1:]
    q_scale = np.deg2rad(98.0)
    m_scale = max(max_mass, 1e-6)
    while remaining and len(selected) < max_count:
        best_i = 0
        best_value = -1.0
        for index, row in enumerate(remaining):
            q, m, margin = row
            distance = min(
                sqrt(((q - sq) / q_scale) ** 2 + ((m - sm) / m_scale) ** 2)
                for sq, sm, _ in selected
            )
            value = distance + 0.08 * min(margin / np.deg2rad(10.0), 1.0)
            if value > best_value:
                best_value = value
                best_i = index
        selected.append(remaining.pop(best_i))
    return selected


def _diverse_candidates(candidates: list[_Candidate], *, max_count: int) -> list[_Candidate]:
    if len(candidates) <= max_count:
        return candidates
    # Seed with the numerically best candidate; fill with candidates that remain
    # close in force error while spanning assembly angle and mass.
    best = candidates[0]
    error_limit = max(best.rms_error_N + 2.0, 1.35 * best.rms_error_N + 1.0)
    pool = [candidate for candidate in candidates if candidate.rms_error_N <= error_limit]
    if len(pool) < max_count:
        pool = candidates[: min(len(candidates), max_count * 4)]
    selected = [pool[0]]
    remaining = pool[1:]
    q_scale = np.deg2rad(98.0)
    m_scale = max(max(candidate.mass_kg for candidate in pool), 1e-6)
    while remaining and len(selected) < max_count:
        best_i = 0
        best_value = -1e30
        for index, candidate in enumerate(remaining):
            distance = min(
                sqrt(((candidate.q0_rad - other.q0_rad) / q_scale) ** 2 + ((candidate.mass_kg - other.mass_kg) / m_scale) ** 2)
                for other in selected
            )
            value = distance + 0.10 * candidate.score - 0.01 * candidate.rms_error_N
            if value > best_value:
                best_value = value
                best_i = index
        selected.append(remaining.pop(best_i))
    return selected


def _record_failure(
    counts: dict[str, int],
    examples: dict[str, dict[str, object]],
    code: str,
    shift_m: float | None,
    message: str | None,
) -> None:
    counts[code] = counts.get(code, 0) + 1
    if code not in examples:
        examples[code] = {"shift_m": shift_m, "message": message}


def _diagnostic_documents(
    counts: dict[str, int],
    examples: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    labels = {
        "Q_RANGE_EXCEEDED": "The target consumes more flyweight-angle range than this mass/assembly angle provides.",
        "Q_RANGE_EXCEEDED_AFTER_SMOOTHING": "The C3+ production ramp smoothing pushes the angle branch outside its admissible range.",
        "MOTION_RATIO_NONPOSITIVE": "The required q(x) branch reaches zero or reversed motion ratio.",
        "ROLLER_CENTER_DIRECTION_REVERSAL": "The finite-roller centre path reverses in the declared ramp direction.",
        "FINITE_ROLLER_OFFSET_SINGULAR": "Finite roller radius and path curvature approach an offset singularity.",
        "RAMP_TANGENT_LIMIT": "The inverse requires a near-radial/dead-centre ramp orientation.",
        "PACKAGING_RAMP_KEEP_OUT": "The generated physical ramp intersects a ramp keep-out zone.",
        "PACKAGING_FLYWEIGHT_KEEP_OUT": "The flyweight arm or roller intersects a flyweight keep-out zone.",
        "SECOND_SIMULTANEOUS_CONTACT": "The generated ramp produces a second simultaneous roller contact.",
        "RAMP_SELF_INTERSECTION": "The generated physical ramp self-intersects.",
    }
    rows = []
    for code, count in sorted(counts.items(), key=lambda item: item[1], reverse=True):
        example = examples.get(code, {})
        rows.append({
            "severity": "info",
            "code": code,
            "count": count,
            "shift_m": example.get("shift_m"),
            "message": example.get("message") or labels.get(code, "Candidate realizations reached this admissibility boundary."),
        })
    return rows[:12]
