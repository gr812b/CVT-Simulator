"""Exact CINDER-facing mechanics for the fixed-pivot primary design tool.

This module is the only part of the feature that imports CINDER mechanics.
Geometry is solved once for a concrete ramp, then operating-condition response
is evaluated from the cached geometry path without re-solving roller contact.
The actual flyweight closing-force law remains CINDER's
``FixedPivotFlyweightForce`` rather than being duplicated here.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, degrees, hypot, pi, sin, sqrt
import numpy as np

from cinder.model.cvt.actuation import (
    FixedPivotFlyweightForce,
    FixedPivotFlyweightForceSpec,
    FixedPivotFlyweightSample,
    FlyweightMassGeometry,
    PivotedRollerFollowerFlyweightMap,
    PivotedRollerFollowerGeometry,
    PivotedRollerFollowerGeometrySpec,
    PulleyActuationContext,
)
from cinder.model.cvt.closure import AffineClosureScalar, ClosureUnknowns
from cinder.model.cvt.profiles import (
    C3TransitionSegment,
    CircularSegment,
    LinearSegment,
    PiecewiseRamp,
)

from .models import ArchitectureDesign, OperatingCondition, RampDesign

HALF_PI = 0.5 * pi


@dataclass(frozen=True, slots=True)
class GeometryPoint:
    shift_m: float
    angle_rad: float
    angle_gradient_rad_per_m: float
    angle_curvature_rad_per_m2: float
    contact_coordinate_m: float
    contact_x_m: float
    contact_r_m: float
    roller_center_x_m: float
    roller_center_r_m: float
    ramp_tangent_deg: float
    ramp_normal_x: float
    ramp_normal_r: float


@dataclass(frozen=True, slots=True)
class GeometryAnalysis:
    architecture: ArchitectureDesign
    ramp_design: RampDesign
    ramp: PiecewiseRamp
    geometry_spec: PivotedRollerFollowerGeometrySpec
    points: tuple[GeometryPoint, ...]
    requested_travel_m: float
    contact_valid_travel_m: float
    contact_range_complete: bool
    ramp_surface_open_x_m: tuple[float, ...]
    ramp_surface_open_r_m: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class _SingleSampleMap:
    """Minimal structural implementation of CINDER's FixedPivotFlyweightMap."""

    sample: FixedPivotFlyweightSample
    axial_position_min: float = 0.0
    axial_position_max: float = 1.0

    def evaluate(self, axial_position: float) -> FixedPivotFlyweightSample:
        del axial_position
        return self.sample


def build_ramp(design: RampDesign) -> PiecewiseRamp:
    _validate_ramp_design(design)
    if design.kind == "constant":
        return PiecewiseRamp(
            (
                LinearSegment(
                    length=design.total_length_m,
                    angle_degrees=design.start_angle_deg,
                ),
            )
        )

    linear = LinearSegment(
        length=design.linear_length_m,
        angle_degrees=design.start_angle_deg,
    )
    circular = CircularSegment(
        length=design.circular_length_m,
        angle_start_degrees=design.start_angle_deg,
        angle_end_degrees=design.end_angle_deg,
        quadrant=2,
    )
    blend = C3TransitionSegment.between_segments(
        left=linear,
        right=circular,
        length=design.blend_length_m,
    )
    ramp = PiecewiseRamp((linear, blend, circular))
    ramp.require_continuity(order=3)
    return ramp


def analyze_geometry(
    architecture: ArchitectureDesign,
    ramp_design: RampDesign,
    *,
    sample_count: int,
) -> GeometryAnalysis:
    _validate_architecture(architecture)
    if sample_count < 3:
        raise ValueError("sample_count must be at least 3.")

    ramp = build_ramp(ramp_design)
    requested_max = architecture.required_travel_m
    full_spec = _geometry_spec(
        architecture,
        ramp_design,
        ramp,
        axial_position_max=requested_max,
    )
    provisional = PivotedRollerFollowerGeometry(full_spec)

    probe_count = max(1025, 8 * sample_count + 1)
    probe = np.linspace(0.0, requested_max, probe_count)
    trace = provisional.trace_contact_branch(probe, require_complete=False)
    if len(trace) < 2:
        raise ValueError(
            "No continuous roller/ramp contact branch exists from the fully-open position."
        )

    complete = len(trace) == len(probe)
    if complete:
        valid_max = requested_max
    else:
        # Leave one full probe interval before the first failed point so the
        # stricter production map is not compiled on the loss-of-contact edge.
        safe_index = max(1, len(trace) - 2)
        valid_max = float(probe[safe_index])

    mechanism_map = _build_production_map(
        architecture,
        ramp_design,
        ramp,
        axial_position_max=valid_max,
        compilation_points=max(129, min(513, 2 * sample_count + 1)),
    )

    shifts = np.linspace(0.0, valid_max, sample_count)
    points = tuple(
        _geometry_point(mechanism_map, ramp, float(shift))
        for shift in shifts
    )

    xi = np.linspace(ramp.x_min, ramp.x_max, max(161, sample_count))
    open_x: list[float] = []
    open_r: list[float] = []
    spec = mechanism_map.geometry_spec
    for coordinate in xi:
        profile = ramp.evaluate(float(coordinate))
        open_x.append(
            spec.ramp_reference_axial_position
            + spec.ramp_axial_direction * float(coordinate)
        )
        open_r.append(spec.ramp_reference_radius + profile.value)

    return GeometryAnalysis(
        architecture=architecture,
        ramp_design=ramp_design,
        ramp=ramp,
        geometry_spec=mechanism_map.geometry_spec,
        points=points,
        requested_travel_m=requested_max,
        contact_valid_travel_m=valid_max,
        contact_range_complete=complete,
        ramp_surface_open_x_m=tuple(open_x),
        ramp_surface_open_r_m=tuple(open_r),
    )


