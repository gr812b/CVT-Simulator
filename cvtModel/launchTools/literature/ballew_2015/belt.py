"""Mass- and geometry-preserving belt reconstruction for Ballew (2015)."""

from __future__ import annotations

from dataclasses import dataclass
from math import asin, isclose, pi, radians, sqrt, tan

from scipy.optimize import brentq

from cinder.model.cvt.geometry import (
    BeltPulleyGeometry,
    BeltPulleyGeometrySpec,
    BeltSectionSpec,
)

from constants import PUBLISHED


_ROOT_TOLERANCE = 1.0e-12


@dataclass(frozen=True, slots=True)
class BallewEquivalentBeltMapping:
    """Resolved bridge from Ballew's one-dimensional belt to CINDER geometry.

    Ballew's transient model represents the belt as a one-dimensional nodal
    path. CINDER separately tracks the belt outer surface and a cord-line
    effective radius. Reconstruction A4 identifies Ballew's nodal path with
    CINDER's effective/cord-line path, then offsets the CINDER outer geometry
    by the Figure 39 cord depth.

    The smooth trapezoid is an equivalent load-carrying core, not a literal
    representation of the cogged belt envelope. Its density is therefore an
    *effective mass density* selected so the resolved CINDER belt mass is the
    published 1.000 kg exactly.
    """

    section: BeltSectionSpec
    reference_effective_length_m: float
    cinder_outer_length_m: float
    equivalent_cross_sectional_area_m2: float
    effective_density_kg_per_m3: float
    primary_effective_radius_at_zero_shift_m: float
    secondary_effective_radius_at_zero_shift_m: float
    maximum_shift_m: float

    @property
    def resolved_mass_kg(self) -> float:
        return (
            self.effective_density_kg_per_m3
            * self.equivalent_cross_sectional_area_m2
            * self.cinder_outer_length_m
        )


def build_equivalent_belt_mapping() -> BallewEquivalentBeltMapping:
    """Resolve the Ballew belt into CINDER's smooth-section conventions.

    Reconstruction A4, summarized:

    * Figure 39 supplies the smooth equivalent section and cord-line depth.
    * Ballew's published belt length is treated as the one-dimensional nodal /
      effective-path length used by his transient algorithm.
    * Offsetting both pulley radii outward by the constant cord depth leaves
      the straight spans unchanged and increases total open-belt length by
      ``2*pi*d`` because the two wrap angles sum to ``2*pi``.
    * Effective density is selected from ``m = rho*A*L_outer`` so CINDER
      carries Ballew's published 1 kg total belt mass exactly.
    """

    section = BeltSectionSpec(
        height=PUBLISHED.figure39_core_height_m,
        outer_width=PUBLISHED.figure39_core_outer_width_m,
        inner_width=PUBLISHED.figure39_core_inner_width_m,
        cord_depth_from_outer=PUBLISHED.figure39_cord_depth_from_outer_m,
    )
    area = 0.5 * section.height * (section.outer_width + section.inner_width)

    reference_length = PUBLISHED.belt_length_m
    outer_length = reference_length + 2.0 * pi * section.cord_depth_from_outer
    effective_density = PUBLISHED.belt_mass_kg / (area * outer_length)

    # Ballew's listed minimum radii are hard search limits, not simultaneous
    # endpoints of the fixed-length loop. At the low-ratio end the secondary
    # reaches its published maximum first. Solve the compatible primary radius
    # from Ballew's own L, C, and r_s,max. See reconstruction A4.
    primary_zero = brentq(
        lambda primary_radius: (
            _open_belt_length(
                center_distance=PUBLISHED.center_distance_m,
                primary_radius=primary_radius,
                secondary_radius=PUBLISHED.output_radius_max_m,
            )
            - reference_length
        ),
        PUBLISHED.input_radius_min_m,
        PUBLISHED.input_radius_max_m,
        xtol=_ROOT_TOLERANCE,
    )
    secondary_zero = PUBLISHED.output_radius_max_m

    # Use s=0 as the compatible low-ratio geometric endpoint and choose the
    # upper shift so the primary reaches Ballew's published maximum radius.
    # Ballew begins Chapter 5 already engaged, so no deadzone is introduced.
    maximum_shift = 2.0 * tan(radians(PUBLISHED.sheave_half_angle_deg)) * (
        PUBLISHED.input_radius_max_m - primary_zero
    )

    mapping = BallewEquivalentBeltMapping(
        section=section,
        reference_effective_length_m=reference_length,
        cinder_outer_length_m=outer_length,
        equivalent_cross_sectional_area_m2=area,
        effective_density_kg_per_m3=effective_density,
        primary_effective_radius_at_zero_shift_m=primary_zero,
        secondary_effective_radius_at_zero_shift_m=secondary_zero,
        maximum_shift_m=maximum_shift,
    )
    _validate_mapping(mapping)
    return mapping


