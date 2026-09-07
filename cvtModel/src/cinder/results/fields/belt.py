"""Standard belt-path domain and analytical belt-tension result field."""

from __future__ import annotations

from dataclasses import dataclass
from math import pi, sin

from cinder.model.cvt.dynamics.equation_context import TrialEquationContext
from cinder.results.inspection import CVTStateInspection

from .expression import (
    FieldExpression,
    abs_expr,
    cos_expr,
    expm1_expr,
    less_than,
    sin_expr,
    sqrt_expr,
    where,
)
from .types import (
    SpatialDomainDefinition,
    SpatialFieldDefinition,
    SpatialRegionDefinition,
)


@dataclass(frozen=True, slots=True)
class BeltTensionBoundaries:
    """The four wrap-boundary tensions recovered from one engaged inspection."""

    primary_in: float
    primary_out: float
    secondary_in: float
    secondary_out: float


def recover_belt_tension_boundaries(
    inspection: CVTStateInspection,
) -> BeltTensionBoundaries | None:
    """Recover exact reduced-model wrap endpoint tensions after integration.

    This is post-processing only.  It evaluates the same closed-form quantities
    implied by the already-solved normal resultants, accelerations, geometry,
    and signed traction utilizations.  Deadzone samples have no engaged belt
    contact and return ``None``.
    """

    contact = inspection.contact
    unknowns = inspection.closure_unknowns
    if contact is None or unknowns is None:
        return None

    snapshot = contact.snapshot
    geometry = snapshot.geometry
    state = snapshot.state
    terms = TrialEquationContext(
        snapshot=snapshot,
        traction_utilization=contact.traction_utilization,
    ).contact_terms
    q = snapshot.belt_linear_density
    sin_beta = sin(snapshot.sheave_half_angle)

    def offsets(radius) -> tuple[float, float]:
        radius_acceleration = (
            radius.d2_center_of_mass_ds2 * state.shift_speed**2
            + radius.d_center_of_mass_ds * unknowns.shift_acceleration
        )
        c_value = q * (
            state.belt_speed**2 - radius.center_of_mass * radius_acceleration
        )
        a_value = q * (
            radius.center_of_mass * unknowns.belt_acceleration
            + radius.d_center_of_mass_ds * state.shift_speed * state.belt_speed
        )
        return c_value, a_value

    primary_c, primary_a = offsets(geometry.primary)
    secondary_c, secondary_a = offsets(geometry.secondary)
    primary_wrap = geometry.primary_wrap_angle
    secondary_wrap = geometry.secondary_wrap_angle

    primary_in = (
        primary_c
        + unknowns.primary_normal_resultant
        * sin_beta
        / (primary_wrap * terms.primary_phi_minus)
        - primary_a * primary_wrap * terms.primary_psi_minus / terms.primary_phi_minus
    )
    primary_out = (
        primary_c
        + terms.primary_exp_neg * (primary_in - primary_c)
        + primary_a * primary_wrap * terms.primary_phi_minus
    )
    secondary_in = (
        secondary_c
        + unknowns.secondary_normal_resultant
        * sin_beta
        / (secondary_wrap * terms.secondary_phi_minus)
        - secondary_a
        * secondary_wrap
        * terms.secondary_psi_minus
        / terms.secondary_phi_minus
    )
    secondary_out = (
        secondary_c
        + terms.secondary_exp_neg * (secondary_in - secondary_c)
        + secondary_a * secondary_wrap * terms.secondary_phi_minus
    )

    return BeltTensionBoundaries(
        primary_in=float(primary_in),
        primary_out=float(primary_out),
        secondary_in=float(secondary_in),
        secondary_out=float(secondary_out),
    )


