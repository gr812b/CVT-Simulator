"""Mass-scale-agnostic comparison of two fixed-pivot primary architectures.

The comparison intentionally asks a different question from force-to-ramp
inverse design.  Here the object of interest is the family of *complete* ramp
behaviours admitted by each architecture.  Each history-certified path has an
arm-specific normalized force gain A(x) and a tip-mass gain B(x).  Dividing the
arm contribution by arm mass and mixing it with B through a dimensionless mass
fraction produces a specific-force family that is independent of overall
flyweight mass scale and shaft speed.

Two complementary comparisons live here:

* target matching uses the continuous Appendix-D inverse and therefore asks
  whether each architecture can directly realize a user-requested normalized
  force shape;
* discovery uses a sampled atlas of history-certified complete paths to find
  behaviours that expose large architecture-to-architecture differences.

The sampled atlas is intentionally *not* used for target matching.  Keeping
those questions separate avoids presenting a poor atlas neighbour as the
architecture's best achievable response to a requested force curve.
"""

from __future__ import annotations

from dataclasses import replace
from math import degrees

import numpy as np
from scipy.spatial import ConvexHull

from .path_domain import (
    CompiledPathDomain,
    _path_document,
    _path_from_state_indices,
    certify_path_history,
)
from .path_domain_refinement import _candidate_state_paths, _diverse_path_order
from .inverse_design import (
    Q_MAX_DESIGN,
    _Candidate,
    _check_generated_packaging,
    _evaluate_candidate,
    _mass_moments,
    _piecewise_path_from_candidate,
    _potential,
)

_ATLAS_CACHE: dict[tuple[int, int], list[tuple[tuple[int, ...], dict[str, object]]]] = {}


def compare_compiled_domains(
    compiled_a: CompiledPathDomain,
    compiled_b: CompiledPathDomain,
    *,
    atlas_path_count: int = 32,
    mass_mix_count: int = 7,
) -> dict[str, object]:
    if atlas_path_count < 8:
        raise ValueError("atlas_path_count must be at least 8")
    if mass_mix_count < 3:
        raise ValueError("mass_mix_count must be at least 3")

    atlas_a = _certified_atlas(compiled_a, atlas_path_count)
    atlas_b = _certified_atlas(compiled_b, atlas_path_count)
    mixes = np.linspace(0.0, 0.96, mass_mix_count)

    points_a = _shape_points(compiled_a, atlas_a, mixes, label="A")
    points_b = _shape_points(compiled_b, atlas_b, mixes, label="B")

    footprint_a = _footprint_document(points_a)
    footprint_b = _footprint_document(points_b)
    leverage_a = _leverage_envelope(points_a)
    leverage_b = _leverage_envelope(points_b)

    witnesses_a, stats_a = _directional_witnesses(points_a, points_b, "A", "B")
    witnesses_b, stats_b = _directional_witnesses(points_b, points_a, "B", "A")

    return {
        "definition": {
            "mass_agnostic": True,
            "specific_gain": (
                "For mass mix w = m_tip/(m_arm+m_tip), K_specific = "
                "[(1-w)*(K_arm/m_arm) + w*K_tip] / n_f. This is force gain per kg of the "
                "complete flyweight set and per omega^2, so flyweight count, overall mass scale, and RPM are removed."
            ),
            "shape_normalization": (
                "Each complete-path specific-gain curve is divided by its shift-average gain before "
                "projection. c1 is overall progression, c2 primary curvature, c3 higher-order/S-shape content."
            ),
            "sampling_note": (
                "Footprints are sampled from history-certified complete paths and mass-ratio mixes; "
                "they are an exploratory architecture map rather than a proof of the exact continuous hull. "
                "Witness similarity is evaluated over the complete normalized force curve, not only c1/c2/c3."
            ),
        },
        "architecture_a": {
            "domain_id": None,
            "certified_path_count": len(atlas_a),
            "shape_sample_count": len(points_a),
            "footprint": footprint_a,
            "specific_leverage_envelope": leverage_a,
        },
        "architecture_b": {
            "domain_id": None,
            "certified_path_count": len(atlas_b),
            "shape_sample_count": len(points_b),
            "footprint": footprint_b,
            "specific_leverage_envelope": leverage_b,
        },
        "witnesses": {
            "a_not_b": witnesses_a,
            "b_not_a": witnesses_b,
        },
        "summary": {
            "atlas_path_count_requested": atlas_path_count,
            "mass_mix_count": mass_mix_count,
            "a_to_b_median_shape_distance": stats_a["median"],
            "a_to_b_max_shape_distance": stats_a["max"],
            "b_to_a_median_shape_distance": stats_b["median"],
            "b_to_a_max_shape_distance": stats_b["max"],
        },
    }


