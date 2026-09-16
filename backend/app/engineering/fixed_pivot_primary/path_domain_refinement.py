"""Refined path-domain projections and conditioned solution extraction.

This module builds on the Phase-3 graph kernel without changing its physical
acceptance rules.  It improves three presentation/search layers:

* architecture representatives are selected for geometric diversity rather
  than taking the first history-valid paths encountered;
* capability plots are sampled through the actual Hermite edges, not only at
  graph stations;
* force capability preserves disconnected attainable force intervals and
  conditioned representatives are extracted from the conditioned graph itself
  while carrying one common flyweight-mass set through the full path.
"""

from __future__ import annotations

from math import isfinite, pi

import numpy as np

# Projection caches are process-local and keyed by the cached domain object.
# They keep the interactive Requirements page from re-evaluating every Hermite
# edge when only RPM changes or when React mounts the page in development mode.
_EDGE_GAIN_CACHE: dict[tuple[int, int], list[tuple[int, float, np.ndarray, np.ndarray, np.ndarray]]] = {}
_FULL_FORCE_CACHE: dict[tuple[int, int, float], dict[str, object]] = {}

from .path_domain import (
    CompiledPathDomain,
    ForceRequirement,
    LayerEdge,
    PathSegment,
    _continuous_path_mass_interval,
    _first_set_bit,
    _mass_from_index,
    _normalized_force_gain,
    _path_absolute_force_document,
    _path_document,
    _path_from_state_indices,
    _physical_domain_projection,
    _reference_speed,
    _requirement_mass_mask,
    _station_projection,
    certify_path_history,
)


def refresh_compiled_domain_views(
    compiled: CompiledPathDomain,
    *,
    representative_count: int = 12,
    capability_samples_per_layer: int = 25,
) -> None:
    """Replace biased atlas/projection views while leaving graph physics untouched."""

    state_paths = _candidate_state_paths(
        compiled,
        edge_masks=None,
        max_candidates=max(48, 8 * representative_count),
    )
    existing = {
        tuple(path): document
        for path, document in zip(
            compiled.representative_state_paths,
            compiled.representative_documents,
            strict=True,
        )
    }
    selected_paths: list[tuple[int, ...]] = []
    selected_documents: list[dict[str, object]] = []
    rejected = 0

    for state_path in _diverse_path_order(compiled, state_paths):
        signature = tuple(state_path)
        document = existing.get(signature)
        if document is None:
            ramp_path = _path_from_state_indices(
                compiled.architecture,
                compiled.states,
                list(signature),
                compiled.shift_station_count,
            )
            certification = certify_path_history(
                ramp_path,
                trace_sample_count=compiled.history_trace_sample_count,
            )
            if not certification.valid:
                rejected += 1
                continue
            document = _path_document(
                ramp_path,
                list(signature),
                certification,
                sample_count=max(161, 20 * compiled.shift_station_count + 1),
            )
        selected_paths.append(signature)
        selected_documents.append(document)
        if len(selected_documents) >= representative_count:
            break

    if selected_documents:
        compiled.representative_state_paths = tuple(selected_paths)
        compiled.representative_documents = tuple(selected_documents)
        compiled.document["representative_paths"] = selected_documents
        history = compiled.document.get("history")
        if isinstance(history, dict):
            history["certified_representative_path_count"] = len(selected_documents)
            history["diverse_candidate_path_count"] = len(state_paths)
            history["diverse_history_rejection_count"] = rejected

    compiled.document["capability"] = _continuous_normalized_capability(
        compiled,
        samples_per_layer=capability_samples_per_layer,
    )

    # Requirements opens at 300 g/flyweight (or the architecture maximum when
    # lower). Prime that exact full force-set projection while the architecture
    # domain is already being compiled so entering the next page is immediate.
    _full_force_projection_cached(
        compiled,
        max_tip_mass_per_flyweight_kg=min(0.300, compiled.architecture.max_tip_mass_per_flyweight_kg),
        shaft_speed_rad_s=1.0,
        samples_per_layer=9,
    )
    numerics = compiled.document.get("numerics")
    if isinstance(numerics, dict):
        numerics["capability_samples_per_layer"] = capability_samples_per_layer