def build_ballew_geometry(
    mapping: BallewEquivalentBeltMapping | None = None,
) -> BeltPulleyGeometry:
    """Build CINDER geometry while preserving Ballew's effective belt path."""

    mapping = mapping or build_equivalent_belt_mapping()
    cord_depth = mapping.section.cord_depth_from_outer

    geometry = BeltPulleyGeometry(
        BeltPulleyGeometrySpec(
            belt=mapping.section,
            belt_outer_length=mapping.cinder_outer_length_m,
            primary_outer_radius_at_zero_shift=(
                mapping.primary_effective_radius_at_zero_shift_m + cord_depth
            ),
            secondary_outer_radius_at_zero_shift=(
                mapping.secondary_effective_radius_at_zero_shift_m + cord_depth
            ),
            sheave_half_angle=radians(PUBLISHED.sheave_half_angle_deg),
            deadzone_shift=0.0,
            max_shift=mapping.maximum_shift_m,
        )
    )

    if not isclose(
        geometry.spec.center_distance,
        PUBLISHED.center_distance_m,
        rel_tol=0.0,
        abs_tol=2.0e-12,
    ):
        raise RuntimeError(
            "Ballew geometry reconstruction no longer preserves the published "
            "center distance."
        )
    return geometry


def solve_initial_shift_from_published_speeds(geometry: BeltPulleyGeometry) -> float:
    """Return the engaged shift consistent with Ballew's exact 2500/1136 RPM.

    Table B1's ``2.2`` ratio is treated as a rounded description. The two
    explicitly tabulated shaft speeds are used as the authoritative initial
    rotational state (reconstruction A3).
    """

    target_speed_ratio = PUBLISHED.initial_input_rpm / PUBLISHED.initial_output_rpm

    def ratio_residual(shift: float) -> float:
        position = geometry.evaluate(shift)
        geometric_speed_ratio = position.secondary.effective / position.primary.effective
        return geometric_speed_ratio - target_speed_ratio

    lower = ratio_residual(0.0)
    upper = ratio_residual(geometry.spec.max_shift)
    if lower == 0.0:
        return 0.0
    if upper == 0.0:
        return geometry.spec.max_shift
    if lower * upper > 0.0:
        raise RuntimeError(
            "Published Ballew initial shaft-speed ratio lies outside the "
            "reconstructed geometry range."
        )
    return brentq(ratio_residual, 0.0, geometry.spec.max_shift, xtol=_ROOT_TOLERANCE)


def _open_belt_length(
    *, center_distance: float, primary_radius: float, secondary_radius: float
) -> float:
    """Open-belt length on Ballew's one-dimensional/effective path datum."""

    difference = secondary_radius - primary_radius
    alpha = asin(difference / center_distance)
    primary_wrap = pi - 2.0 * alpha
    secondary_wrap = pi + 2.0 * alpha
    span = sqrt(center_distance**2 - difference**2)
    return primary_radius * primary_wrap + secondary_radius * secondary_wrap + 2.0 * span


def _validate_mapping(mapping: BallewEquivalentBeltMapping) -> None:
    if not isclose(
        mapping.resolved_mass_kg,
        PUBLISHED.belt_mass_kg,
        rel_tol=0.0,
        abs_tol=2.0e-12,
    ):
        raise RuntimeError("Equivalent belt mapping no longer preserves 1 kg mass.")

    implied_reference_length = _open_belt_length(
        center_distance=PUBLISHED.center_distance_m,
        primary_radius=mapping.primary_effective_radius_at_zero_shift_m,
        secondary_radius=mapping.secondary_effective_radius_at_zero_shift_m,
    )
    if not isclose(
        implied_reference_length,
        mapping.reference_effective_length_m,
        rel_tol=0.0,
        abs_tol=2.0e-12,
    ):
        raise RuntimeError("Equivalent belt mapping no longer preserves Ballew belt length.")