def _certified_atlas(
    compiled: CompiledPathDomain,
    count: int,
) -> list[tuple[tuple[int, ...], dict[str, object]]]:
    key = (id(compiled), count)
    cached = _ATLAS_CACHE.get(key)
    if cached is not None:
        return cached

    documents: dict[tuple[int, ...], dict[str, object]] = {
        tuple(path): document
        for path, document in zip(
            compiled.representative_state_paths,
            compiled.representative_documents,
            strict=True,
        )
    }
    selected: list[tuple[tuple[int, ...], dict[str, object]]] = []
    for signature in _diverse_path_order(compiled, list(documents)):
        selected.append((signature, documents[signature]))
        if len(selected) >= count:
            _ATLAS_CACHE[key] = selected
            return selected

    candidates = _candidate_state_paths(
        compiled,
        edge_masks=None,
        max_candidates=max(256, 14 * count),
    )
    for path in _diverse_path_order(compiled, candidates):
        signature = tuple(path)
        if signature in documents:
            continue
        ramp = _path_from_state_indices(
            compiled.architecture,
            compiled.states,
            list(signature),
            compiled.shift_station_count,
        )
        certification = certify_path_history(
            ramp,
            trace_sample_count=compiled.history_trace_sample_count,
            broad_phase_samples_per_segment=33,
        )
        if not certification.valid:
            continue
        document = _path_document(
            ramp,
            list(signature),
            certification,
            sample_count=121,
        )
        documents[signature] = document
        selected.append((signature, document))
        if len(selected) >= count:
            break

    _ATLAS_CACHE[key] = selected
    return selected


def _shape_points(
    compiled: CompiledPathDomain,
    atlas: list[tuple[tuple[int, ...], dict[str, object]]],
    mixes: np.ndarray,
    *,
    label: str,
) -> list[dict[str, object]]:
    arm_mass = compiled.architecture.arm_mass_per_flyweight_kg
    rows: list[dict[str, object]] = []
    for path_index, (signature, document) in enumerate(atlas):
        capability = document.get("capability")
        if not isinstance(capability, dict):
            continue
        shift = np.asarray(document.get("shift_m", []), dtype=float)
        arm = np.asarray(capability.get("arm_force_per_omega2", []), dtype=float)
        tip = np.asarray(capability.get("tip_force_per_omega2_per_kg", []), dtype=float)
        if shift.size < 5 or arm.size != shift.size or tip.size != shift.size:
            continue
        flyweight_count = max(int(compiled.architecture.number_of_flyweights), 1)
        if arm_mass > 1e-12:
            arm_specific = arm / (arm_mass * flyweight_count)
        else:
            arm_specific = tip / flyweight_count
        tip_specific = tip / flyweight_count

        xi = 2.0 * (shift - shift[0]) / max(shift[-1] - shift[0], 1e-12) - 1.0
        for mix in mixes:
            specific = (1.0 - mix) * arm_specific + mix * tip_specific
            mean_gain = float(np.trapezoid(specific, xi) / 2.0)
            if not np.isfinite(mean_gain) or mean_gain <= 1e-12:
                continue
            normalized = specific / mean_gain
            residual = normalized - 1.0
            c1 = _legendre_coefficient(xi, residual, 1)
            c2 = _legendre_coefficient(xi, residual, 2)
            c3 = _legendre_coefficient(xi, residual, 3)
            rows.append(
                {
                    "architecture": label,
                    "path_index": path_index,
                    "state_indices": list(signature),
                    "mass_mix_fraction": float(mix),
                    "tip_to_arm_mass_ratio": float(mix / max(1.0 - mix, 1e-12)),
                    "c1": c1,
                    "c2": c2,
                    "c3": c3,
                    "mean_specific_gain": mean_gain,
                    "shift_fraction": (
                        (shift - shift[0]) / max(shift[-1] - shift[0], 1e-12)
                    ).tolist(),
                    "specific_gain": specific.tolist(),
                    "normalized_shape": normalized.tolist(),
                    "ramp": {
                        "shift_m": document.get("shift_m", []),
                        "q_deg": document.get("q_deg", []),
                        "ramp_tangent_deg": document.get("ramp_tangent_deg", []),
                        "roller_center": document.get("roller_center", {}),
                        "ramp_surface": document.get("ramp_surface", {}),
                    },
                }
            )
    return rows