def condition_path_domain_refined(
    compiled: CompiledPathDomain,
    requirements: tuple[ForceRequirement, ...],
    *,
    max_tip_mass_per_flyweight_kg: float,
    mass_sample_count: int = 1025,
    representative_solution_count: int = 12,
    reference_shaft_speed_rad_s: float | None = None,
    force_samples_per_layer: int = 9,
) -> dict[str, object]:
    """Condition the graph while preserving force-set topology and solution paths."""

    architecture = compiled.architecture
    if max_tip_mass_per_flyweight_kg < 0.0:
        raise ValueError("maximum tip mass must be non-negative")
    if max_tip_mass_per_flyweight_kg > architecture.max_tip_mass_per_flyweight_kg + 1.0e-12:
        raise ValueError("maximum tip mass cannot exceed the architecture limit")
    if mass_sample_count < 65:
        raise ValueError("mass_sample_count must be at least 65")
    if representative_solution_count < 1:
        raise ValueError("representative_solution_count must be positive")
    if reference_shaft_speed_rad_s is not None and reference_shaft_speed_rad_s <= 0.0:
        raise ValueError("reference shaft speed must be positive")

    display_speed = reference_shaft_speed_rad_s or _reference_speed(requirements)
    travel = architecture.required_travel_m
    for requirement in requirements:
        if requirement.shift_m < -1.0e-12 or requirement.shift_m > travel + 1.0e-12:
            raise ValueError("force requirement shift lies outside the required travel")
        if requirement.force_N < 0.0 or requirement.tolerance_N < 0.0:
            raise ValueError("force requirements and tolerances must be non-negative")
        if requirement.shaft_speed_rad_s <= 0.0:
            raise ValueError("force requirements require a positive shaft speed")

    # No force points means no graph conditioning at all: every viable edge and
    # every mass in [0, max] survives. Returning directly avoids two complete
    # forward/backward passes over a large graph just to rediscover that fact.
    if not requirements:
        return _unrestricted_condition_result(
            compiled,
            max_tip_mass_per_flyweight_kg=max_tip_mass_per_flyweight_kg,
            mass_sample_count=mass_sample_count,
            representative_solution_count=representative_solution_count,
            display_speed=display_speed,
            force_samples_per_layer=force_samples_per_layer,
        )

    station_count = compiled.shift_station_count
    layer_count = station_count - 1
    dx = travel / layer_count
    all_mask = (1 << mass_sample_count) - 1
    mass_step = max_tip_mass_per_flyweight_kg / (mass_sample_count - 1)

    requirements_by_layer: list[list[ForceRequirement]] = [[] for _ in range(layer_count)]
    for requirement in requirements:
        x = min(max(requirement.shift_m, 0.0), travel)
        layer = min(layer_count - 1, int(x / dx))
        requirements_by_layer[layer].append(requirement)

    edge_masks: list[list[int]] = []
    individual_status: dict[str, bool] = {requirement.id: False for requirement in requirements}
    for layer_index, layer_edges in enumerate(compiled.viable_edges):
        masks: list[int] = []
        x0 = layer_index * dx
        for edge in layer_edges:
            template = compiled.templates[edge.template_index]
            segment = PathSegment(
                x0_m=x0,
                x1_m=x0 + dx,
                q0_rad=template.q0_rad,
                q1_rad=template.q1_rad,
                m0_rad_per_m=template.m0_rad_per_m,
                m1_rad_per_m=template.m1_rad_per_m,
            )
            mask = all_mask
            for requirement in requirements_by_layer[layer_index]:
                requirement_mask = _requirement_mass_mask(
                    architecture,
                    segment,
                    requirement,
                    max_tip_mass_per_flyweight_kg,
                    mass_sample_count,
                )
                if requirement_mask:
                    individual_status[requirement.id] = True
                mask &= requirement_mask
            masks.append(mask)
        edge_masks.append(masks)

    forward: list[dict[int, int]] = [dict() for _ in range(station_count)]
    backward: list[dict[int, int]] = [dict() for _ in range(station_count)]
    for state_index in compiled.viable_nodes[0]:
        forward[0][state_index] = all_mask
    for layer_index, layer_edges in enumerate(compiled.viable_edges):
        next_map = forward[layer_index + 1]
        for edge_index, edge in enumerate(layer_edges):
            mask = forward[layer_index].get(edge.start_state, 0) & edge_masks[layer_index][edge_index]
            if mask:
                next_map[edge.end_state] = next_map.get(edge.end_state, 0) | mask

    for state_index in compiled.viable_nodes[-1]:
        backward[-1][state_index] = all_mask
    for layer_index in range(layer_count - 1, -1, -1):
        current_map = backward[layer_index]
        for edge_index, edge in enumerate(compiled.viable_edges[layer_index]):
            mask = backward[layer_index + 1].get(edge.end_state, 0) & edge_masks[layer_index][edge_index]
            if mask:
                current_map[edge.start_state] = current_map.get(edge.start_state, 0) | mask

    node_masks: list[dict[int, int]] = []
    conditioned_nodes: list[set[int]] = []
    conditioned_edge_masks: list[list[int]] = []
    conditioned_edges: list[list[LayerEdge]] = []
    for station in range(station_count):
        row: dict[int, int] = {}
        nodes: set[int] = set()
        for state_index in compiled.viable_nodes[station]:
            mask = forward[station].get(state_index, 0) & backward[station].get(state_index, 0)
            if mask:
                row[state_index] = mask
                nodes.add(state_index)
        node_masks.append(row)
        conditioned_nodes.append(nodes)

    for layer_index, layer_edges in enumerate(compiled.viable_edges):
        masks: list[int] = []
        edges: list[LayerEdge] = []
        for edge_index, edge in enumerate(layer_edges):
            mask = (
                forward[layer_index].get(edge.start_state, 0)
                & edge_masks[layer_index][edge_index]
                & backward[layer_index + 1].get(edge.end_state, 0)
            )
            masks.append(mask)
            if mask:
                edges.append(edge)
        conditioned_edge_masks.append(masks)
        conditioned_edges.append(edges)

    # The blank Requirements view is a particularly common call. With no force
    # points, the conditioned graph is identical to the full graph, so compute
    # the force projection once and reuse the already-compiled physical domain.
    # This also avoids re-certifying a second representative atlas merely to
    # display the untouched starting state.
    full_force_capability = _full_force_projection_cached(
        compiled,
        max_tip_mass_per_flyweight_kg=max_tip_mass_per_flyweight_kg,
        shaft_speed_rad_s=display_speed,
        samples_per_layer=force_samples_per_layer,
    )
    if requirements:
        conditioned_force_capability = _force_interval_projection(
            compiled,
            max_tip_mass_per_flyweight_kg=max_tip_mass_per_flyweight_kg,
            shaft_speed_rad_s=display_speed,
            edge_mass_masks=conditioned_edge_masks,
            mass_sample_count=mass_sample_count,
            samples_per_layer=force_samples_per_layer,
        )
        projection = _physical_domain_projection(
            architecture,
            conditioned_nodes,
            compiled.states,
            station_count,
            q_sample_count=compiled.q_sample_count,
            alpha_sample_count=compiled.alpha_sample_count,
        )
        projection["meaning"] = (
            "Physical projection of complete graph states that remain reachable and "
            "co-reachable while carrying at least one common tip mass satisfying all "
            "current force requirements."
        )
    else:
        conditioned_force_capability = full_force_capability
        projection = compiled.document["domain_projection"]

    jointly_feasible = bool(conditioned_nodes and conditioned_nodes[0])
    if jointly_feasible and requirements:
        representative_solutions = _conditioned_representatives(
            compiled,
            requirements,
            conditioned_edge_masks,
            max_tip_mass_per_flyweight_kg=max_tip_mass_per_flyweight_kg,
            mass_sample_count=mass_sample_count,
            representative_solution_count=representative_solution_count,
            display_speed=display_speed,
        )
    elif jointly_feasible:
        representative_solutions = _unconditioned_representatives(
            compiled,
            max_tip_mass_per_flyweight_kg=max_tip_mass_per_flyweight_kg,
            representative_solution_count=representative_solution_count,
            display_speed=display_speed,
        )
    else:
        representative_solutions = []

    impossible_ids = [identifier for identifier, possible in individual_status.items() if not possible]
    findings: list[dict[str, object]] = []
    if impossible_ids:
        findings.append(
            {
                "severity": "error",
                "code": "INDIVIDUAL_REQUIREMENT_OUTSIDE_CAPABILITY",
                "message": "One or more force points are outside the architecture capability for the allowed mass range.",
                "requirement_ids": impossible_ids,
            }
        )
    elif requirements and not jointly_feasible:
        findings.append(
            {
                "severity": "error",
                "code": "REQUIREMENTS_JOINTLY_INCOMPATIBLE",
                "message": (
                    "Every force point is individually attainable, but no complete ramp "
                    "with one constant tip mass can satisfy all points together."
                ),
            }
        )

    mass_values_seen: list[float] = []
    for row in node_masks:
        for mask in row.values():
            for first, last in _mask_runs(mask):
                mass_values_seen.extend(
                    (
                        _mass_from_index(first, max_tip_mass_per_flyweight_kg, mass_sample_count),
                        _mass_from_index(last, max_tip_mass_per_flyweight_kg, mass_sample_count),
                    )
                )

    return {
        "validity": {
            "valid": jointly_feasible and not impossible_ids,
            "findings": findings,
        },
        "requirements": [
            {
                "id": requirement.id,
                "shift_m": requirement.shift_m,
                "force_N": requirement.force_N,
                "shaft_speed_rad_s": requirement.shaft_speed_rad_s,
                "tolerance_N": requirement.tolerance_N,
                "individually_attainable": individual_status[requirement.id],
            }
            for requirement in requirements
        ],
        "mass": {
            "maximum_tip_mass_per_flyweight_kg": max_tip_mass_per_flyweight_kg,
            "mass_sample_count": mass_sample_count,
            "mass_resolution_kg": mass_step,
            "surviving_mass_min_kg": min(mass_values_seen) if mass_values_seen else None,
            "surviving_mass_max_kg": max(mass_values_seen) if mass_values_seen else None,
        },
        "graph": {
            "viable_layer_edge_counts": [len(row) for row in conditioned_edges],
            "viable_node_counts": [len(row) for row in conditioned_nodes],
            "station_projection": _station_projection(conditioned_nodes, compiled.states, station_count),
        },
        "domain_projection": projection,
        "force_capability": {
            "reference_shaft_speed_rad_s": display_speed,
            "full": full_force_capability,
            "conditioned": conditioned_force_capability,
        },
        "representative_solutions": representative_solutions,
        "summary": {
            "requirement_count": len(requirements),
            "jointly_feasible": jointly_feasible,
            "conditioned_domain_point_count": projection["point_count"],
            "representative_solution_count": len(representative_solutions),
        },
    }


