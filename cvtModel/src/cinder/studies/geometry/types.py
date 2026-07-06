"""Typed inputs and numeric outputs for static belt-pulley geometry studies."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, pi, tan
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from cinder.model.cvt.geometry import BeltPulleyGeometrySpec, BeltSectionSpec


class GeometryDesignInfeasibleError(ValueError):
    """Raised when a requested static geometry cannot be resolved physically."""


@dataclass(frozen=True, slots=True)
class GeometryDesignContext:
    """Fixed inputs shared by both geometry-design solve modes.

    This is deliberately the unresolved portion of
    :class:`~cinder.model.cvt.geometry.BeltPulleyGeometrySpec`: it contains
    the belt and shift convention but not a selected endpoint geometry.
    """

    belt: BeltSectionSpec
    belt_outer_length: float
    sheave_half_angle: float
    deadzone_shift: float
    max_shift: float

    def __post_init__(self) -> None:
        if not isinstance(self.belt, BeltSectionSpec):
            raise TypeError("belt must be a BeltSectionSpec.")
        _require_positive("belt_outer_length", self.belt_outer_length)
        if (
            not isfinite(self.sheave_half_angle)
            or not 0.0 < self.sheave_half_angle < pi / 2.0
        ):
            raise ValueError("sheave_half_angle must lie between 0 and pi / 2.")
        _require_nonnegative("deadzone_shift", self.deadzone_shift)
        _require_nonnegative("max_shift", self.max_shift)
        if self.max_shift < self.deadzone_shift:
            raise ValueError(
                "max_shift must be greater than or equal to deadzone_shift."
            )

    @property
    def active_shift_travel(self) -> float:
        """Primary axial travel that changes the belt radii."""

        return self.max_shift - self.deadzone_shift

    @property
    def active_primary_radial_travel(self) -> float:
        """Primary outer-radius increase across active shift travel."""

        return self.active_shift_travel / (2.0 * tan(self.sheave_half_angle))

    def build_geometry_spec(
        self,
        *,
        primary_outer_radius_at_zero_shift: float,
        secondary_outer_radius_at_zero_shift: float,
    ) -> BeltPulleyGeometrySpec:
        """Construct CINDER's canonical resolved runtime geometry object."""

        return BeltPulleyGeometrySpec(
            belt=self.belt,
            belt_outer_length=self.belt_outer_length,
            primary_outer_radius_at_zero_shift=primary_outer_radius_at_zero_shift,
            secondary_outer_radius_at_zero_shift=secondary_outer_radius_at_zero_shift,
            sheave_half_angle=self.sheave_half_angle,
            deadzone_shift=self.deadzone_shift,
            max_shift=self.max_shift,
        )


@dataclass(frozen=True, slots=True)
class EndpointRadiiDesignRequest:
    """Case A: resolve a design from low-ratio endpoint outer radii."""

    context: GeometryDesignContext
    primary_outer_radius_at_zero_shift: float
    secondary_outer_radius_at_zero_shift: float

    def __post_init__(self) -> None:
        if not isinstance(self.context, GeometryDesignContext):
            raise TypeError("context must be a GeometryDesignContext.")
        _require_positive(
            "primary_outer_radius_at_zero_shift",
            self.primary_outer_radius_at_zero_shift,
        )
        _require_positive(
            "secondary_outer_radius_at_zero_shift",
            self.secondary_outer_radius_at_zero_shift,
        )


@dataclass(frozen=True, slots=True)
class TargetRatioDesignRequest:
    """Case B: resolve a design from desired maximum and minimum CVT ratios."""

    context: GeometryDesignContext
    maximum_ratio: float
    minimum_ratio: float

    def __post_init__(self) -> None:
        if not isinstance(self.context, GeometryDesignContext):
            raise TypeError("context must be a GeometryDesignContext.")
        _require_positive("maximum_ratio", self.maximum_ratio)
        _require_positive("minimum_ratio", self.minimum_ratio)
        if self.maximum_ratio <= self.minimum_ratio:
            raise ValueError(
                "maximum_ratio must exceed minimum_ratio under CINDER's "
                "zero-shift-to-max-shift convention."
            )