def _legendre_coefficient(x: np.ndarray, residual: np.ndarray, order: int) -> float:
    if order == 1:
        basis = x
    elif order == 2:
        basis = 0.5 * (3.0 * x * x - 1.0)
    elif order == 3:
        basis = 0.5 * (5.0 * x * x * x - 3.0 * x)
    else:
        raise ValueError("only the first three shape coefficients are used")
    return float((2 * order + 1) / 2.0 * np.trapezoid(residual * basis, x))


def _footprint_document(points: list[dict[str, object]]) -> dict[str, object]:
    xy = np.asarray([[float(point["c1"]), float(point["c2"])] for point in points], dtype=float)
    hull: list[list[float]] = []
    if len(xy) >= 3:
        try:
            unique = np.unique(np.round(xy, 12), axis=0)
            if len(unique) >= 3:
                ch = ConvexHull(unique)
                hull = unique[ch.vertices].tolist()
        except Exception:
            hull = []
    return {
        "points": [
            {
                "c1": point["c1"],
                "c2": point["c2"],
                "c3": point["c3"],
                "path_index": point["path_index"],
                "mass_mix_fraction": point["mass_mix_fraction"],
                "mean_specific_gain": point["mean_specific_gain"],
            }
            for point in points
        ],
        "hull_c1_c2": hull,
    }


def _leverage_envelope(
    points: list[dict[str, object]], sample_count: int = 81
) -> dict[str, object]:
    xi = np.linspace(0.0, 1.0, sample_count)
    rows: list[np.ndarray] = []
    for point in points:
        source_x = np.asarray(point["shift_fraction"], dtype=float)
        source_y = np.asarray(point["specific_gain"], dtype=float)
        if source_x.size < 2:
            continue
        rows.append(np.interp(xi, source_x, source_y))
    if not rows:
        return {"shift_fraction": xi.tolist(), "min": [], "max": [], "median": []}
    matrix = np.vstack(rows)
    return {
        "shift_fraction": xi.tolist(),
        "min": np.min(matrix, axis=0).tolist(),
        "max": np.max(matrix, axis=0).tolist(),
        "median": np.median(matrix, axis=0).tolist(),
    }


def _directional_witnesses(
    source: list[dict[str, object]],
    target: list[dict[str, object]],
    source_label: str,
    target_label: str,
) -> tuple[list[dict[str, object]], dict[str, float | None]]:
    """Find source behaviours farthest from the nearest complete target curve.

    c1/c2/c3 are deliberately *not* used as the similarity metric.  They are a
    compact visualization coordinate only.  Nearest neighbours are measured by
    RMS difference over the entire normalized force-shape curve so higher-order
    structure and local excursions remain visible to the comparison.
    """

    if not source or not target:
        return [], {"median": None, "max": None}

    xi = np.linspace(0.0, 1.0, 101)
    source_curves = np.vstack(
        [
            np.interp(
                xi,
                np.asarray(row["shift_fraction"], dtype=float),
                np.asarray(row["normalized_shape"], dtype=float),
            )
            for row in source
        ]
    )
    target_curves = np.vstack(
        [
            np.interp(
                xi,
                np.asarray(row["shift_fraction"], dtype=float),
                np.asarray(row["normalized_shape"], dtype=float),
            )
            for row in target
        ]
    )

    nearest_indices = np.empty(len(source), dtype=int)
    distances = np.empty(len(source), dtype=float)
    for index, curve in enumerate(source_curves):
        delta = target_curves - curve[None, :]
        rms = np.sqrt(np.mean(delta * delta, axis=1))
        nearest = int(np.argmin(rms))
        nearest_indices[index] = nearest
        distances[index] = float(rms[nearest])

    order = np.argsort(-distances)
    witnesses: list[dict[str, object]] = []
    used_paths: set[int] = set()
    for raw_index in order:
        index = int(raw_index)
        row = source[index]
        path_index = int(row["path_index"])
        if path_index in used_paths:
            continue
        nearest = target[int(nearest_indices[index])]
        pointwise = np.abs(source_curves[index] - target_curves[int(nearest_indices[index])])
        gap_index = int(np.argmax(pointwise))
        witnesses.append(
            {
                "source_architecture": source_label,
                "nearest_architecture": target_label,
                "shape_distance": float(distances[index]),
                "max_pointwise_shape_gap": float(pointwise[gap_index]),
                "gap_shift_fraction": float(xi[gap_index]),
                "source": row,
                "nearest": nearest,
            }
        )
        used_paths.add(path_index)
        if len(witnesses) >= 5:
            break

    return witnesses, {
        "median": float(np.median(distances)),
        "max": float(np.max(distances)),
    }


