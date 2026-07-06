"""Sampled static shift paths and compact geometry summaries."""

from __future__ import annotations

import numpy as np

from cinder.model.cvt.geometry import BeltPulleyGeometry

from .types import GeometryDesignSummary, GeometryPathTable, ResolvedGeometryDesign


def summarize_geometry_design(design: ResolvedGeometryDesign) -> GeometryDesignSummary:
    """Return scalar range and packaging data from a resolved geometry design."""

    maximum = design.maximum_ratio_endpoint
    minimum = design.minimum_ratio_endpoint
    spec = design.geometry_spec
    return GeometryDesignSummary(
        center_distance=spec.center_distance,
        active_shift_travel=spec.max_shift - spec.deadzone_shift,
        active_primary_radial_travel=(
            spec.primary_outer_radius_at_max_shift
            - spec.primary_outer_radius_at_zero_shift
        ),
        maximum_ratio=maximum.ratio,
        minimum_ratio=minimum.ratio,
        ratio_span=design.ratio_span,
        primary_outer_radius_min=maximum.primary_outer_radius,
        primary_outer_radius_max=minimum.primary_outer_radius,
        secondary_outer_radius_min=minimum.secondary_outer_radius,
        secondary_outer_radius_max=maximum.secondary_outer_radius,
        primary_effective_radius_min=maximum.primary_effective_radius,
        primary_effective_radius_max=minimum.primary_effective_radius,
        secondary_effective_radius_min=minimum.secondary_effective_radius,
        secondary_effective_radius_max=maximum.secondary_effective_radius,
    )


def sample_geometry_path(
    design: ResolvedGeometryDesign,
    *,
    sample_count: int = 201,
) -> GeometryPathTable:
    """Evaluate the canonical CINDER geometry over its complete shift range."""

    if sample_count < 2:
        raise ValueError("sample_count must be at least two.")

    spec = design.geometry_spec
    geometry = BeltPulleyGeometry(spec)
    shifts = np.linspace(0.0, spec.max_shift, sample_count, dtype=float)

    primary_outer = np.empty(sample_count, dtype=float)
    secondary_outer = np.empty(sample_count, dtype=float)
    primary_effective = np.empty(sample_count, dtype=float)
    secondary_effective = np.empty(sample_count, dtype=float)
    ratio = np.empty(sample_count, dtype=float)
    ratio_per_m = np.empty(sample_count, dtype=float)
    primary_wrap = np.empty(sample_count, dtype=float)
    secondary_wrap = np.empty(sample_count, dtype=float)

    for index, shift in enumerate(shifts):
        position = geometry.evaluate(float(shift))
        primary_outer[index] = position.primary.outer
        secondary_outer[index] = position.secondary.outer
        primary_effective[index] = position.primary.effective
        secondary_effective[index] = position.secondary.effective
        ratio[index] = position.secondary.effective / position.primary.effective
        ratio_per_m[index] = (
            position.secondary.d_effective_ds * position.primary.effective
            - position.secondary.effective * position.primary.d_effective_ds
        ) / (position.primary.effective**2)
        primary_wrap[index] = position.primary_wrap_angle
        secondary_wrap[index] = position.secondary_wrap_angle

    return GeometryPathTable(
        shift=_readonly(shifts),
        primary_outer_radius=_readonly(primary_outer),
        secondary_outer_radius=_readonly(secondary_outer),
        primary_effective_radius=_readonly(primary_effective),
        secondary_effective_radius=_readonly(secondary_effective),
        ratio=_readonly(ratio),
        ratio_change_per_m_shift=_readonly(ratio_per_m),
        ratio_change_per_mm_shift=_readonly(ratio_per_m / 1.0e3),
        primary_wrap_angle=_readonly(primary_wrap),
        secondary_wrap_angle=_readonly(secondary_wrap),
    )


def _readonly(values: np.ndarray) -> np.ndarray:
    values.setflags(write=False)
    return values