def evaluate_response(
    analysis: GeometryAnalysis,
    operating: OperatingCondition,
) -> dict[str, list[float | bool | None]]:
    """Evaluate one operating condition over an already-solved geometry path."""
    if operating.tip_mass_per_flyweight_kg < 0.0:
        raise ValueError("tip mass per flyweight must be non-negative.")

    architecture = analysis.architecture
    mass = FlyweightMassGeometry.uniform_arm_with_end_mass(
        number_of_flyweights=architecture.number_of_flyweights,
        arm_length=architecture.arm_length_m,
        arm_mass_per_flyweight=architecture.arm_mass_per_flyweight_kg,
        end_mass_per_flyweight=operating.tip_mass_per_flyweight_kg,
        second_moment_z_per_flyweight=0.0,
    )
    unknowns = ClosureUnknowns.zeros()

    output: dict[str, list[float | bool | None]] = {
        "flyweight_centrifugal_force_N": [],
        "flyweight_axial_inertia_force_N": [],
        "flyweight_curvature_force_N": [],
        "flyweight_total_closing_force_N": [],
        "ramp_force_normal_N": [],
        "ramp_force_axial_N": [],
        "ramp_force_radial_N": [],
        "ramp_moment_about_anchor_Nm": [],
        "com_x_m": [],
        "com_r_m": [],
        "equivalent_centrifugal_force_N": [],
        "pivot_reaction_axial_N": [],
        "pivot_reaction_radial_N": [],
        "pivot_reaction_tangential_N": [],
        "pivot_reaction_resultant_N": [],
        "compressive_contact": [],
    }

    for point in analysis.points:
        if point.angle_rad > HALF_PI + 1.0e-10:
            _append_invalid_load_point(output)
            continue

        d_j_d_q = mass.shaft_inertia_angle_gradient(
            angle=point.angle_rad,
            pivot_radius=architecture.pivot_radius_m,
        )
        sample = FixedPivotFlyweightSample(
            angle=point.angle_rad,
            angle_gradient=point.angle_gradient_rad_per_m,
            angle_curvature=point.angle_curvature_rad_per_m2,
            shaft_inertia=mass.shaft_inertia(
                angle=point.angle_rad,
                pivot_radius=architecture.pivot_radius_m,
            ),
            shaft_inertia_gradient=(d_j_d_q * point.angle_gradient_rad_per_m),
            pivot_inertia=mass.pivot_inertia,
        )
        law = FixedPivotFlyweightForce(
            FixedPivotFlyweightForceSpec(mechanism_map=_SingleSampleMap(sample))
        )
        context = PulleyActuationContext(
            time=0.0,
            axial_position=point.shift_m,
            axial_speed=operating.shift_speed_m_s,
            shaft_speed=operating.shaft_speed_rad_s,
            shift_speed=operating.shift_speed_m_s,
            axial_acceleration=AffineClosureScalar.constant(
                operating.shift_acceleration_m_s2
            ),
        )
        contributions = {
            contribution.key: contribution.relation.evaluate(unknowns)
            for contribution in law.inspect(context)
        }
        total = law.evaluate(context).evaluate(unknowns)

        count = architecture.number_of_flyweights
        per_ramp_axial = total / count
        if abs(point.ramp_normal_x) <= 1.0e-10:
            normal_force = None
            per_ramp_radial = None
            moment = None
        else:
            normal_force = per_ramp_axial / point.ramp_normal_x
            per_ramp_radial = normal_force * point.ramp_normal_r
            anchor_x = (
                architecture.pivot_axial_position_m
                + analysis.ramp_design.anchor_axial_from_pivot_m
                + point.shift_m
            )
            anchor_r = (
                architecture.pivot_radius_m
                + analysis.ramp_design.anchor_radial_from_pivot_m
            )
            dx = point.contact_x_m - anchor_x
            dr = point.contact_r_m - anchor_r
            moment = dx * per_ramp_radial - dr * per_ramp_axial

        m = mass.mass_per_flyweight
        u_bar = mass.first_moment_u / m
        v_bar = mass.first_moment_v / m
        q = point.angle_rad
        x_rel = u_bar * cos(q) - v_bar * sin(q)
        r_rel = u_bar * sin(q) + v_bar * cos(q)
        com_x = architecture.pivot_axial_position_m + x_rel
        com_r = architecture.pivot_radius_m + r_rel

        q_dot = point.angle_gradient_rad_per_m * operating.shift_speed_m_s
        q_ddot = (
            point.angle_gradient_rad_per_m * operating.shift_acceleration_m_s2
            + point.angle_curvature_rad_per_m2 * operating.shift_speed_m_s**2
        )
        dx_dq = -r_rel
        d2x_dq2 = -x_rel
        dr_dq = x_rel
        d2r_dq2 = -r_rel
        com_x_accel = dx_dq * q_ddot + d2x_dq2 * q_dot**2
        com_r_dot = dr_dq * q_dot
        com_r_accel = (
            dr_dq * q_ddot
            + d2r_dq2 * q_dot**2
            - com_r * operating.shaft_speed_rad_s**2
        )
        com_theta_accel = 2.0 * com_r_dot * operating.shaft_speed_rad_s

        if per_ramp_radial is None:
            pivot_x = None
            pivot_r = None
            pivot_theta = None
            pivot_resultant = None
        else:
            pivot_x = m * com_x_accel + per_ramp_axial
            pivot_r = m * com_r_accel + per_ramp_radial
            pivot_theta = m * com_theta_accel
            pivot_resultant = sqrt(
                pivot_x**2 + pivot_r**2 + pivot_theta**2
            )

        equivalent_centrifugal = (
            m * operating.shaft_speed_rad_s**2 * com_r
        )

        output["flyweight_centrifugal_force_N"].append(
            float(contributions["fixed_pivot_flyweight_centrifugal"])
        )
        output["flyweight_axial_inertia_force_N"].append(
            float(contributions["fixed_pivot_flyweight_axial_inertia"])
        )
        output["flyweight_curvature_force_N"].append(
            float(contributions["fixed_pivot_flyweight_motion_ratio_curvature"])
        )
        output["flyweight_total_closing_force_N"].append(float(total))
        output["ramp_force_normal_N"].append(
            None if normal_force is None else float(normal_force)
        )
        output["ramp_force_axial_N"].append(float(per_ramp_axial))
        output["ramp_force_radial_N"].append(
            None if per_ramp_radial is None else float(per_ramp_radial)
        )
        output["ramp_moment_about_anchor_Nm"].append(
            None if moment is None else float(moment)
        )
        output["com_x_m"].append(float(com_x))
        output["com_r_m"].append(float(com_r))
        output["equivalent_centrifugal_force_N"].append(
            float(equivalent_centrifugal)
        )
        output["pivot_reaction_axial_N"].append(
            None if pivot_x is None else float(pivot_x)
        )
        output["pivot_reaction_radial_N"].append(
            None if pivot_r is None else float(pivot_r)
        )
        output["pivot_reaction_tangential_N"].append(
            None if pivot_theta is None else float(pivot_theta)
        )
        output["pivot_reaction_resultant_N"].append(
            None if pivot_resultant is None else float(pivot_resultant)
        )
        output["compressive_contact"].append(
            bool(normal_force is not None and normal_force >= 0.0)
        )

    return output