def match_target_shape(
    compiled_a: CompiledPathDomain,
    compiled_b: CompiledPathDomain,
    target_points: list[tuple[float, float]],
    *,
    atlas_path_count: int = 40,
    mass_mix_count: int = 11,
    sample_count: int = 121,
) -> dict[str, object]:
    """Continuously invert one requested force *shape* for both architectures.

    This deliberately does **not** search the sampled path atlas.  Overall force
    magnitude is free, so for a chosen mass distribution, q(0), and q(L), the
    Appendix-D static relation determines the force scale that makes the target
    shape integrate exactly between those two angles.  The analytic Force -> Ramp
    inverse then reconstructs q(x), the finite-radius roller locus, and the
    physical ramp.  Candidates are rejected only by the real geometry,
    packaging, or nonlocal contact-history checks.

    ``atlas_path_count`` is retained in the API signature for backwards
    compatibility with Phase 3.9 callers but is intentionally unused here.
    """
    del atlas_path_count
    if mass_mix_count < 3:
        raise ValueError("mass_mix_count must be at least 3")
    if sample_count < 81:
        # The continuous finite-roller checker is intentionally denser than the
        # old atlas interpolation.
        sample_count = 81
    if len(target_points) < 2:
        raise ValueError("at least two target shape points are required")

    xs, ys, xi, target = _normalized_target_shape(target_points, sample_count)
    result_a, diag_a = _continuous_shape_match(
        compiled_a,
        xs,
        ys,
        xi,
        target,
        mass_mix_count=mass_mix_count,
        sample_count=sample_count,
        label="A",
    )
    result_b, diag_b = _continuous_shape_match(
        compiled_b,
        xs,
        ys,
        xi,
        target,
        mass_mix_count=mass_mix_count,
        sample_count=sample_count,
        label="B",
    )

    return {
        "definition": {
            "mass_scale_agnostic": True,
            "normalization": (
                "Target and generated curves are divided by their own shift-average force. "
                "100% therefore means that curve's own average force."
            ),
            "distance": "Whole-curve RMS difference in normalized force over the complete shift.",
            "sampling_note": (
                "Target matching uses the continuous Appendix-D analytic inverse, not the sampled path atlas. "
                "The search varies assembly angle, flyweight mass distribution, and force scale, then checks "
                "finite-roller geometry, packaging, and complete contact history."
            ),
        },
        "target": {
            "shift_fraction": xi.tolist(),
            "normalized_shape": target.tolist(),
            "input_points": [
                {"shift_fraction": float(x), "relative_force": float(y)} for x, y in target_points
            ],
        },
        "architecture_a": result_a,
        "architecture_b": result_b,
        "summary": {
            "a_rms_shape_error": None if result_a is None else result_a["rms_shape_error"],
            "b_rms_shape_error": None if result_b is None else result_b["rms_shape_error"],
            "a_max_shape_error": None if result_a is None else result_a["max_shape_error"],
            "b_max_shape_error": None if result_b is None else result_b["max_shape_error"],
            "a_diagnostics": diag_a,
            "b_diagnostics": diag_b,
        },
    }


