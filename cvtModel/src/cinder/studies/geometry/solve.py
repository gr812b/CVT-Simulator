"""Case A and Case B static geometry solves."""

from __future__ import annotations

from math import isfinite

import numpy as np
from scipy.optimize import brentq

from cinder.model.cvt.geometry import BeltPulleyGeometry

from .types import (
    EndpointRadiiDesignRequest,
    GeometryDesignContext,
    GeometryDesignInfeasibleError,
    GeometryEndpoint,
    ResolvedGeometryDesign,
    TargetRatioDesignRequest,
)

_ROOT_TOLERANCE = 1.0e-12
_SCAN_POINTS = 96


def solve_geometry_from_endpoint_radii(
    request: EndpointRadiiDesignRequest,
) -> ResolvedGeometryDesign:
    """Resolve Case A from primary-minimum and secondary-maximum radii.

    The existing :class:`BeltPulleyGeometrySpec` construction performs the
    canonical belt-length closure and resolves the complementary endpoint.
    """

    try:
        geometry_spec = request.context.build_geometry_spec(
            primary_outer_radius_at_zero_shift=(
                request.primary_outer_radius_at_zero_shift
            ),
            secondary_outer_radius_at_zero_shift=(
                request.secondary_outer_radius_at_zero_shift
            ),
        )
    except (ValueError, RuntimeError) as error:
        raise GeometryDesignInfeasibleError(str(error)) from error

    return _resolved_design_from_spec(geometry_spec)


def solve_geometry_from_target_ratios(
    request: TargetRatioDesignRequest,
) -> ResolvedGeometryDesign:
    """Resolve Case B from target maximum and minimum effective-radius ratios.

    Under CINDER's fixed active primary radial travel, the low-end primary
    outer radius is the sole scalar unknown. The implementation scans the
    physically admissible interval before root refinement so it verifies the
    uniqueness observed in the Case-B investigation rather than silently
    assuming a one-root bracket.
    """

    context = request.context
    lower_bound, upper_bound = _primary_low_radius_bounds(
        context=context,
        maximum_ratio=request.maximum_ratio,
    )
    if not lower_bound < upper_bound:
        raise GeometryDesignInfeasibleError(
            "No admissible low-end primary radius exists for the requested "
            "maximum ratio under the fixed shift-travel convention."
        )

    trial_radii = np.linspace(lower_bound, upper_bound, _SCAN_POINTS)
    residuals = np.full(trial_radii.shape, np.nan, dtype=float)
    for index, primary_radius in enumerate(trial_radii):
        try:
            candidate = _resolve_case_b_trial(
                context=context,
                maximum_ratio=request.maximum_ratio,
                primary_outer_radius_at_zero_shift=float(primary_radius),
            )
        except GeometryDesignInfeasibleError:
            continue
        residuals[index] = (
            candidate.minimum_ratio_endpoint.ratio - request.minimum_ratio
        )

    root_intervals: list[tuple[float, float]] = []
    exact_roots: list[float] = []
    for x0, x1, f0, f1 in zip(
        trial_radii[:-1],
        trial_radii[1:],
        residuals[:-1],
        residuals[1:],
        strict=True,
    ):
        if not (isfinite(float(f0)) and isfinite(float(f1))):
            continue
        if abs(float(f0)) <= _ROOT_TOLERANCE:
            exact_roots.append(float(x0))
        if f0 * f1 < 0.0:
            root_intervals.append((float(x0), float(x1)))

    last_residual = residuals[-1]
    if isfinite(float(last_residual)) and abs(float(last_residual)) <= _ROOT_TOLERANCE:
        exact_roots.append(float(trial_radii[-1]))

    roots = _deduplicate_roots(exact_roots)
    for lower, upper in root_intervals:
        root = brentq(
            lambda primary_radius: _case_b_residual(
                context=context,
                maximum_ratio=request.maximum_ratio,
                minimum_ratio=request.minimum_ratio,
                primary_outer_radius_at_zero_shift=primary_radius,
            ),
            lower,
            upper,
            xtol=_ROOT_TOLERANCE,
            rtol=4.0 * np.finfo(float).eps,
        )
        roots = _deduplicate_roots([*roots, root])

    if not roots:
        raise GeometryDesignInfeasibleError(
            "No fixed-travel geometry reaches the requested maximum and "
            "minimum ratio pair."
        )
    if len(roots) != 1:
        raise RuntimeError(
            "Target-ratio geometry produced multiple admissible roots. "
            "The current fixed-travel solver requires a unique design."
        )

    return _resolve_case_b_trial(
        context=context,
        maximum_ratio=request.maximum_ratio,
        primary_outer_radius_at_zero_shift=roots[0],
    )