def _append_invalid_load_point(
    output: dict[str, list[float | bool | None]],
) -> None:
    for key, values in output.items():
        values.append(False if key == "compressive_contact" else None)


def _build_production_map(
    architecture: ArchitectureDesign,
    ramp_design: RampDesign,
    ramp: PiecewiseRamp,
    *,
    axial_position_max: float,
    compilation_points: int,
) -> PivotedRollerFollowerFlyweightMap:
    # Mass has no effect on q(x). Use the real arm mass and a harmless tiny end
    # mass if necessary so this production map can compile geometry once.
    arm_mass = architecture.arm_mass_per_flyweight_kg
    end_mass = 0.0 if arm_mass > 0.0 else 1.0e-9
    mass = FlyweightMassGeometry.uniform_arm_with_end_mass(
        number_of_flyweights=architecture.number_of_flyweights,
        arm_length=architecture.arm_length_m,
        arm_mass_per_flyweight=arm_mass,
        end_mass_per_flyweight=end_mass,
        second_moment_z_per_flyweight=0.0,
    )
    return PivotedRollerFollowerFlyweightMap(
        geometry_spec=_geometry_spec(
            architecture,
            ramp_design,
            ramp,
            axial_position_max=axial_position_max,
        ),
        mass_geometry=mass,
        compilation_points=compilation_points,
    )