def _continuous_normalized_capability(
    compiled: CompiledPathDomain,
    *,
    samples_per_layer: int,
) -> dict[str, object]:
    architecture = compiled.architecture
    stations: list[dict[str, object]] = []
    for _layer_index, shift_m, arm, tip, active in _edge_gain_samples(compiled, samples_per_layer):
        valid_arm = arm[active]
        valid_tip = tip[active]
        valid_total = valid_arm + architecture.max_tip_mass_per_flyweight_kg * valid_tip

        def extrema(values: np.ndarray) -> tuple[float | None, float | None]:
            if values.size == 0:
                return None, None
            return float(np.min(values)), float(np.max(values))

        arm_min, arm_max = extrema(valid_arm)
        tip_min, tip_max = extrema(valid_tip)
        total_min, total_max = extrema(valid_total)
        stations.append(
            {
                "station": len(stations),
                "shift_m": shift_m,
                "shift_fraction": shift_m / max(architecture.required_travel_m, 1.0e-12),
                "active_state_count": int(np.count_nonzero(active)),
                "arm_force_per_omega2_min": arm_min,
                "arm_force_per_omega2_max": arm_max,
                "tip_force_per_omega2_per_kg_min": tip_min,
                "tip_force_per_omega2_per_kg_max": tip_max,
                "max_tip_total_force_per_omega2_min": total_min,
                "max_tip_total_force_per_omega2_max": total_max,
            }
        )

    return {
        "definition": (
            "Quasi-static centrifugal closing-force gain normalized by shaft-speed squared. "
            "The envelope is evaluated densely through the actual complete-path-viable "
            "Hermite edges, so displayed representative ramps use the same continuous "
            "geometry rather than a nine-station interpolation."
        ),
        "units": {
            "arm_force_per_omega2": "N/(rad/s)^2",
            "tip_force_per_omega2_per_kg": "N/(rad/s)^2/kg",
            "max_tip_total_force_per_omega2": "N/(rad/s)^2",
        },
        "max_tip_mass_per_flyweight_kg": architecture.max_tip_mass_per_flyweight_kg,
        "stations": stations,
    }