def _normalized_target_shape(
    target_points: list[tuple[float, float]],
    sample_count: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    cleaned = sorted((float(x), float(y)) for x, y in target_points)
    if cleaned[0][0] < -1e-12 or cleaned[-1][0] > 1.0 + 1e-12:
        raise ValueError("target shift fractions must lie in [0, 1]")
    if any(y <= 0.0 or not np.isfinite(y) for _, y in cleaned):
        raise ValueError("target relative force values must be finite and positive")

    dedup: dict[float, float] = {}
    for x, y in cleaned:
        dedup[round(x, 12)] = y
    xs = np.asarray(sorted(dedup), dtype=float)
    ys = np.asarray([dedup[float(x)] for x in xs], dtype=float)
    if xs.size < 2:
        raise ValueError("target shape points must span at least two distinct shift locations")
    if xs[0] > 0.0:
        xs = np.insert(xs, 0, 0.0)
        ys = np.insert(ys, 0, ys[0])
    if xs[-1] < 1.0:
        xs = np.append(xs, 1.0)
        ys = np.append(ys, ys[-1])

    from scipy.interpolate import PchipInterpolator

    xi = np.linspace(0.0, 1.0, sample_count)
    raw_interp = PchipInterpolator(xs, ys, extrapolate=False)
    target_raw = np.asarray(raw_interp(xi), dtype=float)
    if np.any(~np.isfinite(target_raw)) or np.any(target_raw <= 0.0):
        raise ValueError("target interpolation produced a non-positive or non-finite force shape")
    target_mean = float(np.trapezoid(target_raw, xi))
    if target_mean <= 1e-12:
        raise ValueError("target shape has zero average")
    ys_normalized = ys / target_mean
    target = target_raw / target_mean
    return xs, ys_normalized, xi, target


def _continuous_shape_match(
    compiled: CompiledPathDomain,
    target_x: np.ndarray,
    target_y_normalized: np.ndarray,
    output_xi: np.ndarray,
    output_target: np.ndarray,
    *,
    mass_mix_count: int,
    sample_count: int,
    label: str,
) -> tuple[dict[str, object] | None, list[dict[str, object]]]:
    """Find a certified continuous inverse realization of one normalized shape."""
    architecture = compiled.architecture
    travel = float(architecture.required_travel_m)
    if travel <= 0.0:
        raise ValueError("architecture travel must be positive")

    # The comparison is deliberately weight-scale agnostic.  Use one arbitrary
    # unit of total mass per flyweight and vary only how that unit is distributed
    # between a uniform arm and the tip package.  Any common mass multiplier (or
    # RPM multiplier) merely rescales force and cannot change the normalized
    # shape being compared.
    mixes = np.linspace(0.0, 0.98, mass_mix_count)
    q0_values = np.deg2rad(np.linspace(-27.0, 74.0, 18))
    span_values_deg = np.asarray([2.5, 4.0, 6.5, 10.0, 15.0, 22.0, 31.0, 42.0, 56.0])

    from scipy.interpolate import PchipInterpolator

    geometry_candidates: list[tuple[float, _Candidate, float, float]] = []
    failure_counts: dict[str, int] = {}

    for mix in mixes:
        # unit total mass per flyweight: arm=(1-w), tip=w
        solve_architecture = replace(
            architecture,
            arm_mass_per_flyweight_kg=float(1.0 - mix),
            max_tip_mass_per_flyweight_kg=max(float(mix), 1.0),
        )
        moments = _mass_moments(solve_architecture, float(mix))

        for q0 in q0_values:
            max_span_deg = degrees(Q_MAX_DESIGN - q0) - 0.35
            if max_span_deg <= 1.0:
                continue
            spans = span_values_deg[span_values_deg < max_span_deg]
            if spans.size == 0:
                spans = np.asarray([max(1.25, 0.55 * max_span_deg)])

            u0 = float(_potential(solve_architecture, moments, float(q0)))
            for span_deg in spans:
                q1 = float(q0 + np.deg2rad(float(span_deg)))
                if q1 >= Q_MAX_DESIGN:
                    continue
                du = float(_potential(solve_architecture, moments, q1)) - u0
                if not np.isfinite(du) or du <= 1e-12:
                    continue

                # The normalized target has mean 1 over shift fraction, so an
                # arbitrary force scale A = du/L makes its integrated generalized
                # work exactly equal U(q1)-U(q0) for omega=1.
                force_scale = du / travel
                target = PchipInterpolator(
                    target_x * travel,
                    target_y_normalized * force_scale,
                    extrapolate=False,
                )
                candidate, failure = _evaluate_candidate(
                    solve_architecture,
                    (),  # packaging is screened after the cheap geometry search
                    target,
                    1.0,
                    float(q0),
                    float(mix),
                    max(81, sample_count),
                )
                if candidate is None:
                    code = failure[0] if failure is not None else "GEOMETRY_REJECTED"
                    failure_counts[code] = failure_counts.get(code, 0) + 1
                    continue

                # Compare in the actual normalized-force coordinates the user sees.
                curve_mean = float(
                    np.trapezoid(candidate.recovered_force_N, candidate.shift_m) / travel
                )
                if not np.isfinite(curve_mean) or curve_mean <= 1e-14:
                    continue
                normalized = candidate.recovered_force_N / curve_mean
                source_fraction = candidate.shift_m / travel
                sampled = np.interp(output_xi, source_fraction, normalized)
                delta = sampled - output_target
                normalized_rms = float(np.sqrt(np.mean(delta * delta)))
                geometry_candidates.append(
                    (normalized_rms, candidate, float(mix), float(force_scale))
                )

    # For exact inverse candidates the force error is generally numerical noise;
    # robustness decides which physical realization is worth certifying first.
    geometry_candidates.sort(key=lambda row: (row[0], -row[1].score))

    packaging_rejections = 0
    history_rejections = 0
    certified_considered = 0
    best: tuple[float, _Candidate, float, float] | None = None
    for normalized_rms, candidate, mix, force_scale in geometry_candidates[:180]:
        packaging_ok, _margin, _failure = _check_generated_packaging(
            architecture,
            compiled.zones,
            candidate.shift_m,
            candidate.roller_x,
            candidate.roller_r,
            candidate.contact_x,
            candidate.contact_r,
        )
        if not packaging_ok:
            packaging_rejections += 1
            continue

        path = _piecewise_path_from_candidate(architecture, candidate, node_count=25)
        certification = certify_path_history(
            path,
            trace_sample_count=max(129, compiled.history_trace_sample_count),
            broad_phase_samples_per_segment=25,
        )
        certified_considered += 1
        if not certification.valid:
            history_rejections += 1
            continue

        candidate.history = {
            "valid": True,
            "max_contact_root_count": certification.max_contact_root_count,
            "multiple_root_shift_count": certification.multiple_root_shift_count,
        }
        best = (normalized_rms, candidate, mix, force_scale)
        break

    diagnostics = [
        {"label": "continuous geometry candidates", "value": len(geometry_candidates)},
        {"label": "packaging rejections before certification", "value": packaging_rejections},
        {"label": "history-certified candidates checked", "value": certified_considered},
        {"label": "history rejections", "value": history_rejections},
    ]
    if failure_counts:
        for code, count in sorted(failure_counts.items(), key=lambda item: item[1], reverse=True)[
            :5
        ]:
            diagnostics.append({"label": code, "value": count})

    if best is None:
        return None, diagnostics

    _rms_hint, candidate, mix, force_scale = best
    curve_mean = float(np.trapezoid(candidate.recovered_force_N, candidate.shift_m) / travel)
    normalized = candidate.recovered_force_N / curve_mean
    source_fraction = candidate.shift_m / travel
    sampled = np.interp(output_xi, source_fraction, normalized)
    delta = sampled - output_target
    rms = float(np.sqrt(np.mean(delta * delta)))
    abs_delta = np.abs(delta)
    gap_index = int(np.argmax(abs_delta))

    return {
        "architecture": label,
        "rms_shape_error": rms,
        "max_shape_error": float(abs_delta[gap_index]),
        "max_error_shift_fraction": float(output_xi[gap_index]),
        "mass_mix_fraction": float(mix),
        "tip_to_arm_mass_ratio": float(mix / max(1.0 - mix, 1e-12)),
        "shift_fraction": output_xi.tolist(),
        "normalized_shape": sampled.tolist(),
        "ramp": {
            "shift_m": candidate.shift_m.tolist(),
            "q_deg": np.degrees(candidate.q_rad).tolist(),
            "ramp_tangent_deg": candidate.tangent_deg.tolist(),
            "roller_center": {
                "x_m": candidate.roller_x.tolist(),
                "r_m": candidate.roller_r.tolist(),
            },
            "ramp_surface": {
                "x_m": candidate.contact_x.tolist(),
                "r_m": candidate.contact_r.tolist(),
            },
        },
        # Retain the old field name so the Phase 3.9 frontend/API contract stays
        # compatible.  It now counts continuous geometry realizations searched,
        # not atlas curves.
        "sampled_candidate_count": len(geometry_candidates),
        "continuous_inverse": True,
        "force_scale_arbitrary_units": float(force_scale),
        "q0_deg": degrees(candidate.q0_rad),
        "q1_deg": float(np.degrees(candidate.q_rad[-1])),
    }, diagnostics