@dataclass(frozen=True, slots=True)
class GeometryEndpoint:
    """Resolved static geometry at one end of the available shift range."""

    shift: float
    primary_outer_radius: float
    secondary_outer_radius: float
    primary_effective_radius: float
    secondary_effective_radius: float
    ratio: float
    primary_wrap_angle: float
    secondary_wrap_angle: float


@dataclass(frozen=True, slots=True)
class ResolvedGeometryDesign:
    """One fully resolved belt-pulley design shared by Case A and Case B."""

    geometry_spec: BeltPulleyGeometrySpec
    maximum_ratio_endpoint: GeometryEndpoint
    minimum_ratio_endpoint: GeometryEndpoint

    def __post_init__(self) -> None:
        if not isinstance(self.geometry_spec, BeltPulleyGeometrySpec):
            raise TypeError("geometry_spec must be a BeltPulleyGeometrySpec.")

    @property
    def center_distance(self) -> float:
        return self.geometry_spec.center_distance

    @property
    def ratio_span(self) -> float:
        return self.maximum_ratio_endpoint.ratio / self.minimum_ratio_endpoint.ratio


@dataclass(frozen=True, slots=True)
class GeometryDesignSummary:
    """Compact scalar geometry outputs for cards, tables, or JSON APIs."""

    center_distance: float
    active_shift_travel: float
    active_primary_radial_travel: float
    maximum_ratio: float
    minimum_ratio: float
    ratio_span: float
    primary_outer_radius_min: float
    primary_outer_radius_max: float
    secondary_outer_radius_min: float
    secondary_outer_radius_max: float
    primary_effective_radius_min: float
    primary_effective_radius_max: float
    secondary_effective_radius_min: float
    secondary_effective_radius_max: float


@dataclass(frozen=True, slots=True)
class GeometryPathTable:
    """A sampled shift path through one resolved geometry design.

    All arrays are one-dimensional and share the same length.
    """

    shift: NDArray[np.float64]
    primary_outer_radius: NDArray[np.float64]
    secondary_outer_radius: NDArray[np.float64]
    primary_effective_radius: NDArray[np.float64]
    secondary_effective_radius: NDArray[np.float64]
    ratio: NDArray[np.float64]
    ratio_change_per_m_shift: NDArray[np.float64]
    ratio_change_per_mm_shift: NDArray[np.float64]
    primary_wrap_angle: NDArray[np.float64]
    secondary_wrap_angle: NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class RadiusPlaneField:
    """Radius-plane values at one fixed center distance.

    Two-dimensional arrays use the shape ``(secondary_axis.size,
    primary_axis.size)``. Invalid geometric combinations are marked by
    ``feasible_mask=False`` and represented as NaN in numeric fields.
    """

    primary_outer_radius: NDArray[np.float64]
    secondary_outer_radius: NDArray[np.float64]
    ratio: NDArray[np.float64]
    implied_belt_outer_length: NDArray[np.float64]
    feasible_mask: NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class RatioSensitivityField:
    """Static ratio sensitivity over a radius plane at one center distance.

    The rate is geometric ``dR/ds`` rather than dynamic ``dR/dt``. Two-
    dimensional arrays use the shape ``(secondary_axis.size,
    primary_axis.size)``.
    """

    primary_outer_radius: NDArray[np.float64]
    secondary_outer_radius: NDArray[np.float64]
    ratio_change_per_m_shift: NDArray[np.float64]
    ratio_change_per_mm_shift: NDArray[np.float64]
    feasible_mask: NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class GeometryFeasibilityIssue:
    """One structured static-design warning or error."""

    code: str
    severity: Literal["error", "warning"]
    message: str
    shift: float | None = None


@dataclass(frozen=True, slots=True)
class GeometryFeasibilityReport:
    """Feasibility findings for an already resolved static geometry design."""

    is_feasible: bool
    issues: tuple[GeometryFeasibilityIssue, ...]


def _require_positive(name: str, value: float) -> None:
    if not isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be finite and positive.")


def _require_nonnegative(name: str, value: float) -> None:
    if not isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative.")