def _edge_gain_samples(
    compiled: CompiledPathDomain,
    samples_per_layer: int,
) -> list[tuple[int, float, np.ndarray, np.ndarray, np.ndarray]]:
    """Vectorized arm/tip gains for every viable edge at every displayed shift."""

    key = (id(compiled), int(samples_per_layer))
    cached = _EDGE_GAIN_CACHE.get(key)
    if cached is not None:
        return cached

    architecture = compiled.architecture
    layer_count = compiled.shift_station_count - 1
    dx = architecture.required_travel_m / layer_count
    count = float(architecture.number_of_flyweights)
    pivot_radius = architecture.pivot_radius_m
    length = architecture.arm_length_m
    arm_mass = architecture.arm_mass_per_flyweight_kg
    rows: list[tuple[int, float, np.ndarray, np.ndarray, np.ndarray]] = []

    for layer_index, layer_edges in enumerate(compiled.viable_edges):
        if layer_edges:
            templates = [compiled.templates[edge.template_index] for edge in layer_edges]
            q0 = np.asarray([template.q0_rad for template in templates], dtype=float)
            q1 = np.asarray([template.q1_rad for template in templates], dtype=float)
            m0 = np.asarray([template.m0_rad_per_m for template in templates], dtype=float)
            m1 = np.asarray([template.m1_rad_per_m for template in templates], dtype=float)
            delta = q1 - q0
            M0 = dx * m0
            M1 = dx * m1
            A = 3.0 * delta - 2.0 * M0 - M1
            B = -2.0 * delta + M0 + M1
        else:
            q0 = q1 = m0 = m1 = delta = M0 = M1 = A = B = np.asarray([], dtype=float)

        fractions = np.linspace(0.0, 1.0, max(2, samples_per_layer))
        if layer_index > 0:
            fractions = fractions[1:]
        x0 = layer_index * dx
        for t_raw in fractions:
            t = float(t_raw)
            q = q0 + M0 * t + A * t * t + B * t * t * t
            qt = M0 + 2.0 * A * t + 3.0 * B * t * t
            dq = qt / dx
            sin_q = np.sin(q)
            cos_q = np.cos(q)
            d_j_d_q_arm = count * arm_mass * (
                pivot_radius * length * cos_q
                + (2.0 / 3.0) * length * length * sin_q * cos_q
            )
            d_j_d_q_tip = count * (
                2.0 * length * cos_q * (pivot_radius + length * sin_q)
            )
            arm_gain = 0.5 * d_j_d_q_arm * dq
            tip_gain = 0.5 * d_j_d_q_tip * dq
            active = (dq > 1.0e-8) & np.isfinite(arm_gain) & np.isfinite(tip_gain)
            rows.append((layer_index, x0 + t * dx, arm_gain, tip_gain, active))

    _EDGE_GAIN_CACHE[key] = rows
    return rows


