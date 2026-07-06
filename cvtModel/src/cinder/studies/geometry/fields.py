"""Radius-plane and static ratio-sensitivity field evaluation."""

from __future__ import annotations

from math import isfinite, pi, tan

import numpy as np
from numpy.typing import NDArray

from cinder.model.cvt.geometry import BeltSectionSpec

from .types import RadiusPlaneField, RatioSensitivityField


def evaluate_radius_plane(
    *,
    belt: BeltSectionSpec,
    center_distance: float,
    primary_outer_radius: NDArray[np.float64] | np.ndarray,
    secondary_outer_radius: NDArray[np.float64] | np.ndarray,
) -> RadiusPlaneField:
    """Evaluate ratio and implied belt length over a radius plane.

    The field is independent of a particular Case-A or Case-B design except
    for the fixed center distance supplied by the caller. Constant contours of
    ``implied_belt_outer_length`` are the belt-length families for that center
    distance.
    """

    grid = _evaluate_radius_grid(
        belt=belt,
        center_distance=center_distance,
        primary_outer_radius=primary_outer_radius,
        secondary_outer_radius=secondary_outer_radius,
    )
    return RadiusPlaneField(
        primary_outer_radius=grid.primary_axis,
        secondary_outer_radius=grid.secondary_axis,
        ratio=grid.ratio,
        implied_belt_outer_length=grid.implied_belt_outer_length,
        feasible_mask=grid.feasible_mask,
    )


def evaluate_ratio_sensitivity_field(
    *,
    belt: BeltSectionSpec,
    center_distance: float,
    sheave_half_angle: float,
    primary_outer_radius: NDArray[np.float64] | np.ndarray,
    secondary_outer_radius: NDArray[np.float64] | np.ndarray,
) -> RatioSensitivityField:
    """Evaluate geometric ``dR/ds`` over a radius plane.

    This is a static sensitivity field. It intentionally does not require belt
    length or a selected path: those values only choose which valid
    center-distance contour and path are overlaid by a caller.
    """

    if not isfinite(sheave_half_angle) or not 0.0 < sheave_half_angle < pi / 2.0:
        raise ValueError("sheave_half_angle must lie between 0 and pi / 2.")

    grid = _evaluate_radius_grid(
        belt=belt,
        center_distance=center_distance,
        primary_outer_radius=primary_outer_radius,
        secondary_outer_radius=secondary_outer_radius,
    )

    primary_radius_slope = 1.0 / (2.0 * tan(sheave_half_angle))
    secondary_radius_slope = (
        -(grid.primary_wrap_angle / grid.secondary_wrap_angle) * primary_radius_slope
    )

    sensitivity_per_m = (
        secondary_radius_slope * grid.primary_effective_radius
        - grid.secondary_effective_radius * primary_radius_slope
    ) / (grid.primary_effective_radius**2)
    sensitivity_per_m = np.where(grid.feasible_mask, sensitivity_per_m, np.nan)

    return RatioSensitivityField(
        primary_outer_radius=grid.primary_axis,
        secondary_outer_radius=grid.secondary_axis,
        ratio_change_per_m_shift=_readonly(sensitivity_per_m),
        ratio_change_per_mm_shift=_readonly(sensitivity_per_m / 1.0e3),
        feasible_mask=grid.feasible_mask,
    )


class _RadiusGrid:
    """Internal shared numerical grid used by both public field evaluators."""

    def __init__(
        self,
        *,
        primary_axis: NDArray[np.float64],
        secondary_axis: NDArray[np.float64],
        primary_outer_radius: NDArray[np.float64],
        secondary_outer_radius: NDArray[np.float64],
        primary_effective_radius: NDArray[np.float64],
        secondary_effective_radius: NDArray[np.float64],
        primary_wrap_angle: NDArray[np.float64],
        secondary_wrap_angle: NDArray[np.float64],
        ratio: NDArray[np.float64],
        implied_belt_outer_length: NDArray[np.float64],
        feasible_mask: NDArray[np.bool_],
    ) -> None:
        self.primary_axis = primary_axis
        self.secondary_axis = secondary_axis
        self.primary_outer_radius = primary_outer_radius
        self.secondary_outer_radius = secondary_outer_radius
        self.primary_effective_radius = primary_effective_radius
        self.secondary_effective_radius = secondary_effective_radius
        self.primary_wrap_angle = primary_wrap_angle
        self.secondary_wrap_angle = secondary_wrap_angle
        self.ratio = ratio
        self.implied_belt_outer_length = implied_belt_outer_length
        self.feasible_mask = feasible_mask