def build_belt_path_domain(*, center_distance: float) -> SpatialDomainDefinition:
    """Return CINDER's planar effective-radius closed belt path definition."""

    u = FieldExpression.coordinate()
    rp = FieldExpression.signal("geometry.primary_effective_radius")
    rs = FieldExpression.signal("geometry.secondary_effective_radius")
    phi_p = FieldExpression.signal("geometry.primary_wrap_angle")
    phi_s = FieldExpression.signal("geometry.secondary_wrap_angle")
    c = FieldExpression.literal(center_distance)
    alpha = (pi - phi_p) / 2.0

    sin_alpha = sin_expr(alpha)
    cos_alpha = cos_expr(alpha)

    p_upper_x = -rp * sin_alpha
    p_upper_y = rp * cos_alpha
    s_upper_x = c - rs * sin_alpha
    s_upper_y = rs * cos_alpha
    p_lower_x = -rp * sin_alpha
    p_lower_y = -rp * cos_alpha
    s_lower_x = c - rs * sin_alpha
    s_lower_y = -rs * cos_alpha

    straight_length = sqrt_expr(c * c - (rs - rp) * (rs - rp))

    primary_theta = (pi / 2.0) + alpha + u * phi_p
    secondary_theta = (3.0 * pi / 2.0) - alpha + u * phi_s

    def lerp(start, end):
        return start + u * (end - start)

    return SpatialDomainDefinition(
        key="belt.path",
        label="Belt path",
        description=(
            "Planar closed belt path at the effective (cord) radii, ordered from "
            "the secondary upper tangent to the primary upper tangent, around the "
            "primary wrap, across the lower span, and around the secondary wrap."
        ),
        periodic=True,
        embedding_unit="m",
        regions=(
            SpatialRegionDefinition(
                key="upper_span",
                label="Upper straight span",
                length=straight_length,
                x=lerp(s_upper_x, p_upper_x),
                y=lerp(s_upper_y, p_upper_y),
            ),
            SpatialRegionDefinition(
                key="primary_wrap",
                label="Primary wrap",
                length=rp * phi_p,
                x=rp * cos_expr(primary_theta),
                y=rp * sin_expr(primary_theta),
            ),
            SpatialRegionDefinition(
                key="lower_span",
                label="Lower straight span",
                length=straight_length,
                x=lerp(p_lower_x, s_lower_x),
                y=lerp(p_lower_y, s_lower_y),
            ),
            SpatialRegionDefinition(
                key="secondary_wrap",
                label="Secondary wrap",
                length=rs * phi_s,
                x=c + rs * cos_expr(secondary_theta),
                y=rs * sin_expr(secondary_theta),
            ),
        ),
    )


def build_belt_tension_field(*, sheave_half_angle: float) -> SpatialFieldDefinition:
    """Return the compact analytical field definition for belt tension."""

    u = FieldExpression.coordinate()
    t_p_in = FieldExpression.signal("contact.primary_tension_in")
    t_p_out = FieldExpression.signal("contact.primary_tension_out")
    t_s_in = FieldExpression.signal("contact.secondary_tension_in")
    t_s_out = FieldExpression.signal("contact.secondary_tension_out")
    lambda_p = FieldExpression.signal("contact.primary_lambda")
    lambda_s = FieldExpression.signal("contact.secondary_lambda")
    phi_p = FieldExpression.signal("geometry.primary_wrap_angle")
    phi_s = FieldExpression.signal("geometry.secondary_wrap_angle")
    sin_beta = sin(sheave_half_angle)

    def lerp(start, end):
        return start + u * (end - start)

    def wrap(start, end, z):
        # Exact endpoint form of the reduced wrap solution.  ``expm1`` keeps
        # small nonzero z stable; the explicit z=0 branch gives the linear
        # limit without exposing any CVT-specific operation to consumers.
        weight = where(
            less_than(abs_expr(z), 1.0e-10),
            u,
            expm1_expr(-z * u) / expm1_expr(-z),
        )
        return start + (end - start) * weight

    z_p = lambda_p * phi_p / sin_beta
    z_s = lambda_s * phi_s / sin_beta

    return SpatialFieldDefinition(
        key="belt.tension",
        label="Belt tension",
        unit="N",
        group="contact",
        domain_key="belt.path",
        description=(
            "Continuous tensile force around the reduced closed belt loop. "
            "Wrap regions use CINDER's analytical tension evolution and straight "
            "spans use the exact linear span balance between solved endpoints."
        ),
        regions={
            "upper_span": lerp(t_s_out, t_p_in),
            "primary_wrap": wrap(t_p_in, t_p_out, z_p),
            "lower_span": lerp(t_p_out, t_s_in),
            "secondary_wrap": wrap(t_s_in, t_s_out, z_s),
        },
    )