def _full_force_projection_cached(
    compiled: CompiledPathDomain,
    *,
    max_tip_mass_per_flyweight_kg: float,
    shaft_speed_rad_s: float,
    samples_per_layer: int,
) -> dict[str, object]:
    mass_key = round(float(max_tip_mass_per_flyweight_kg), 12)
    key = (id(compiled), int(samples_per_layer), mass_key)
    basis = _FULL_FORCE_CACHE.get(key)
    if basis is None:
        basis = _force_interval_projection(
            compiled,
            max_tip_mass_per_flyweight_kg=max_tip_mass_per_flyweight_kg,
            shaft_speed_rad_s=1.0,
            edge_mass_masks=None,
            mass_sample_count=65,
            samples_per_layer=samples_per_layer,
        )
        _FULL_FORCE_CACHE[key] = basis
    scale = shaft_speed_rad_s * shaft_speed_rad_s
    stations: list[dict[str, object]] = []
    for row in basis["stations"]:
        assert isinstance(row, dict)
        intervals = row["force_intervals_N"]
        assert isinstance(intervals, list)
        stations.append(
            {
                **row,
                "force_min_N": None if row["force_min_N"] is None else float(row["force_min_N"]) * scale,
                "force_max_N": None if row["force_max_N"] is None else float(row["force_max_N"]) * scale,
                "force_intervals_N": [[float(lo) * scale, float(hi) * scale] for lo, hi in intervals],
            }
        )
    return {
        "shaft_speed_rad_s": shaft_speed_rad_s,
        "max_tip_mass_per_flyweight_kg": max_tip_mass_per_flyweight_kg,
        "stations": stations,
    }