def _evaluate_radius_grid(
    *,
    belt: BeltSectionSpec,
    center_distance: float,
    primary_outer_radius: NDArray[np.float64] | np.ndarray,
    secondary_outer_radius: NDArray[np.float64] | np.ndarray,
) -> _RadiusGrid:
    if not isinstance(belt, BeltSectionSpec):
        raise TypeError("belt must be a BeltSectionSpec.")
    if not isfinite(center_distance) or center_distance <= 0.0:
        raise ValueError("center_distance must be finite and positive.")

    primary_axis = _radius_axis("primary_outer_radius", primary_outer_radius)
    secondary_axis = _radius_axis("secondary_outer_radius", secondary_outer_radius)
    primary_outer, secondary_outer = np.meshgrid(
        primary_axis,
        secondary_axis,
        indexing="xy",
    )

    cord_depth = belt.cord_depth_from_outer
    primary_effective = primary_outer - cord_depth
    secondary_effective = secondary_outer - cord_depth
    radius_difference = secondary_outer - primary_outer

    feasible_mask = (
        (primary_outer >= belt.height)
        & (secondary_outer >= belt.height)
        & (primary_effective > 0.0)
        & (secondary_effective > 0.0)
        & (primary_outer + secondary_outer < center_distance)
        & (np.abs(radius_difference) < center_distance)
    )

    ratio = np.full(primary_outer.shape, np.nan, dtype=float)
    length = np.full(primary_outer.shape, np.nan, dtype=float)
    primary_wrap = np.full(primary_outer.shape, np.nan, dtype=float)
    secondary_wrap = np.full(primary_outer.shape, np.nan, dtype=float)

    valid_difference = radius_difference[feasible_mask]
    alpha = np.arcsin(valid_difference / center_distance)
    valid_primary_wrap = pi - 2.0 * alpha
    valid_secondary_wrap = pi + 2.0 * alpha
    valid_straight_span = np.sqrt(center_distance**2 - valid_difference**2)

    primary_wrap[feasible_mask] = valid_primary_wrap
    secondary_wrap[feasible_mask] = valid_secondary_wrap
    ratio[feasible_mask] = (
        secondary_effective[feasible_mask] / primary_effective[feasible_mask]
    )
    length[feasible_mask] = (
        primary_outer[feasible_mask] * valid_primary_wrap
        + secondary_outer[feasible_mask] * valid_secondary_wrap
        + 2.0 * valid_straight_span
    )

    return _RadiusGrid(
        primary_axis=_readonly(primary_axis),
        secondary_axis=_readonly(secondary_axis),
        primary_outer_radius=_readonly(primary_outer),
        secondary_outer_radius=_readonly(secondary_outer),
        primary_effective_radius=_readonly(primary_effective),
        secondary_effective_radius=_readonly(secondary_effective),
        primary_wrap_angle=_readonly(primary_wrap),
        secondary_wrap_angle=_readonly(secondary_wrap),
        ratio=_readonly(ratio),
        implied_belt_outer_length=_readonly(length),
        feasible_mask=_readonly(feasible_mask),
    )


def _radius_axis(
    name: str, values: NDArray[np.float64] | np.ndarray
) -> NDArray[np.float64]:
    axis = np.asarray(values, dtype=float)
    if axis.ndim != 1 or axis.size < 2:
        raise ValueError(
            f"{name} must be a one-dimensional array with at least two values."
        )
    if not np.all(np.isfinite(axis)) or np.any(axis <= 0.0):
        raise ValueError(f"{name} must contain only finite positive radii.")
    if np.any(np.diff(axis) <= 0.0):
        raise ValueError(f"{name} must be strictly increasing.")
    return axis.copy()


def _readonly(values: np.ndarray) -> np.ndarray:
    values.setflags(write=False)
    return values