def _resolved_design_from_spec(geometry_spec) -> ResolvedGeometryDesign:
    geometry = BeltPulleyGeometry(geometry_spec)
    zero = geometry.evaluate(0.0)
    maximum_shift = geometry.evaluate(geometry_spec.max_shift)
    return ResolvedGeometryDesign(
        geometry_spec=geometry_spec,
        maximum_ratio_endpoint=_endpoint_from_position(zero),
        minimum_ratio_endpoint=_endpoint_from_position(maximum_shift),
    )


def _endpoint_from_position(position) -> GeometryEndpoint:
    ratio = position.secondary.effective / position.primary.effective
    return GeometryEndpoint(
        shift=position.shift,
        primary_outer_radius=position.primary.outer,
        secondary_outer_radius=position.secondary.outer,
        primary_effective_radius=position.primary.effective,
        secondary_effective_radius=position.secondary.effective,
        ratio=ratio,
        primary_wrap_angle=position.primary_wrap_angle,
        secondary_wrap_angle=position.secondary_wrap_angle,
    )


def _resolve_case_b_trial(
    *,
    context: GeometryDesignContext,
    maximum_ratio: float,
    primary_outer_radius_at_zero_shift: float,
) -> ResolvedGeometryDesign:
    cord_depth = context.belt.cord_depth_from_outer
    secondary_outer_radius_at_zero_shift = cord_depth + maximum_ratio * (
        primary_outer_radius_at_zero_shift - cord_depth
    )
    try:
        geometry_spec = context.build_geometry_spec(
            primary_outer_radius_at_zero_shift=primary_outer_radius_at_zero_shift,
            secondary_outer_radius_at_zero_shift=secondary_outer_radius_at_zero_shift,
        )
    except (ValueError, RuntimeError) as error:
        raise GeometryDesignInfeasibleError(str(error)) from error
    return _resolved_design_from_spec(geometry_spec)


def _case_b_residual(
    *,
    context: GeometryDesignContext,
    maximum_ratio: float,
    minimum_ratio: float,
    primary_outer_radius_at_zero_shift: float,
) -> float:
    design = _resolve_case_b_trial(
        context=context,
        maximum_ratio=maximum_ratio,
        primary_outer_radius_at_zero_shift=primary_outer_radius_at_zero_shift,
    )
    return design.minimum_ratio_endpoint.ratio - minimum_ratio


def _primary_low_radius_bounds(
    *,
    context: GeometryDesignContext,
    maximum_ratio: float,
) -> tuple[float, float]:
    """Conservative physical bounds for the Case-B scalar trial variable."""

    belt = context.belt
    belt_height = belt.height
    cord_depth = belt.cord_depth_from_outer
    belt_length = context.belt_outer_length
    delta_primary = context.active_primary_radial_travel

    # Both low-end outer radii must contain the physical belt cross-section.
    lower_bound = max(
        belt_height,
        cord_depth + np.finfo(float).eps,
        cord_depth + (belt_height - cord_depth) / maximum_ratio,
    )

    # Necessary, not sufficient, endpoint-length conditions.
    maximum_low_from_length = (
        belt_length / np.pi - (1.0 - maximum_ratio) * cord_depth
    ) / (1.0 + maximum_ratio)
    maximum_high_from_containment = belt_length / np.pi - belt_height - delta_primary
    upper_bound = min(maximum_low_from_length, maximum_high_from_containment)

    # Keep the scalar solve inside the open physical interval.
    return lower_bound, upper_bound * (1.0 - 1.0e-10)


def _deduplicate_roots(roots: list[float]) -> list[float]:
    unique: list[float] = []
    for root in sorted(roots):
        if not unique or abs(root - unique[-1]) > 1.0e-9:
            unique.append(root)
    return unique