def _unrestricted_condition_result(
    compiled: CompiledPathDomain,
    *,
    max_tip_mass_per_flyweight_kg: float,
    mass_sample_count: int,
    representative_solution_count: int,
    display_speed: float,
    force_samples_per_layer: int,
) -> dict[str, object]:
    full_force = _full_force_projection_cached(
        compiled,
        max_tip_mass_per_flyweight_kg=max_tip_mass_per_flyweight_kg,
        shaft_speed_rad_s=display_speed,
        samples_per_layer=force_samples_per_layer,
    )
    projection = compiled.document["domain_projection"]
    representatives = _unconditioned_representatives(
        compiled,
        max_tip_mass_per_flyweight_kg=max_tip_mass_per_flyweight_kg,
        representative_solution_count=representative_solution_count,
        display_speed=display_speed,
    )
    graph = compiled.document["graph"]
    assert isinstance(graph, dict)
    return {
        "validity": {"valid": bool(compiled.viable_nodes and compiled.viable_nodes[0]), "findings": []},
        "requirements": [],
        "mass": {
            "maximum_tip_mass_per_flyweight_kg": max_tip_mass_per_flyweight_kg,
            "mass_sample_count": mass_sample_count,
            "mass_resolution_kg": max_tip_mass_per_flyweight_kg / (mass_sample_count - 1),
            "surviving_mass_min_kg": 0.0,
            "surviving_mass_max_kg": max_tip_mass_per_flyweight_kg,
        },
        "graph": {
            "viable_layer_edge_counts": [len(row) for row in compiled.viable_edges],
            "viable_node_counts": [len(row) for row in compiled.viable_nodes],
            "station_projection": graph["station_projection"],
        },
        "domain_projection": projection,
        "force_capability": {
            "reference_shaft_speed_rad_s": display_speed,
            "full": full_force,
            "conditioned": full_force,
        },
        "representative_solutions": representatives,
        "summary": {
            "requirement_count": 0,
            "jointly_feasible": bool(compiled.viable_nodes and compiled.viable_nodes[0]),
            "conditioned_domain_point_count": projection["point_count"],
            "representative_solution_count": len(representatives),
        },
    }

def _force_interval_projection(
    compiled: CompiledPathDomain,
    *,
    max_tip_mass_per_flyweight_kg: float,
    shaft_speed_rad_s: float,
    edge_mass_masks: list[list[int]] | None,
    mass_sample_count: int,
    samples_per_layer: int,
) -> dict[str, object]:
    omega2 = shaft_speed_rad_s * shaft_speed_rad_s
    samples: list[dict[str, object]] = []
    all_mask = (1 << mass_sample_count) - 1

    for layer_index, shift_m, arm, tip, active in _edge_gain_samples(compiled, samples_per_layer):
        if edge_mass_masks is None:
            valid = active
            low = omega2 * arm[valid]
            high = omega2 * (arm[valid] + max_tip_mass_per_flyweight_kg * tip[valid])
            lows = np.minimum(low, high)
            highs = np.maximum(low, high)
            merged = _merge_numpy_intervals(lows, highs)
            merged_mass = [(0.0, max_tip_mass_per_flyweight_kg)] if lows.size else []
            active_count = int(lows.size)
        else:
            intervals: list[tuple[float, float]] = []
            mass_intervals: list[tuple[float, float]] = []
            active_count = 0
            masks = edge_mass_masks[layer_index]
            for edge_index in np.flatnonzero(active):
                mask = masks[int(edge_index)]
                if not mask:
                    continue
                if mask == all_mask:
                    mass_runs = ((0.0, max_tip_mass_per_flyweight_kg),)
                else:
                    mass_runs = tuple(
                        (
                            _mass_from_index(first, max_tip_mass_per_flyweight_kg, mass_sample_count),
                            _mass_from_index(last, max_tip_mass_per_flyweight_kg, mass_sample_count),
                        )
                        for first, last in _mask_runs(mask)
                    )
                for low_mass, high_mass in mass_runs:
                    a = omega2 * (float(arm[edge_index]) + low_mass * float(tip[edge_index]))
                    b = omega2 * (float(arm[edge_index]) + high_mass * float(tip[edge_index]))
                    intervals.append((min(a, b), max(a, b)))
                    mass_intervals.append((low_mass, high_mass))
                active_count += 1
            merged = _merge_intervals(intervals)
            merged_mass = _merge_intervals(mass_intervals)

        samples.append(
            {
                "station": len(samples),
                "shift_m": shift_m,
                "active_state_count": active_count,
                "force_min_N": merged[0][0] if merged else None,
                "force_max_N": merged[-1][1] if merged else None,
                "force_intervals_N": [[lo, hi] for lo, hi in merged],
                "mass_min_kg": merged_mass[0][0] if merged_mass else None,
                "mass_max_kg": merged_mass[-1][1] if merged_mass else None,
            }
        )

    return {
        "shaft_speed_rad_s": shaft_speed_rad_s,
        "max_tip_mass_per_flyweight_kg": max_tip_mass_per_flyweight_kg,
        "stations": samples,
    }


