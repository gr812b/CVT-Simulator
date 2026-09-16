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

from math import degrees, isfinite, pi

import numpy as np
from scipy.interpolate import PchipInterpolator

# Projection caches are process-local and keyed by the cached domain object.
# They keep the interactive Requirements page from re-evaluating every Hermite
# edge when only RPM changes or when React mounts the page in development mode.
_EDGE_GAIN_CACHE: dict[tuple[int, int], list[tuple[int, float, np.ndarray, np.ndarray, np.ndarray]]] = {}
_FULL_FORCE_CACHE: dict[tuple[int, int, float], dict[str, object]] = {}
_REQUIREMENT_GAIN_CACHE: dict[tuple[int, int, float], tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
_SOLUTION_CACHE: dict[tuple[object, ...], list[dict[str, object]]] = {}

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
    _path_capability_document,
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

    numerics = compiled.document.get("numerics")
    if isinstance(numerics, dict):
        if (
            numerics.get("refined_views_representative_count") == representative_count
            and numerics.get("capability_samples_per_layer") == capability_samples_per_layer
        ):
            return

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

    # Reuse history-certified documents already attached to this graph before
    # certifying any fresh candidate. This is especially valuable after a
    # packaging edit, where many base-architecture ramps survive unchanged.
    for signature in _diverse_path_order(compiled, list(existing)):
        document = existing[signature]
        selected_paths.append(signature)
        selected_documents.append(document)
        if len(selected_documents) >= representative_count:
            break

    for state_path in _diverse_path_order(compiled, state_paths):
        if len(selected_documents) >= representative_count:
            break
        signature = tuple(state_path)
        if signature in selected_paths:
            continue
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
        numerics["refined_views_representative_count"] = representative_count


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
    """Condition hard locks and search soft profile guides over complete paths.

    Requirements whose id begins with ``guide-`` are profile handles: they shape
    the desired force curve but do not remove physically valid graph states.
    Every other requirement remains a hard force lock for backwards
    compatibility.  This distinction lets the UI express desired behaviour
    without turning every sketch point into a brittle equality constraint.
    """

    architecture = compiled.architecture
    if max_tip_mass_per_flyweight_kg < 0.0:
        raise ValueError("maximum tip mass must be non-negative")
    if max_tip_mass_per_flyweight_kg > architecture.max_tip_mass_per_flyweight_kg + 1.0e-12:
        raise ValueError("maximum tip mass cannot exceed the architecture limit")
    if mass_sample_count < 65:
        raise ValueError("mass_sample_count must be at least 65")
    if representative_solution_count < 0:
        raise ValueError("representative_solution_count must be non-negative")
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

    guide_requirements = tuple(requirement for requirement in requirements if _is_profile_guide(requirement))
    hard_requirements = tuple(requirement for requirement in requirements if not _is_profile_guide(requirement))

    if not requirements:
        result = _unrestricted_condition_result(
            compiled,
            max_tip_mass_per_flyweight_kg=max_tip_mass_per_flyweight_kg,
            mass_sample_count=mass_sample_count,
            representative_solution_count=representative_solution_count,
            display_speed=display_speed,
            force_samples_per_layer=force_samples_per_layer,
        )
        summary = result.get("summary")
        if isinstance(summary, dict):
            summary.update({
                "profile_guide_count": 0,
                "hard_lock_count": 0,
                "best_profile_rms_error_N": None,
                "best_profile_max_error_N": None,
            })
        return result

    station_count = compiled.shift_station_count
    layer_count = station_count - 1
    dx = travel / layer_count
    all_mask = (1 << mass_sample_count) - 1
    mass_step = max_tip_mass_per_flyweight_kg / (mass_sample_count - 1)

    # Individual attainability is useful feedback for both guide and hard points,
    # but only hard points participate in the graph mask.
    individual_status: dict[str, bool] = {}
    for requirement in requirements:
        x = min(max(requirement.shift_m, 0.0), travel)
        layer = min(layer_count - 1, int(x / dx))
        masks = _requirement_mass_masks_for_layer(
            compiled,
            layer,
            requirement,
            max_tip_mass_per_flyweight_kg,
            mass_sample_count,
        )
        individual_status[requirement.id] = any(masks)

    requirements_by_layer: list[list[ForceRequirement]] = [[] for _ in range(layer_count)]
    for requirement in hard_requirements:
        x = min(max(requirement.shift_m, 0.0), travel)
        layer = min(layer_count - 1, int(x / dx))
        requirements_by_layer[layer].append(requirement)

    edge_masks: list[list[int]] = []
    for layer_index, layer_edges in enumerate(compiled.viable_edges):
        masks = [all_mask] * len(layer_edges)
        for requirement in requirements_by_layer[layer_index]:
            requirement_masks = _requirement_mass_masks_for_layer(
                compiled,
                layer_index,
                requirement,
                max_tip_mass_per_flyweight_kg,
                mass_sample_count,
            )
            masks = [left & right for left, right in zip(masks, requirement_masks, strict=True)]
        edge_masks.append(masks)

    if hard_requirements:
        forward: list[dict[int, int]] = [dict() for _ in range(station_count)]
        backward: list[dict[int, int]] = [dict() for _ in range(station_count)]
        constrained_layers = [index for index, row in enumerate(requirements_by_layer) if row]
        first_constrained_layer = min(constrained_layers)
        last_constrained_layer = max(constrained_layers)

        for station in range(first_constrained_layer + 1):
            forward[station] = {state_index: all_mask for state_index in compiled.viable_nodes[station]}
        for layer_index in range(first_constrained_layer, layer_count):
            next_map = forward[layer_index + 1]
            for edge_index, edge in enumerate(compiled.viable_edges[layer_index]):
                mask = forward[layer_index].get(edge.start_state, 0) & edge_masks[layer_index][edge_index]
                if mask:
                    next_map[edge.end_state] = next_map.get(edge.end_state, 0) | mask

        for station in range(last_constrained_layer + 1, station_count):
            backward[station] = {state_index: all_mask for state_index in compiled.viable_nodes[station]}
        for layer_index in range(last_constrained_layer, -1, -1):
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
    else:
        node_masks = [
            {state_index: all_mask for state_index in compiled.viable_nodes[station]}
            for station in range(station_count)
        ]
        conditioned_nodes = [set(row) for row in compiled.viable_nodes]
        conditioned_edge_masks = [[all_mask] * len(row) for row in compiled.viable_edges]
        conditioned_edges = [list(row) for row in compiled.viable_edges]

    jointly_feasible = bool(conditioned_nodes and conditioned_nodes[0])
    full_force_capability = _full_force_projection_cached(
        compiled,
        max_tip_mass_per_flyweight_kg=max_tip_mass_per_flyweight_kg,
        shaft_speed_rad_s=display_speed,
        samples_per_layer=force_samples_per_layer,
    )

    if hard_requirements:
        if representative_solution_count == 0:
            conditioned_force_capability = _node_force_interval_projection(
                compiled,
                node_masks=node_masks,
                max_tip_mass_per_flyweight_kg=max_tip_mass_per_flyweight_kg,
                shaft_speed_rad_s=display_speed,
                mass_sample_count=mass_sample_count,
            )
        else:
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
            "Physical projection after hard force locks. Soft profile guides rank complete "
            "paths but do not remove physically valid graph states."
        )
    else:
        conditioned_force_capability = full_force_capability
        projection = compiled.document["domain_projection"]

    preview_only = representative_solution_count == 0 and bool(guide_requirements)
    if not jointly_feasible:
        representative_solutions: list[dict[str, object]] = []
    elif guide_requirements:
        representative_solutions = _profile_ranked_representatives(
            compiled,
            guide_requirements=guide_requirements,
            hard_requirements=hard_requirements,
            edge_masks=conditioned_edge_masks,
            max_tip_mass_per_flyweight_kg=max_tip_mass_per_flyweight_kg,
            mass_sample_count=mass_sample_count,
            representative_solution_count=(6 if representative_solution_count == 0 else representative_solution_count),
            display_speed=display_speed,
            certify_history=(representative_solution_count > 0),
        )
    elif representative_solution_count == 0 and hard_requirements:
        representative_solutions = _conditioned_preview_representatives(
            compiled,
            hard_requirements,
            conditioned_edge_masks,
            max_tip_mass_per_flyweight_kg=max_tip_mass_per_flyweight_kg,
            mass_sample_count=mass_sample_count,
            preview_count=6,
            display_speed=display_speed,
        )
        preview_only = True
    elif representative_solution_count > 0 and hard_requirements:
        representative_solutions = _conditioned_representatives(
            compiled,
            hard_requirements,
            conditioned_edge_masks,
            max_tip_mass_per_flyweight_kg=max_tip_mass_per_flyweight_kg,
            mass_sample_count=mass_sample_count,
            representative_solution_count=representative_solution_count,
            display_speed=display_speed,
        )
    else:
        representative_solutions = _unconditioned_representatives(
            compiled,
            max_tip_mass_per_flyweight_kg=max_tip_mass_per_flyweight_kg,
            representative_solution_count=representative_solution_count,
            display_speed=display_speed,
        )

    hard_impossible_ids = [
        requirement.id for requirement in hard_requirements if not individual_status.get(requirement.id, False)
    ]
    guide_outside_ids = [
        requirement.id for requirement in guide_requirements if not individual_status.get(requirement.id, False)
    ]
    findings: list[dict[str, object]] = []
    if hard_impossible_ids:
        findings.append({
            "severity": "error",
            "code": "HARD_LOCK_OUTSIDE_CAPABILITY",
            "message": "One or more hard force locks lie outside the architecture capability.",
            "requirement_ids": hard_impossible_ids,
        })
    elif hard_requirements and not jointly_feasible:
        findings.append({
            "severity": "error",
            "code": "HARD_LOCKS_JOINTLY_INCOMPATIBLE",
            "message": "The hard force locks are individually attainable but cannot be satisfied by one complete ramp and one constant tip mass.",
        })
    if guide_outside_ids:
        findings.append({
            "severity": "warning",
            "code": "PROFILE_GUIDE_OUTSIDE_CAPABILITY",
            "message": "One or more profile handles are outside the architecture capability; best-fit solutions will approach them as closely as possible.",
            "requirement_ids": guide_outside_ids,
        })

    mass_values_seen: list[float] = []
    for row in node_masks:
        for mask in row.values():
            for first, last in _mask_runs(mask):
                mass_values_seen.extend((
                    _mass_from_index(first, max_tip_mass_per_flyweight_kg, mass_sample_count),
                    _mass_from_index(last, max_tip_mass_per_flyweight_kg, mass_sample_count),
                ))

    best_fit = None
    if representative_solutions:
        solution = representative_solutions[0].get("solution")
        if isinstance(solution, dict):
            fit = solution.get("profile_fit")
            if isinstance(fit, dict):
                best_fit = fit

    return {
        "validity": {
            "valid": jointly_feasible and not hard_impossible_ids,
            "findings": findings,
        },
        "requirements": [
            {
                "id": requirement.id,
                "shift_m": requirement.shift_m,
                "force_N": requirement.force_N,
                "shaft_speed_rad_s": requirement.shaft_speed_rad_s,
                "tolerance_N": requirement.tolerance_N,
                "mode": "guide" if _is_profile_guide(requirement) else "hard",
                "individually_attainable": individual_status.get(requirement.id, False),
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
            "profile_guide_count": len(guide_requirements),
            "hard_lock_count": len(hard_requirements),
            "jointly_feasible": jointly_feasible,
            "conditioned_domain_point_count": projection["point_count"],
            "representative_solution_count": len(representative_solutions),
            "representative_solutions_preview_only": preview_only,
            "best_profile_rms_error_N": None if best_fit is None else best_fit.get("rms_error_N"),
            "best_profile_max_error_N": None if best_fit is None else best_fit.get("max_abs_error_N"),
        },
    }


def _is_profile_guide(requirement: ForceRequirement) -> bool:
    return requirement.id.startswith("guide-")


def _profile_points(
    guides: tuple[ForceRequirement, ...],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return unique sorted guide points, averaging accidental duplicate shifts."""
    grouped: dict[float, list[ForceRequirement]] = {}
    for requirement in guides:
        grouped.setdefault(round(float(requirement.shift_m), 12), []).append(requirement)
    xs: list[float] = []
    ys: list[float] = []
    tolerances: list[float] = []
    for key in sorted(grouped):
        row = grouped[key]
        xs.append(float(np.mean([item.shift_m for item in row])))
        ys.append(float(np.mean([item.force_N for item in row])))
        tolerances.append(float(np.mean([max(1.0, item.tolerance_N) for item in row])))
    return np.asarray(xs), np.asarray(ys), np.asarray(tolerances)


def _profile_target_samples(
    guides: tuple[ForceRequirement, ...],
    *,
    count: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    xs, ys, tolerances = _profile_points(guides)
    if len(xs) == 0:
        return xs, ys, tolerances
    if len(xs) == 1:
        return xs.copy(), ys.copy(), tolerances.copy()
    sample_x = np.linspace(float(xs[0]), float(xs[-1]), max(3, count))
    target = np.asarray(PchipInterpolator(xs, ys, extrapolate=False)(sample_x), dtype=float)
    corridor = np.asarray(PchipInterpolator(xs, tolerances, extrapolate=False)(sample_x), dtype=float)
    return sample_x, target, np.maximum(1.0, corridor)


def _profile_edge_quadratics(
    compiled: CompiledPathDomain,
    guides: tuple[ForceRequirement, ...],
    display_speed: float,
    *,
    samples_per_layer: int = 5,
) -> list[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Edge error = A*m^2 + B*m + C against the full target profile."""
    profile_x, profile_y, _corridor = _profile_points(guides)
    if len(profile_x) == 0:
        return [
            (np.zeros(len(row)), np.zeros(len(row)), np.zeros(len(row)))
            for row in compiled.viable_edges
        ]
    interpolator = PchipInterpolator(profile_x, profile_y, extrapolate=False) if len(profile_x) >= 2 else None
    omega2 = display_speed * display_speed
    layer_count = compiled.shift_station_count - 1
    dx = compiled.architecture.required_travel_m / layer_count
    result: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []

    for layer_index, edges in enumerate(compiled.viable_edges):
        n = len(edges)
        A = np.zeros(n, dtype=float)
        B = np.zeros(n, dtype=float)
        C = np.zeros(n, dtype=float)
        if n == 0:
            result.append((A, B, C))
            continue
        x0 = layer_index * dx
        x1 = x0 + dx
        if len(profile_x) == 1:
            samples = np.asarray([profile_x[0]]) if x0 - 1e-12 <= profile_x[0] <= x1 + 1e-12 else np.asarray([])
            targets = np.asarray([profile_y[0]]) if samples.size else np.asarray([])
        else:
            left = max(x0, float(profile_x[0]))
            right = min(x1, float(profile_x[-1]))
            if right < left - 1e-12:
                samples = np.asarray([])
                targets = np.asarray([])
            else:
                samples = np.linspace(left, right, max(2, samples_per_layer))
                targets = np.asarray(interpolator(samples), dtype=float)
        for shift_m, target in zip(samples, targets, strict=True):
            arm_gain, tip_gain, active = _edge_gains_at_shift(compiled, layer_index, float(shift_m))
            base = omega2 * arm_gain
            slope = omega2 * tip_gain
            err0 = base - float(target)
            A += np.where(active, slope * slope, 0.0)
            B += np.where(active, 2.0 * err0 * slope, 0.0)
            C += np.where(active, err0 * err0, 0.0)
        result.append((A, B, C))
    return result


def _profile_candidate_paths(
    compiled: CompiledPathDomain,
    guides: tuple[ForceRequirement, ...],
    edge_masks: list[list[int]],
    *,
    max_mass_kg: float,
    mass_sample_count: int,
    display_speed: float,
    probe_count: int,
) -> list[tuple[int, ...]]:
    """Globally minimize target-profile error on the layered DAG for sampled masses."""
    quadratics = _profile_edge_quadratics(compiled, guides, display_speed)
    if max_mass_kg <= 1.0e-15:
        mass_probes = np.asarray([0.0])
    else:
        probe_indices = {
            int(round(value))
            for value in np.linspace(0, mass_sample_count - 1, max(3, probe_count))
        }
        # Hard locks can leave a very narrow shared mass window. Include the
        # endpoints and midpoint of every globally surviving mass run so the
        # target-guided search cannot miss a valid design merely because a
        # uniform probe grid stepped over that window.
        global_mask = 0
        if edge_masks:
            for mask in edge_masks[0]:
                global_mask |= mask
        if global_mask:
            for first, last in _mask_runs(global_mask):
                probe_indices.update((first, (first + last) // 2, last))
        mass_probes = np.asarray([
            max_mass_kg * index / (mass_sample_count - 1)
            for index in sorted(probe_indices)
        ])
    candidates: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()

    for mass in mass_probes:
        if max_mass_kg <= 1.0e-15:
            bit = 1
        else:
            mass_index = int(round(float(mass) / max_mass_kg * (mass_sample_count - 1)))
            mass_index = max(0, min(mass_sample_count - 1, mass_index))
            bit = 1 << mass_index
        costs = {state_index: 0.0 for state_index in compiled.viable_nodes[0]}
        predecessors: list[dict[int, int]] = []
        for layer_index, edges in enumerate(compiled.viable_edges):
            next_costs: dict[int, float] = {}
            predecessor: dict[int, int] = {}
            A, B, C = quadratics[layer_index]
            local = A * mass * mass + B * mass + C
            for edge_index, edge in enumerate(edges):
                if edge_masks[layer_index][edge_index] & bit == 0:
                    continue
                start_cost = costs.get(edge.start_state)
                if start_cost is None:
                    continue
                total = start_cost + float(local[edge_index])
                previous = next_costs.get(edge.end_state)
                if previous is None or total < previous:
                    next_costs[edge.end_state] = total
                    predecessor[edge.end_state] = edge.start_state
            predecessors.append(predecessor)
            costs = next_costs
            if not costs:
                break
        if len(predecessors) != compiled.shift_station_count - 1 or not costs:
            continue
        end_state = min(costs, key=costs.get)
        path = [end_state]
        current = end_state
        ok = True
        for layer_index in range(compiled.shift_station_count - 2, -1, -1):
            previous = predecessors[layer_index].get(current)
            if previous is None:
                ok = False
                break
            path.append(previous)
            current = previous
        if not ok:
            continue
        signature = tuple(reversed(path))
        if signature not in seen:
            seen.add(signature)
            candidates.append(signature)
    return candidates


def _profile_fit_for_path(
    compiled: CompiledPathDomain,
    state_path: tuple[int, ...],
    guides: tuple[ForceRequirement, ...],
    hard_requirements: tuple[ForceRequirement, ...],
    *,
    max_mass_kg: float,
    display_speed: float,
) -> tuple[float, float, float, tuple[float, float], np.ndarray, np.ndarray] | None:
    ramp_path = _path_from_state_indices(
        compiled.architecture,
        compiled.states,
        list(state_path),
        compiled.shift_station_count,
    )
    interval = _continuous_path_mass_interval(ramp_path, hard_requirements, max_mass_kg)
    if interval is None:
        return None
    mass_low, mass_high = interval
    sample_x, target, _corridor = _profile_target_samples(guides, count=129)
    if len(sample_x) == 0:
        mass = 0.5 * (mass_low + mass_high)
        return 0.0, 0.0, mass, interval, sample_x, target

    base: list[float] = []
    slope: list[float] = []
    omega2 = display_speed * display_speed
    for x in sample_x:
        row = ramp_path.evaluate(float(x))
        arm_gain, tip_gain, _ = _normalized_force_gain(
            compiled.architecture,
            row["q_rad"],
            row["dq_dx_rad_per_m"],
        )
        base.append(omega2 * arm_gain)
        slope.append(omega2 * tip_gain)
    base_arr = np.asarray(base)
    slope_arr = np.asarray(slope)
    denominator = float(np.dot(slope_arr, slope_arr))
    if denominator > 1.0e-18:
        mass = float(np.dot(slope_arr, target - base_arr) / denominator)
    else:
        mass = 0.5 * (mass_low + mass_high)
    mass = min(max(mass, mass_low), mass_high)
    force = base_arr + mass * slope_arr
    error = force - target
    rms = float(np.sqrt(np.mean(error * error)))
    maximum = float(np.max(np.abs(error)))
    return rms, maximum, mass, interval, sample_x, target


def _profile_ranked_representatives(
    compiled: CompiledPathDomain,
    *,
    guide_requirements: tuple[ForceRequirement, ...],
    hard_requirements: tuple[ForceRequirement, ...],
    edge_masks: list[list[int]],
    max_tip_mass_per_flyweight_kg: float,
    mass_sample_count: int,
    representative_solution_count: int,
    display_speed: float,
    certify_history: bool,
) -> list[dict[str, object]]:
    if representative_solution_count <= 0:
        return []

    guide_signature = tuple(
        (round(item.shift_m, 12), round(item.force_N, 7), round(item.tolerance_N, 7))
        for item in guide_requirements
    )
    hard_signature = tuple(
        (round(item.shift_m, 12), round(item.force_N, 7), round(item.tolerance_N, 7))
        for item in hard_requirements
    )
    cache_key = (
        "profile",
        id(compiled),
        guide_signature,
        hard_signature,
        round(max_tip_mass_per_flyweight_kg, 12),
        int(mass_sample_count),
        int(representative_solution_count),
        round(display_speed, 7),
        bool(certify_history),
    )
    cached = _SOLUTION_CACHE.get(cache_key)
    if cached is not None:
        return cached

    target_candidates = _profile_candidate_paths(
        compiled,
        guide_requirements,
        edge_masks,
        max_mass_kg=max_tip_mass_per_flyweight_kg,
        mass_sample_count=mass_sample_count,
        display_speed=display_speed,
        probe_count=(11 if not certify_history else 31),
    )
    # Add a bounded geometry-diverse pool so the gallery can expose alternative
    # near-optimal families, but rank every path by full-profile error afterwards.
    fallback = _candidate_state_paths(
        compiled,
        edge_masks=edge_masks,
        max_candidates=(36 if not certify_history else 96),
    )
    candidate_paths: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()
    for path in [*target_candidates, *compiled.representative_state_paths, *fallback]:
        signature = tuple(path)
        if signature not in seen:
            seen.add(signature)
            candidate_paths.append(signature)

    scored: list[tuple[float, float, float, tuple[float, float], tuple[int, ...], np.ndarray, np.ndarray]] = []
    for path in candidate_paths:
        fit = _profile_fit_for_path(
            compiled,
            path,
            guide_requirements,
            hard_requirements,
            max_mass_kg=max_tip_mass_per_flyweight_kg,
            display_speed=display_speed,
        )
        if fit is None:
            continue
        rms, maximum, mass, interval, target_x, target_force = fit
        scored.append((rms, maximum, mass, interval, path, target_x, target_force))
    scored.sort(key=lambda item: (item[0], item[1]))
    if not scored:
        return []

    # Quality first, diversity second. Never choose a geometrically interesting
    # path whose profile fit is dramatically worse than the best achievable one.
    best_rms = scored[0][0]
    quality_limit = max(best_rms * 1.6, best_rms + 120.0)
    quality_pool = [item for item in scored if item[0] <= quality_limit][:40]
    if not quality_pool:
        quality_pool = scored[:40]
    pool_by_path = {item[4]: item for item in quality_pool}
    diverse = _diverse_path_order(compiled, [item[4] for item in quality_pool])
    ordered_paths = [scored[0][4]] + [path for path in diverse if path != scored[0][4]]
    for item in scored:
        if item[4] not in ordered_paths:
            ordered_paths.append(item[4])

    existing = {
        tuple(path): document
        for path, document in zip(
            compiled.representative_state_paths,
            compiled.representative_documents,
            strict=True,
        )
    }
    results: list[dict[str, object]] = []
    sample_count = max(161, 20 * compiled.shift_station_count + 1)
    for path in ordered_paths:
        item = pool_by_path.get(path)
        if item is None:
            item = next((entry for entry in scored if entry[4] == path), None)
        if item is None:
            continue
        rms, maximum, mass, interval, _path, target_x, target_force = item
        ramp_path = _path_from_state_indices(
            compiled.architecture,
            compiled.states,
            list(path),
            compiled.shift_station_count,
        )
        document = existing.get(path)
        if certify_history:
            if document is None:
                certification = certify_path_history(
                    ramp_path,
                    trace_sample_count=compiled.history_trace_sample_count,
                )
                if not certification.valid:
                    continue
                document = _path_document(
                    ramp_path,
                    list(path),
                    certification,
                    sample_count=sample_count,
                )
        else:
            data = ramp_path.sample(max(81, 10 * compiled.shift_station_count + 1))
            document = {
                "state_indices": list(path),
                "shift_m": [float(value) for value in data["shift_m"]],
                "q_deg": [degrees(float(value)) for value in data["q_rad"]],
                "ramp_tangent_deg": [float(value) for value in data["ramp_tangent_deg"]],
                "roller_center": {
                    "x_m": [float(value) for value in data["roller_center_x_m"]],
                    "r_m": [float(value) for value in data["roller_center_r_m"]],
                },
                "ramp_surface": {
                    "x_m": [float(value) for value in data["contact_x_m"]],
                    "r_m": [float(value) for value in data["contact_r_m"]],
                },
                "capability": _path_capability_document(compiled.architecture, data),
                "history": {
                    "max_contact_root_count": 0,
                    "multiple_root_shift_count": 0,
                    "trace_shift_m": [],
                    "trace_parameter_m": [],
                    "trace_q_deg": [],
                },
            }
        mass_min, mass_max = interval
        solution = {
            **document,
            "solution": {
                "tip_mass_min_kg": mass_min,
                "tip_mass_max_kg": mass_max,
                "example_tip_mass_kg": mass,
                "force_N": _path_absolute_force_document(
                    document,
                    mass,
                    hard_requirements,
                    display_speed,
                ),
                "profile_fit": {
                    "rms_error_N": rms,
                    "max_abs_error_N": maximum,
                    "target_shift_m": [float(value) for value in target_x],
                    "target_force_N": [float(value) for value in target_force],
                    "history_certified": certify_history,
                },
            },
        }
        results.append(solution)
        if len(results) >= representative_solution_count:
            break

    _SOLUTION_CACHE[cache_key] = results
    return results


def _requirement_mass_masks_for_layer(
    compiled: CompiledPathDomain,
    layer_index: int,
    requirement: ForceRequirement,
    max_mass_kg: float,
    mass_sample_count: int,
) -> list[int]:
    """Vectorized exact force-point mass masks for every edge in one graph layer."""

    arm_gain, tip_gain, active = _edge_gains_at_shift(
        compiled,
        layer_index,
        requirement.shift_m,
    )
    count = len(compiled.viable_edges[layer_index])
    if count == 0:
        return []

    omega2 = requirement.shaft_speed_rad_s * requirement.shaft_speed_rad_s
    target_low = requirement.force_N - requirement.tolerance_N
    target_high = requirement.force_N + requirement.tolerance_N
    base = omega2 * arm_gain
    slope = omega2 * tip_gain
    masks = [0] * count
    all_mask = (1 << mass_sample_count) - 1

    flat = active & (np.abs(slope) <= 1.0e-14)
    flat_ok = flat & (base >= target_low - 1.0e-9) & (base <= target_high + 1.0e-9)
    for index in np.flatnonzero(flat_ok):
        masks[int(index)] = all_mask

    sloped = active & (np.abs(slope) > 1.0e-14)
    if not np.any(sloped):
        return masks

    indices = np.flatnonzero(sloped)
    a = (target_low - base[indices]) / slope[indices]
    b = (target_high - base[indices]) / slope[indices]
    mass_low = np.maximum(0.0, np.minimum(a, b))
    mass_high = np.minimum(max_mass_kg, np.maximum(a, b))
    feasible = mass_high >= mass_low - 1.0e-12
    if max_mass_kg <= 1.0e-15:
        for local_index in np.flatnonzero(feasible):
            if mass_low[local_index] <= 1.0e-12 <= mass_high[local_index] + 1.0e-12:
                masks[int(indices[local_index])] = 1
        return masks

    scale = (mass_sample_count - 1) / max_mass_kg
    first = np.ceil(mass_low * scale - 1.0e-10).astype(np.int64)
    last = np.floor(mass_high * scale + 1.0e-10).astype(np.int64)
    first = np.clip(first, 0, mass_sample_count - 1)
    last = np.clip(last, 0, mass_sample_count - 1)
    feasible &= last >= first
    for local_index in np.flatnonzero(feasible):
        lo = int(first[local_index])
        hi = int(last[local_index])
        masks[int(indices[local_index])] = ((1 << (hi - lo + 1)) - 1) << lo
    return masks


def _edge_gains_at_shift(
    compiled: CompiledPathDomain,
    layer_index: int,
    shift_m: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return exact Hermite arm/tip gains for all viable edges at one shift."""

    key = (id(compiled), int(layer_index), round(float(shift_m), 12))
    cached = _REQUIREMENT_GAIN_CACHE.get(key)
    if cached is not None:
        return cached

    layer_edges = compiled.viable_edges[layer_index]
    if not layer_edges:
        empty = np.asarray([], dtype=float)
        result = (empty, empty, np.asarray([], dtype=bool))
        _REQUIREMENT_GAIN_CACHE[key] = result
        return result

    architecture = compiled.architecture
    layer_count = compiled.shift_station_count - 1
    dx = architecture.required_travel_m / layer_count
    x0 = layer_index * dx
    t = min(1.0, max(0.0, (float(shift_m) - x0) / dx))
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
    q = q0 + M0 * t + A * t * t + B * t * t * t
    dq = (M0 + 2.0 * A * t + 3.0 * B * t * t) / dx

    sin_q = np.sin(q)
    cos_q = np.cos(q)
    n = float(architecture.number_of_flyweights)
    R = architecture.pivot_radius_m
    L = architecture.arm_length_m
    arm_mass = architecture.arm_mass_per_flyweight_kg
    arm_gain = 0.5 * n * arm_mass * (
        R * L * cos_q + (2.0 / 3.0) * L * L * sin_q * cos_q
    ) * dq
    tip_gain = 0.5 * n * (
        2.0 * L * cos_q * (R + L * sin_q)
    ) * dq
    active = (dq > 1.0e-8) & np.isfinite(arm_gain) & np.isfinite(tip_gain)
    result = (arm_gain, tip_gain, active)
    _REQUIREMENT_GAIN_CACHE[key] = result
    return result


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
    representatives = (
        _unconditioned_representatives(
            compiled,
            max_tip_mass_per_flyweight_kg=max_tip_mass_per_flyweight_kg,
            representative_solution_count=representative_solution_count,
            display_speed=display_speed,
        )
        if representative_solution_count > 0
        else []
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

def _node_force_interval_projection(
    compiled: CompiledPathDomain,
    *,
    node_masks: list[dict[int, int]],
    max_tip_mass_per_flyweight_kg: float,
    shaft_speed_rad_s: float,
    mass_sample_count: int,
) -> dict[str, object]:
    """Cheap exact-at-stations force projection for interactive filtering.

    The graph filter already produces a mass bitset for every surviving state.
    Evaluating those states at the graph stations is O(nodes), rather than
    O(edges * display_samples).  This projection is intentionally discrete; it
    is never used to decide whether a new point is placeable.
    """

    omega2 = shaft_speed_rad_s * shaft_speed_rad_s
    architecture = compiled.architecture
    station_count = compiled.shift_station_count
    stations: list[dict[str, object]] = []

    for station in range(station_count):
        shift_m = (
            station / max(1, station_count - 1)
            * architecture.required_travel_m
        )
        force_lows: list[float] = []
        force_highs: list[float] = []
        mass_lows: list[float] = []
        mass_highs: list[float] = []
        active_count = 0

        for state_index, mask in node_masks[station].items():
            if not mask:
                continue
            state = compiled.states[state_index]
            if state.dq_dx_rad_per_m <= 1.0e-8:
                continue
            arm_gain, tip_gain, _ = _normalized_force_gain(
                architecture, state.q_rad, state.dq_dx_rad_per_m
            )
            active_count += 1
            for first, last in _mask_runs(mask):
                low_mass = _mass_from_index(
                    first, max_tip_mass_per_flyweight_kg, mass_sample_count
                )
                high_mass = _mass_from_index(
                    last, max_tip_mass_per_flyweight_kg, mass_sample_count
                )
                a = omega2 * (arm_gain + low_mass * tip_gain)
                b = omega2 * (arm_gain + high_mass * tip_gain)
                force_lows.append(min(a, b))
                force_highs.append(max(a, b))
                mass_lows.append(low_mass)
                mass_highs.append(high_mass)

        merged_force = _merge_numpy_intervals(
            np.asarray(force_lows, dtype=float),
            np.asarray(force_highs, dtype=float),
        )
        merged_mass = _merge_numpy_intervals(
            np.asarray(mass_lows, dtype=float),
            np.asarray(mass_highs, dtype=float),
        )
        stations.append(
            {
                "station": station,
                "shift_m": shift_m,
                "active_state_count": active_count,
                "force_min_N": merged_force[0][0] if merged_force else None,
                "force_max_N": merged_force[-1][1] if merged_force else None,
                "force_intervals_N": [[lo, hi] for lo, hi in merged_force],
                "mass_min_kg": merged_mass[0][0] if merged_mass else None,
                "mass_max_kg": merged_mass[-1][1] if merged_mass else None,
            }
        )

    return {
        "shaft_speed_rad_s": shaft_speed_rad_s,
        "max_tip_mass_per_flyweight_kg": max_tip_mass_per_flyweight_kg,
        "stations": stations,
        "projection_kind": "graph_stations",
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
    """Project attainable force as interval unions without per-sample mask scans."""

    omega2 = shaft_speed_rad_s * shaft_speed_rad_s
    samples: list[dict[str, object]] = []

    run_data: list[tuple[np.ndarray, np.ndarray, np.ndarray] | None] = []
    if edge_mass_masks is not None:
        for masks in edge_mass_masks:
            edge_indices: list[int] = []
            mass_lows: list[float] = []
            mass_highs: list[float] = []
            for edge_index, mask in enumerate(masks):
                if not mask:
                    continue
                for first, last in _mask_runs(mask):
                    edge_indices.append(edge_index)
                    mass_lows.append(
                        _mass_from_index(first, max_tip_mass_per_flyweight_kg, mass_sample_count)
                    )
                    mass_highs.append(
                        _mass_from_index(last, max_tip_mass_per_flyweight_kg, mass_sample_count)
                    )
            if edge_indices:
                run_data.append((
                    np.asarray(edge_indices, dtype=np.int64),
                    np.asarray(mass_lows, dtype=float),
                    np.asarray(mass_highs, dtype=float),
                ))
            else:
                run_data.append(None)

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
            layer_runs = run_data[layer_index]
            if layer_runs is None:
                merged = []
                merged_mass = []
                active_count = 0
            else:
                edge_indices, mass_lows, mass_highs = layer_runs
                valid_runs = active[edge_indices]
                indices = edge_indices[valid_runs]
                lows_mass = mass_lows[valid_runs]
                highs_mass = mass_highs[valid_runs]
                if indices.size == 0:
                    merged = []
                    merged_mass = []
                    active_count = 0
                else:
                    low_force = omega2 * (arm[indices] + lows_mass * tip[indices])
                    high_force = omega2 * (arm[indices] + highs_mass * tip[indices])
                    merged = _merge_numpy_intervals(
                        np.minimum(low_force, high_force),
                        np.maximum(low_force, high_force),
                    )
                    merged_mass = _merge_numpy_intervals(
                        np.minimum(lows_mass, highs_mass),
                        np.maximum(lows_mass, highs_mass),
                    )
                    active_count = int(np.unique(indices).size)

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

def _conditioned_preview_representatives(
    compiled: CompiledPathDomain,
    requirements: tuple[ForceRequirement, ...],
    edge_masks: list[list[int]],
    *,
    max_tip_mass_per_flyweight_kg: float,
    mass_sample_count: int,
    preview_count: int,
    display_speed: float,
) -> list[dict[str, object]]:
    """Return cheap complete-path previews for interactive requirement editing.

    These paths satisfy the current graph constraints and admit one continuous
    constant tip-mass interval through every force point. They intentionally do
    not run the nonlocal history certification used by the final Solutions view.
    """

    if preview_count <= 0:
        return []
    candidates = _candidate_state_paths(
        compiled,
        edge_masks=edge_masks,
        max_candidates=max(18, 4 * preview_count),
    )
    previews: list[dict[str, object]] = []
    sample_count = max(81, 10 * compiled.shift_station_count + 1)
    for state_path in _diverse_path_order(compiled, candidates):
        ramp_path = _path_from_state_indices(
            compiled.architecture,
            compiled.states,
            list(state_path),
            compiled.shift_station_count,
        )
        interval = _continuous_path_mass_interval(
            ramp_path,
            requirements,
            max_tip_mass_per_flyweight_kg,
        )
        if interval is None:
            continue
        data = ramp_path.sample(sample_count)
        document: dict[str, object] = {
            "state_indices": list(state_path),
            "shift_m": [float(value) for value in data["shift_m"]],
            "q_deg": [degrees(float(value)) for value in data["q_rad"]],
            "ramp_tangent_deg": [float(value) for value in data["ramp_tangent_deg"]],
            "roller_center": {
                "x_m": [float(value) for value in data["roller_center_x_m"]],
                "r_m": [float(value) for value in data["roller_center_r_m"]],
            },
            "ramp_surface": {
                "x_m": [float(value) for value in data["contact_x_m"]],
                "r_m": [float(value) for value in data["contact_r_m"]],
            },
            "capability": _path_capability_document(compiled.architecture, data),
            "history": {
                "max_contact_root_count": 0,
                "multiple_root_shift_count": 0,
                "trace_shift_m": [],
                "trace_parameter_m": [],
                "trace_q_deg": [],
            },
        }
        mass_min, mass_max = interval
        example_mass = 0.5 * (mass_min + mass_max)
        previews.append(
            {
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
        )
        if len(previews) >= preview_count:
            break
    return previews


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
    """Extract a small diverse history-certified gallery only on explicit request."""

    if representative_solution_count <= 0:
        return []
    requirement_signature = tuple(
        (
            requirement.id,
            round(requirement.shift_m, 12),
            round(requirement.force_N, 8),
            round(requirement.shaft_speed_rad_s, 8),
            round(requirement.tolerance_N, 8),
        )
        for requirement in requirements
    )
    cache_key = (
        id(compiled),
        requirement_signature,
        round(max_tip_mass_per_flyweight_kg, 12),
        int(mass_sample_count),
        int(representative_solution_count),
        round(display_speed, 8),
    )
    cached = _SOLUTION_CACHE.get(cache_key)
    if cached is not None:
        return cached

    solutions: list[tuple[tuple[int, ...], dict[str, object]]] = []
    seen: set[tuple[int, ...]] = set()

    # Start with already history-certified architecture representatives. Broad
    # requirement regions often retain several of these, so the solution page
    # can open without repeating the expensive nonlocal certification.
    for state_path, document in zip(
        compiled.representative_state_paths,
        compiled.representative_documents,
        strict=True,
    ):
        signature = tuple(state_path)
        ramp_path = _path_from_state_indices(
            compiled.architecture,
            compiled.states,
            list(signature),
            compiled.shift_station_count,
        )
        interval = _continuous_path_mass_interval(
            ramp_path,
            requirements,
            max_tip_mass_per_flyweight_kg,
        )
        if interval is None:
            continue
        mass_min, mass_max = interval
        example_mass = 0.5 * (mass_min + mass_max)
        solution_document = {
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
        solutions.append((signature, solution_document))
        seen.add(signature)
        if len(solutions) >= representative_solution_count:
            result = [item for _, item in solutions]
            _SOLUTION_CACHE[cache_key] = result
            return result

    # Only if the pre-certified atlas did not cover the conditioned region do
    # we search the conditioned graph and certify fresh paths. Keep this pool
    # deliberately bounded; the gallery needs representative designs, not an
    # exhaustive enumeration.
    remaining = representative_solution_count - len(solutions)
    state_paths = _candidate_state_paths(
        compiled,
        edge_masks=edge_masks,
        max_candidates=max(24, 5 * remaining),
    )
    for state_path in _diverse_path_order(compiled, state_paths):
        signature = tuple(state_path)
        if signature in seen:
            continue
        ramp_path = _path_from_state_indices(
            compiled.architecture,
            compiled.states,
            list(signature),
            compiled.shift_station_count,
        )
        interval = _continuous_path_mass_interval(
            ramp_path,
            requirements,
            max_tip_mass_per_flyweight_kg,
        )
        if interval is None:
            continue
        certification = certify_path_history(
            ramp_path,
            trace_sample_count=compiled.history_trace_sample_count,
        )
        if not certification.valid:
            continue
        document = _path_document(
            ramp_path,
            list(signature),
            certification,
            sample_count=max(161, 20 * compiled.shift_station_count + 1),
        )
        mass_min, mass_max = interval
        example_mass = 0.5 * (mass_min + mass_max)
        solution_document = {
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
        solutions.append((signature, solution_document))
        seen.add(signature)
        if len(solutions) >= representative_solution_count:
            break

    ordered_paths = _diverse_path_order(compiled, [path for path, _ in solutions])
    by_path = {path: document for path, document in solutions}
    result = [by_path[path] for path in ordered_paths[:representative_solution_count]]
    _SOLUTION_CACHE[cache_key] = result
    return result


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
