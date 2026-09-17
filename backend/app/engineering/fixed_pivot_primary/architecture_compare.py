"""Mass-scale-agnostic comparison of two fixed-pivot primary architectures.

The comparison intentionally asks a different question from force-to-ramp
inverse design.  Here the object of interest is the family of *complete* ramp
behaviours admitted by each architecture.  Each history-certified path has an
arm-specific normalized force gain A(x) and a tip-mass gain B(x).  Dividing the
arm contribution by arm mass and mixing it with B through a dimensionless mass
fraction produces a specific-force family that is independent of overall
flyweight mass scale and shaft speed.

The curve shape is normalized by its shift-average magnitude and projected onto
the first three shifted Legendre modes.  The resulting sampled footprint is an
exploratory complete-path capability map, not a formal proof of the entire
continuous feasible set.  Witness ramps are returned for the most separated
sampled behaviours in both directions.
"""

from __future__ import annotations

from math import sqrt

import numpy as np
from scipy.spatial import ConvexHull

from .path_domain import (
    CompiledPathDomain,
    _path_document,
    _path_from_state_indices,
    certify_path_history,
)
from .path_domain_refinement import _candidate_state_paths, _diverse_path_order

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
            rows.append({
                "architecture": label,
                "path_index": path_index,
                "state_indices": list(signature),
                "mass_mix_fraction": float(mix),
                "tip_to_arm_mass_ratio": float(mix / max(1.0 - mix, 1e-12)),
                "c1": c1,
                "c2": c2,
                "c3": c3,
                "mean_specific_gain": mean_gain,
                "shift_fraction": ((shift - shift[0]) / max(shift[-1] - shift[0], 1e-12)).tolist(),
                "specific_gain": specific.tolist(),
                "normalized_shape": normalized.tolist(),
                "ramp": {
                    "shift_m": document.get("shift_m", []),
                    "q_deg": document.get("q_deg", []),
                    "ramp_tangent_deg": document.get("ramp_tangent_deg", []),
                    "roller_center": document.get("roller_center", {}),
                    "ramp_surface": document.get("ramp_surface", {}),
                },
            })
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


def _leverage_envelope(points: list[dict[str, object]], sample_count: int = 81) -> dict[str, object]:
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
    source_curves = np.vstack([
        np.interp(xi, np.asarray(row["shift_fraction"], dtype=float), np.asarray(row["normalized_shape"], dtype=float))
        for row in source
    ])
    target_curves = np.vstack([
        np.interp(xi, np.asarray(row["shift_fraction"], dtype=float), np.asarray(row["normalized_shape"], dtype=float))
        for row in target
    ])

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
        witnesses.append({
            "source_architecture": source_label,
            "nearest_architecture": target_label,
            "shape_distance": float(distances[index]),
            "max_pointwise_shape_gap": float(pointwise[gap_index]),
            "gap_shift_fraction": float(xi[gap_index]),
            "source": row,
            "nearest": nearest,
        })
        used_paths.add(path_index)
        if len(witnesses) >= 5:
            break

    return witnesses, {
        "median": float(np.median(distances)),
        "max": float(np.max(distances)),
    }