def _merge_numpy_intervals(lows: np.ndarray, highs: np.ndarray) -> list[tuple[float, float]]:
    if lows.size == 0:
        return []
    order = np.argsort(lows, kind="stable")
    ordered_lows = lows[order]
    ordered_highs = highs[order]
    merged: list[list[float]] = [[float(ordered_lows[0]), float(ordered_highs[0])]]
    for low_raw, high_raw in zip(ordered_lows[1:], ordered_highs[1:], strict=True):
        low = float(low_raw)
        high = float(high_raw)
        current = merged[-1]
        if low <= current[1] + 1.0e-9:
            if high > current[1]:
                current[1] = high
        else:
            merged.append([low, high])
    return [(low, high) for low, high in merged]

def _unconditioned_representatives(
    compiled: CompiledPathDomain,
    *,
    max_tip_mass_per_flyweight_kg: float,
    representative_solution_count: int,
    display_speed: float,
) -> list[dict[str, object]]:
    """Reuse the architecture atlas for the untouched Requirements view."""

    solutions: list[dict[str, object]] = []
    for document in compiled.representative_documents[:representative_solution_count]:
        example_mass = 0.5 * max_tip_mass_per_flyweight_kg
        solutions.append(
            {
                **document,
                "solution": {
                    "tip_mass_min_kg": 0.0,
                    "tip_mass_max_kg": max_tip_mass_per_flyweight_kg,
                    "example_tip_mass_kg": example_mass,
                    "force_N": _path_absolute_force_document(
                        document,
                        example_mass,
                        (),
                        display_speed,
                    ),
                },
            }
        )
    return solutions

def _conditioned_representatives(
    compiled: CompiledPathDomain,
    requirements: tuple[ForceRequirement, ...],
    edge_masks: list[list[int]],
    *,
    max_tip_mass_per_flyweight_kg: float,
    mass_sample_count: int,
    representative_solution_count: int,
    display_speed: float,
) -> list[dict[str, object]]:
    state_paths = _candidate_state_paths(
        compiled,
        edge_masks=edge_masks,
        max_candidates=max(72, 10 * representative_solution_count),
    )
    solutions: list[tuple[tuple[int, ...], dict[str, object]]] = []
    for state_path in _diverse_path_order(compiled, state_paths):
        ramp_path = _path_from_state_indices(
            compiled.architecture,
            compiled.states,
            list(state_path),
            compiled.shift_station_count,
        )
        certification = certify_path_history(
            ramp_path,
            trace_sample_count=compiled.history_trace_sample_count,
        )
        if not certification.valid:
            continue
        interval = _continuous_path_mass_interval(
            ramp_path,
            requirements,
            max_tip_mass_per_flyweight_kg,
        )
        if interval is None:
            continue
        document = _path_document(
            ramp_path,
            list(state_path),
            certification,
            sample_count=max(161, 20 * compiled.shift_station_count + 1),
        )
        mass_min, mass_max = interval
        example_mass = 0.5 * (mass_min + mass_max)
        document = {
            **document,
            "solution": {
                "tip_mass_min_kg": mass_min,
                "tip_mass_max_kg": mass_max,
                "example_tip_mass_kg": example_mass,
                "force_N": _path_absolute_force_document(
                    document,
                    example_mass,
                    requirements,
                    display_speed,
                ),
            },
        }
        solutions.append((tuple(state_path), document))
        if len(solutions) >= representative_solution_count:
            break
    return [document for _, document in solutions]