def _geometry_spec(
    architecture: ArchitectureDesign,
    ramp_design: RampDesign,
    ramp: PiecewiseRamp,
    *,
    axial_position_max: float,
) -> PivotedRollerFollowerGeometrySpec:
    return PivotedRollerFollowerGeometrySpec(
        pivot_axial_position=architecture.pivot_axial_position_m,
        pivot_radius=architecture.pivot_radius_m,
        arm_length=architecture.arm_length_m,
        roller_radius=architecture.roller_radius_m,
        ramp_reference_axial_position=(
            architecture.pivot_axial_position_m
            + ramp_design.anchor_axial_from_pivot_m
        ),
        ramp_reference_radius=(
            architecture.pivot_radius_m
            + ramp_design.anchor_radial_from_pivot_m
        ),
        ramp_profile=ramp,
        ramp_axial_direction=architecture.ramp_axial_direction,
        axial_position_min=0.0,
        axial_position_max=axial_position_max,
        roller_side_sign=architecture.roller_side_sign,
        root_scan_points=513,
        validation_positions=129,
    )


def _geometry_point(
    mechanism_map: PivotedRollerFollowerFlyweightMap,
    ramp: PiecewiseRamp,
    shift_m: float,
) -> GeometryPoint:
    sample = mechanism_map.evaluate(shift_m)
    contact = mechanism_map.contact_at(shift_m)
    spec = mechanism_map.geometry_spec
    profile = ramp.evaluate(contact.contact_coordinate)
    contact_x = (
        spec.ramp_reference_axial_position
        + shift_m
        + spec.ramp_axial_direction * contact.contact_coordinate
    )
    contact_r = spec.ramp_reference_radius + profile.value

    dx = contact.roller_center_axial_position - contact_x
    dr = contact.roller_center_radius - contact_r
    length = hypot(dx, dr)
    if length <= 1.0e-14:
        raise RuntimeError("Roller/ramp contact normal is singular.")
    normal_on_ramp_x = -dx / length
    normal_on_ramp_r = -dr / length

    tangent_angle = degrees(
        atan2(abs(profile.first_derivative), 1.0)
    )
    return GeometryPoint(
        shift_m=shift_m,
        angle_rad=sample.angle,
        angle_gradient_rad_per_m=sample.angle_gradient,
        angle_curvature_rad_per_m2=sample.angle_curvature,
        contact_coordinate_m=contact.contact_coordinate,
        contact_x_m=contact_x,
        contact_r_m=contact_r,
        roller_center_x_m=contact.roller_center_axial_position,
        roller_center_r_m=contact.roller_center_radius,
        ramp_tangent_deg=tangent_angle,
        ramp_normal_x=normal_on_ramp_x,
        ramp_normal_r=normal_on_ramp_r,
    )


def _validate_architecture(architecture: ArchitectureDesign) -> None:
    positive = {
        "pivot_radius_m": architecture.pivot_radius_m,
        "arm_length_m": architecture.arm_length_m,
        "roller_radius_m": architecture.roller_radius_m,
        "required_travel_m": architecture.required_travel_m,
    }
    for name, value in positive.items():
        if value <= 0.0:
            raise ValueError(f"{name} must be positive.")
    if architecture.number_of_flyweights <= 0:
        raise ValueError("number_of_flyweights must be positive.")
    if architecture.arm_mass_per_flyweight_kg < 0.0:
        raise ValueError("arm_mass_per_flyweight_kg must be non-negative.")
    if architecture.ramp_axial_direction not in (-1, 1):
        raise ValueError("ramp_axial_direction must be -1 or +1.")
    if architecture.roller_side_sign not in (-1, 1):
        raise ValueError("roller_side_sign must be -1 or +1.")


def _validate_ramp_design(design: RampDesign) -> None:
    if design.total_length_m <= 0.0:
        raise ValueError("Ramp length must be positive.")
    if not 0.0 < design.start_angle_deg < 90.0:
        raise ValueError("start_angle_deg must lie strictly between 0 and 90 degrees.")
    if design.kind == "constant":
        return
    if design.start_angle_deg <= design.end_angle_deg:
        raise ValueError(
            "Progressive ramp requires start_angle_deg > end_angle_deg; "
            "use the constant profile when the tangents are equal."
        )
    if not 0.0 < design.end_angle_deg < 90.0:
        raise ValueError("end_angle_deg must lie strictly between 0 and 90 degrees.")
    if design.linear_length_m <= 0.0:
        raise ValueError("linear_length_m must be positive for a progressive ramp.")
    if design.blend_length_m <= 0.0:
        raise ValueError("blend_length_m must be positive for a progressive ramp.")
    if design.circular_length_m <= 0.0:
        raise ValueError("circular_length_m must be positive for a progressive ramp.")