def _candidate_state_paths(
    compiled: CompiledPathDomain,
    *,
    edge_masks: list[list[int]] | None,
    max_candidates: int,
) -> list[tuple[int, ...]]:
    all_mask = None
    outgoing: list[dict[int, list[tuple[LayerEdge, int | None]]]] = []
    for layer_index, edges in enumerate(compiled.viable_edges):
        mapping: dict[int, list[tuple[LayerEdge, int | None]]] = {}
        for edge_index, edge in enumerate(edges):
            mask = None if edge_masks is None else edge_masks[layer_index][edge_index]
            if mask == 0:
                continue
            mapping.setdefault(edge.start_state, []).append((edge, mask))
        for choices in mapping.values():
            choices.sort(
                key=lambda item: (
                    compiled.states[item[0].end_state].q_rad,
                    compiled.states[item[0].end_state].alpha_rad,
                )
            )
        outgoing.append(mapping)

    starts = sorted(
        (index for index in compiled.viable_nodes[0] if index in outgoing[0]),
        key=lambda index: (compiled.states[index].q_rad, compiled.states[index].alpha_rad),
    )
    if not starts:
        return []
    if len(starts) > 24:
        picks = np.linspace(0, len(starts) - 1, 24).round().astype(int)
        starts = [starts[int(index)] for index in picks]

    patterns = (
        lambda layer, count: 0.0,
        lambda layer, count: 0.2,
        lambda layer, count: 0.4,
        lambda layer, count: 0.6,
        lambda layer, count: 0.8,
        lambda layer, count: 1.0,
        lambda layer, count: layer / max(1, count - 1),
        lambda layer, count: 1.0 - layer / max(1, count - 1),
        lambda layer, count: 0.2 if layer % 2 == 0 else 0.8,
        lambda layer, count: 0.8 if layer % 2 == 0 else 0.2,
    )

    candidates: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()
    for start in starts:
        for pattern in patterns:
            path = [start]
            current = start
            carried_mask: int | None = all_mask
            ok = True
            for layer in range(compiled.shift_station_count - 1):
                choices = outgoing[layer].get(current, [])
                compatible: list[tuple[LayerEdge, int | None, int | None]] = []
                for edge, mask in choices:
                    next_mask = None if mask is None else (mask if carried_mask is None else carried_mask & mask)
                    if next_mask == 0:
                        continue
                    compatible.append((edge, mask, next_mask))
                if not compatible:
                    ok = False
                    break
                fraction = float(pattern(layer, compiled.shift_station_count - 1))
                choice_index = int(round(fraction * (len(compatible) - 1)))
                edge, _mask, carried_mask = compatible[choice_index]
                current = edge.end_state
                path.append(current)
            signature = tuple(path)
            if ok and signature not in seen:
                seen.add(signature)
                candidates.append(signature)
    if len(candidates) <= max_candidates:
        return candidates
    return _diverse_path_order(compiled, candidates)[:max_candidates]


def _diverse_path_order(
    compiled: CompiledPathDomain,
    paths: list[tuple[int, ...]],
) -> list[tuple[int, ...]]:
    if len(paths) <= 2:
        return paths
    features = np.asarray([_path_feature(compiled, path) for path in paths], dtype=float)
    scale = np.ptp(features, axis=0)
    scale[scale < 1.0e-12] = 1.0
    features = (features - np.min(features, axis=0)) / scale

    means = np.mean(features, axis=1)
    seeds = [int(np.argmin(means)), int(np.argmax(means))]
    selected: list[int] = []
    for index in seeds:
        if index not in selected:
            selected.append(index)
    while len(selected) < len(paths):
        best_index = None
        best_distance = -1.0
        for index in range(len(paths)):
            if index in selected:
                continue
            distance = min(float(np.linalg.norm(features[index] - features[other])) for other in selected)
            if distance > best_distance:
                best_distance = distance
                best_index = index
        if best_index is None:
            break
        selected.append(best_index)
    return [paths[index] for index in selected]


def _path_feature(compiled: CompiledPathDomain, path: tuple[int, ...]) -> list[float]:
    q_scale = pi
    alpha_scale = 0.5 * pi
    feature: list[float] = []
    for index in path:
        state = compiled.states[index]
        feature.extend((state.q_rad / q_scale, state.alpha_rad / alpha_scale))
    return feature


def _mask_runs(mask: int) -> list[tuple[int, int]]:
    """Return contiguous set-bit runs using bigint operations, not bit-by-bit scans."""

    runs: list[tuple[int, int]] = []
    base = 0
    value = mask
    while value:
        first = (value & -value).bit_length() - 1
        value >>= first
        base += first
        # value now starts with one or more 1 bits. For k trailing ones,
        # value ^ (value + 1) contains k+1 low set bits.
        run_length = (value ^ (value + 1)).bit_length() - 1
        runs.append((base, base + run_length - 1))
        value >>= run_length
        base += run_length
    return runs


def _merge_intervals(
    intervals: list[tuple[float, float]],
    *,
    tolerance: float = 1.0e-9,
) -> list[tuple[float, float]]:
    if not intervals:
        return []
    ordered = sorted((min(a, b), max(a, b)) for a, b in intervals)
    merged: list[list[float]] = [[ordered[0][0], ordered[0][1]]]
    for low, high in ordered[1:]:
        current = merged[-1]
        if low <= current[1] + tolerance:
            current[1] = max(current[1], high)
        else:
            merged.append([low, high])
    return [(low, high) for low, high in merged]
