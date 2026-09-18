"""Interactive FEA load inspector for the CINDER fixed-pivot primary flyweights.

Run from ``cvtModel``::

    PYTHONPATH=src python tools/primary_fea_load_inspector.py

The tool deliberately reuses CINDER's production fixed-pivot contact geometry
and force law.  It does not replace the CVT model with a hand-derived tuning
formula.  The only additional step is a load transformation for structural
work: the generalized primary closing force is resolved through the exact
finite-roller contact normal to obtain the force applied to each physical ramp.

The current CINDER v1 reference hardware is the default. Alternate ramp
geometries are exploratory: if their selected contact branch does not survive
the full 0.75-in reference closure, the inspector automatically limits the
shift slider/sweep to the continuous contact-valid range instead of rejecting
the whole design. Reference hardware details:
- three identical flyweights;
- measured arm/body mass from the reference fixed-pivot configuration;
- current finite roller radius, arm length, Point-A offsets and pivot radius;
- current piecewise 35 deg -> 20 deg ramp.

Interactive controls let the user change:
- ramp family (locked reference, constant angle, or progressive start-to-end);
- ramp tangent angles;
- shaft-to-pivot radius;
- concentrated tip-hardware mass per flyweight;
- primary RPM;
- local primary closure;
- local closure speed and acceleration (optional transient corrections).

FEA-oriented outputs include:
- generalized flyweight closing force and its CINDER term breakdown;
- per-ramp normal contact force and its axial/radial components;
- contact location and a reduced moment about Point A;
- equivalent flyweight centrifugal body-force resultant at the COM;
- pivot-pin reaction in axial/radial/circumferential components, assuming
  constant shaft RPM over the instantaneous sample (shaft angular acceleration
  is zero).

Sign convention
---------------
``+x`` is local primary closing. ``+r`` is radially outward. ``+theta`` is the
positive shaft-rotation direction.  The reported ramp force is the force ON THE
RAMP/CARRIER from one roller.  The force on the roller is equal and opposite.
The reported pivot reaction is the force ON THE FLYWEIGHT from the pivot; an FEA
load applied to the pivot carrier is equal and opposite.

Scope
-----
The structural loads inherit the production CINDER fixed-pivot assumptions:
frictionless roller/ramp contact, rigid arm geometry, planar roller/ramp contact,
identical circumferentially symmetric flyweights, no roller spin inertia,
bearing drag, local compliance, backlash or structural flex.  Gravity is omitted
from the pivot-reaction reconstruction.  For nonzero closure speed the pivot
reaction includes the cylindrical Coriolis term, but assumes shaft angular
acceleration is zero.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from math import atan2, cos, degrees, hypot, isfinite, pi, sin, sqrt
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle
from matplotlib.widgets import Button, RadioButtons, Slider

from cinder.model.cvt.actuation import (
    FixedPivotFlyweightForce,
    FixedPivotFlyweightForceSpec,
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


INCH_TO_METRE = 0.0254
MILLIMETRE = 1.0e-3
RPM_TO_RAD_PER_SECOND = 2.0 * pi / 60.0
RAD_PER_SECOND_TO_RPM = 60.0 / (2.0 * pi)
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "examples" / "baja_primary_fixed_pivot_geometry.json"
DEFAULT_OUTPUT_DIR = ROOT / "outputs" / "primary_fea_load_inspector"

RAMP_REFERENCE = "Reference 35→20 (locked)"
RAMP_LINEAR = "Constant angle"
RAMP_CUSTOM = "Progressive start→end"
RAMP_MODES = (RAMP_REFERENCE, RAMP_LINEAR, RAMP_CUSTOM)


@dataclass(frozen=True, slots=True)
class ReferenceHardware:
    name: str
    pivot_radius: float
    arm_length: float
    roller_radius: float
    point_a_axial_offset: float
    point_a_radial_offset: float
    number_of_flyweights: int
    arm_mass_per_flyweight: float
    tip_mass_per_flyweight: float
    axial_position_min: float
    axial_position_max: float
    ramp_payload: dict[str, Any]
    ramp_axial_direction: int
    roller_side_sign: int

    @property
    def total_ramp_length(self) -> float:
        return sum(_segment_length(item) for item in self.ramp_payload["segments"])


@dataclass(frozen=True, slots=True)
class GeometryControls:
    ramp_mode: str
    start_angle_degrees: float
    end_angle_degrees: float
    pivot_radius: float
    tip_mass_per_flyweight: float


@dataclass(frozen=True, slots=True)
class OperatingPoint:
    rpm: float
    axial_position: float
    axial_speed: float
    axial_acceleration: float


@dataclass(frozen=True, slots=True)
class MechanismBundle:
    controls: GeometryControls
    ramp: PiecewiseRamp
    mechanism_map: PivotedRollerFollowerFlyweightMap
    force_law: FixedPivotFlyweightForce
    requested_axial_position_max: float
    contact_valid_axial_position_max: float
    contact_range_truncated: bool


@dataclass(frozen=True, slots=True)
class FEAResult:
    # Operating point / geometry.
    rpm: float
    omega_rad_s: float
    axial_position_m: float
    axial_speed_m_s: float
    axial_acceleration_m_s2: float
    q_rad: float
    q_dot_rad_s: float
    q_ddot_rad_s2: float
    contact_coordinate_m: float
    contact_x_m: float
    contact_r_m: float
    roller_center_x_m: float
    roller_center_r_m: float
    ramp_tangent_angle_deg: float
    ramp_normal_x: float
    ramp_normal_r: float
    # CINDER generalized force terms for the complete flyweight set.
    flyweight_centrifugal_force_N: float
    flyweight_axial_inertia_force_N: float
    flyweight_curvature_force_N: float
    flyweight_total_closing_force_N: float
    # FEA contact load on one physical ramp.
    ramp_force_normal_N: float
    ramp_force_axial_N: float
    ramp_force_radial_N: float
    ramp_moment_about_point_a_Nm: float
    # Equivalent per-flyweight body load / pivot reaction.
    com_x_m: float
    com_r_m: float
    equivalent_centrifugal_force_N: float
    pivot_reaction_axial_N: float
    pivot_reaction_radial_N: float
    pivot_reaction_tangential_N: float
    pivot_reaction_resultant_N: float
    compressive_contact: bool

    def as_dict(self) -> dict[str, float | bool]:
        return {
            field: getattr(self, field)
            for field in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class PreparedGeometry:
    axial_position_m: float
    q_rad: float
    angle_gradient_rad_per_m: float
    angle_curvature_rad_per_m2: float
    contact_coordinate_m: float
    contact_x_m: float
    contact_r_m: float
    roller_center_x_m: float
    roller_center_r_m: float
    ramp_tangent_angle_deg: float
    ramp_normal_x: float
    ramp_normal_r: float
    com_x_m: float
    com_r_m: float
    x_rel_com_m: float
    r_rel_com_m: float


@dataclass(slots=True)
class InspectorState:
    hardware: ReferenceHardware
    bundle: MechanismBundle
    operating: OperatingPoint
    output_dir: Path
    shift_geometry_cache: list[PreparedGeometry] | None = None
    current_geometry_cache: PreparedGeometry | None = None


# ---------------------------------------------------------------------------
# Reference hardware / model construction
# ---------------------------------------------------------------------------


def _inch(value: Any) -> float:
    return float(value) * INCH_TO_METRE


def _mm(value: Any) -> float:
    return float(value) * MILLIMETRE


def _segment_length(segment: dict[str, Any]) -> float:
    if "axial_span_mm" in segment:
        return _mm(segment["axial_span_mm"])
    if "axial_span_in" in segment:
        return _inch(segment["axial_span_in"])
    if "length_m" in segment:
        return float(segment["length_m"])
    raise KeyError("Ramp segment must define axial_span_mm, axial_span_in, or length_m.")


def load_reference_hardware(path: Path) -> ReferenceHardware:
    payload = json.loads(path.read_text(encoding="utf-8"))
    measurement = payload["measurements"]
    mass = payload["mass_model"]
    ramp = payload["ramp"]
    travel = payload["local_closure_travel"]
    return ReferenceHardware(
        name=str(payload["name"]),
        pivot_radius=_inch(measurement["pivot_radius_in"]),
        arm_length=_inch(measurement["pivot_to_roller_center_in"]),
        roller_radius=_mm(measurement["roller_radius_mm"]),
        point_a_axial_offset=_inch(measurement["point_a_from_pivot_axial_in"]),
        point_a_radial_offset=_inch(measurement["point_a_from_pivot_radial_in"]),
        number_of_flyweights=int(measurement["number_of_flyweights"]),
        arm_mass_per_flyweight=float(mass["arm_mass_per_flyweight_g"]) / 1000.0,
        tip_mass_per_flyweight=float(mass["tip_hardware_mass_per_flyweight_g"]) / 1000.0,
        axial_position_min=_inch(travel["minimum_in"]),
        axial_position_max=_inch(travel["maximum_in"]),
        ramp_payload=dict(ramp),
        ramp_axial_direction=int(ramp["ramp_axial_direction"]),
        roller_side_sign=int(ramp["roller_side_sign"]),
    )


def _build_reference_ramp(payload: dict[str, Any]) -> PiecewiseRamp:
    specs = list(payload["segments"])
    built: list[Any | None] = [None] * len(specs)
    for index, segment in enumerate(specs):
        kind = segment["kind"]
        if kind == "auto_c3_transition":
            continue
        length = _segment_length(segment)
        if kind == "linear_segment":
            built[index] = LinearSegment(
                length=length,
                angle_degrees=float(segment["angle_degrees"]),
            )
        elif kind == "circular_segment":
            built[index] = CircularSegment(
                length=length,
                angle_start_degrees=float(segment["angle_start_degrees"]),
                angle_end_degrees=float(segment["angle_end_degrees"]),
                quadrant=int(segment["quadrant"]),
            )
        else:
            raise ValueError(f"Unsupported ramp segment kind: {kind}")

    for index, segment in enumerate(specs):
        if segment["kind"] != "auto_c3_transition":
            continue
        if index == 0 or index == len(specs) - 1:
            raise ValueError("auto_c3_transition must lie between physical segments.")
        left = built[index - 1]
        right = built[index + 1]
        if left is None or right is None:
            raise ValueError("Adjacent automatic C3 transitions are not supported.")
        built[index] = C3TransitionSegment.between_segments(
            left=left,
            right=right,
            length=_segment_length(segment),
        )

    if any(item is None for item in built):
        raise RuntimeError("Could not resolve all reference ramp segments.")
    ramp = PiecewiseRamp(tuple(built))
    ramp.require_continuity(order=3)
    return ramp


def _reference_angles(hardware: ReferenceHardware) -> tuple[float, float]:
    segments = hardware.ramp_payload["segments"]
    linear = next(item for item in segments if item["kind"] == "linear_segment")
    circular = next(item for item in segments if item["kind"] == "circular_segment")
    return float(linear["angle_degrees"]), float(circular["angle_end_degrees"])


def _normalized_controls(
    hardware: ReferenceHardware, controls: GeometryControls
) -> GeometryControls:
    """Make the UI values describe the geometry that is actually built."""
    if controls.ramp_mode == RAMP_REFERENCE:
        start, end = _reference_angles(hardware)
        return GeometryControls(
            ramp_mode=controls.ramp_mode,
            start_angle_degrees=start,
            end_angle_degrees=end,
            pivot_radius=controls.pivot_radius,
            tip_mass_per_flyweight=controls.tip_mass_per_flyweight,
        )
    if controls.ramp_mode == RAMP_LINEAR:
        return GeometryControls(
            ramp_mode=controls.ramp_mode,
            start_angle_degrees=controls.start_angle_degrees,
            end_angle_degrees=controls.start_angle_degrees,
            pivot_radius=controls.pivot_radius,
            tip_mass_per_flyweight=controls.tip_mass_per_flyweight,
        )
    return controls


def build_ramp(
    hardware: ReferenceHardware,
    controls: GeometryControls,
) -> PiecewiseRamp:
    if controls.ramp_mode == RAMP_REFERENCE:
        return _build_reference_ramp(hardware.ramp_payload)

    if controls.ramp_mode == RAMP_LINEAR:
        return PiecewiseRamp(
            (
                LinearSegment(
                    length=hardware.total_ramp_length,
                    angle_degrees=controls.start_angle_degrees,
                ),
            )
        )

    if controls.ramp_mode == RAMP_CUSTOM:
        if controls.start_angle_degrees < controls.end_angle_degrees:
            raise ValueError(
                "Progressive start→end mode is the hard-to-soft Q2 ramp: "
                "start angle must be greater than or equal to end angle."
            )
        # Preserve the reference 5 mm + 3 mm C3 + 30 mm topology.  The first
        # 5 mm is exactly the requested start tangent; the circular tail ends
        # at exactly the requested end tangent.
        specs = hardware.ramp_payload["segments"]
        linear_length = _segment_length(specs[0])
        blend_length = _segment_length(specs[1])
        circular_length = _segment_length(specs[2])
        linear = LinearSegment(
            length=linear_length,
            angle_degrees=controls.start_angle_degrees,
        )
        circular = CircularSegment(
            length=circular_length,
            angle_start_degrees=controls.start_angle_degrees,
            angle_end_degrees=controls.end_angle_degrees,
            quadrant=2,
        )
        blend = C3TransitionSegment.between_segments(
            left=linear,
            right=circular,
            length=blend_length,
        )
        ramp = PiecewiseRamp((linear, blend, circular))
        ramp.require_continuity(order=3)
        return ramp

    raise ValueError(f"Unsupported ramp mode: {controls.ramp_mode}")


def _geometry_spec(
    hardware: ReferenceHardware,
    controls: GeometryControls,
    ramp: PiecewiseRamp,
    *,
    axial_position_max: float,
) -> PivotedRollerFollowerGeometrySpec:
    return PivotedRollerFollowerGeometrySpec(
        pivot_axial_position=0.0,
        pivot_radius=controls.pivot_radius,
        arm_length=hardware.arm_length,
        roller_radius=hardware.roller_radius,
        # Point A moves radially with the pivot-radius control. That preserves
        # the measured local P->A geometry while changing the absolute radius
        # that drives centrifugal loading.
        ramp_reference_axial_position=hardware.point_a_axial_offset,
        ramp_reference_radius=(
            controls.pivot_radius + hardware.point_a_radial_offset
        ),
        ramp_profile=ramp,
        ramp_axial_direction=hardware.ramp_axial_direction,
        axial_position_min=hardware.axial_position_min,
        axial_position_max=axial_position_max,
        roller_side_sign=hardware.roller_side_sign,
        root_scan_points=513,
        validation_positions=129,
    )


def _continuous_contact_limit(
    hardware: ReferenceHardware,
    controls: GeometryControls,
    ramp: PiecewiseRamp,
    *,
    samples: int = 2049,
) -> float:
    """Return the end of the continuous branch reachable from fully open.

    The production runtime map quite correctly requires contact over its whole
    declared interval.  For this design/FEA explorer we first discover the
    interval instead, so an aggressive ramp can still be inspected up to the
    point where its physical continuous branch is lost.
    """
    requested_max = hardware.axial_position_max
    provisional = PivotedRollerFollowerGeometry(
        _geometry_spec(
            hardware, controls, ramp, axial_position_max=requested_max
        )
    )
    positions = np.linspace(hardware.axial_position_min, requested_max, samples)
    trace = provisional.trace_contact_branch(positions, require_complete=False)
    if len(trace) < 2:
        raise ValueError(
            "No usable continuous roller/ramp contact branch exists from the "
            "fully-open position for this geometry."
        )
    if len(trace) == len(positions):
        return requested_max

    # Leave one probe interval of margin before the first failed point. This
    # prevents the stricter production-map audit from being asked to compile
    # exactly on a contact-loss boundary.
    last_valid_index = len(trace) - 1
    safe_index = max(1, last_valid_index - 1)
    return float(positions[safe_index])


def build_bundle(
    hardware: ReferenceHardware,
    controls: GeometryControls,
) -> MechanismBundle:
    controls = _normalized_controls(hardware, controls)
    if controls.pivot_radius <= 0.0:
        raise ValueError("Pivot radius must be positive.")
    if controls.tip_mass_per_flyweight < 0.0:
        raise ValueError("Tip mass per flyweight must be non-negative.")

    ramp = build_ramp(hardware, controls)
    requested_max = hardware.axial_position_max
    if controls.ramp_mode == RAMP_REFERENCE:
        # The reference mechanism is a runtime-valid production geometry and
        # should continue to prove that full interval.
        valid_max = requested_max
    else:
        valid_max = _continuous_contact_limit(hardware, controls, ramp)

    geometry = _geometry_spec(
        hardware, controls, ramp, axial_position_max=valid_max
    )
    mass = FlyweightMassGeometry.uniform_arm_with_end_mass(
        number_of_flyweights=hardware.number_of_flyweights,
        arm_length=hardware.arm_length,
        arm_mass_per_flyweight=hardware.arm_mass_per_flyweight,
        end_mass_per_flyweight=controls.tip_mass_per_flyweight,
        second_moment_z_per_flyweight=0.0,
    )
    mechanism_map = PivotedRollerFollowerFlyweightMap(
        geometry_spec=geometry,
        mass_geometry=mass,
        compilation_points=257,
    )
    force_law = FixedPivotFlyweightForce(
        FixedPivotFlyweightForceSpec(mechanism_map=mechanism_map)
    )
    return MechanismBundle(
        controls=controls,
        ramp=ramp,
        mechanism_map=mechanism_map,
        force_law=force_law,
        requested_axial_position_max=requested_max,
        contact_valid_axial_position_max=valid_max,
        contact_range_truncated=(valid_max < requested_max - 1.0e-9),
    )


# ---------------------------------------------------------------------------
# Force resolution
# ---------------------------------------------------------------------------


def _ramp_surface_point(
    bundle: MechanismBundle,
    *,
    axial_position: float,
    contact_coordinate: float,
) -> tuple[float, float]:
    spec = bundle.mechanism_map.geometry_spec
    profile = spec.ramp_profile.evaluate(contact_coordinate)
    return (
        spec.ramp_reference_axial_position
        + axial_position
        + spec.ramp_axial_direction * contact_coordinate,
        spec.ramp_reference_radius + profile.value,
    )


def _force_terms(
    bundle: MechanismBundle,
    operating: OperatingPoint,
) -> dict[str, float]:
    context = PulleyActuationContext(
        time=0.0,
        axial_position=operating.axial_position,
        axial_speed=operating.axial_speed,
        shaft_speed=operating.rpm * RPM_TO_RAD_PER_SECOND,
        shift_speed=operating.axial_speed,
        axial_acceleration=AffineClosureScalar.constant(operating.axial_acceleration),
    )
    unknowns = ClosureUnknowns.zeros()
    values: dict[str, float] = {}
    for contribution in bundle.force_law.inspect(context):
        values[contribution.key] = contribution.relation.evaluate(unknowns)
    values["total"] = bundle.force_law.evaluate(context).evaluate(unknowns)
    return values


def prepare_geometry(
    state: InspectorState,
    axial_position: float,
) -> PreparedGeometry:
    bundle = state.bundle
    x = float(np.clip(
        axial_position,
        bundle.mechanism_map.axial_position_min,
        bundle.mechanism_map.axial_position_max,
    ))
    sample = bundle.mechanism_map.evaluate(x)
    contact = bundle.mechanism_map.contact_at(x)
    contact_x, contact_r = _ramp_surface_point(
        bundle,
        axial_position=x,
        contact_coordinate=contact.contact_coordinate,
    )

    # Exact finite-roller contact normal from the physical contact point to the
    # roller centre. This remains valid for both smooth and corner contacts.
    center_dx = contact.roller_center_axial_position - contact_x
    center_dr = contact.roller_center_radius - contact_r
    normal_length = hypot(center_dx, center_dr)
    if normal_length <= 1.0e-14:
        raise RuntimeError("Roller/ramp contact normal is singular.")
    normal_on_roller_x = center_dx / normal_length
    normal_on_roller_r = center_dr / normal_length
    normal_on_ramp_x = -normal_on_roller_x
    normal_on_ramp_r = -normal_on_roller_r

    profile_sample = bundle.ramp.evaluate(contact.contact_coordinate)
    tangent_x = float(bundle.mechanism_map.geometry_spec.ramp_axial_direction)
    tangent_r = profile_sample.first_derivative
    tangent_angle = degrees(atan2(abs(tangent_r), abs(tangent_x)))

    mass = bundle.mechanism_map.mass_geometry
    m = mass.mass_per_flyweight
    u_bar = mass.first_moment_u / m
    v_bar = mass.first_moment_v / m
    q = sample.angle
    x_rel = u_bar * cos(q) - v_bar * sin(q)
    r_rel = u_bar * sin(q) + v_bar * cos(q)
    com_x = bundle.mechanism_map.geometry_spec.pivot_axial_position + x_rel
    com_r = bundle.mechanism_map.geometry_spec.pivot_radius + r_rel

    return PreparedGeometry(
        axial_position_m=x,
        q_rad=q,
        angle_gradient_rad_per_m=sample.angle_gradient,
        angle_curvature_rad_per_m2=sample.angle_curvature,
        contact_coordinate_m=contact.contact_coordinate,
        contact_x_m=contact_x,
        contact_r_m=contact_r,
        roller_center_x_m=contact.roller_center_axial_position,
        roller_center_r_m=contact.roller_center_radius,
        ramp_tangent_angle_deg=tangent_angle,
        ramp_normal_x=normal_on_ramp_x,
        ramp_normal_r=normal_on_ramp_r,
        com_x_m=com_x,
        com_r_m=com_r,
        x_rel_com_m=x_rel,
        r_rel_com_m=r_rel,
    )


def _current_prepared_geometry(state: InspectorState) -> PreparedGeometry:
    x = float(np.clip(
        state.operating.axial_position,
        state.bundle.mechanism_map.axial_position_min,
        state.bundle.mechanism_map.axial_position_max,
    ))
    cached = state.current_geometry_cache
    if cached is None or abs(cached.axial_position_m - x) > 1.0e-12:
        cached = prepare_geometry(state, x)
        state.current_geometry_cache = cached
    return cached


def _resolve_fea_result(
    state: InspectorState,
    point: OperatingPoint,
    prepared: PreparedGeometry,
) -> FEAResult:
    bundle = state.bundle
    hardware = state.hardware
    x = prepared.axial_position_m
    point = OperatingPoint(
        rpm=point.rpm,
        axial_position=x,
        axial_speed=point.axial_speed,
        axial_acceleration=point.axial_acceleration,
    )

    force_terms = _force_terms(bundle, point)
    centrifugal = force_terms["fixed_pivot_flyweight_centrifugal"]
    axial_inertia = force_terms["fixed_pivot_flyweight_axial_inertia"]
    curvature = force_terms["fixed_pivot_flyweight_motion_ratio_curvature"]
    total = force_terms["total"]

    count = hardware.number_of_flyweights
    per_ramp_axial = total / count
    if abs(prepared.ramp_normal_x) <= 1.0e-10:
        raise RuntimeError(
            "Ramp normal has essentially zero axial component; finite axial "
            "flyweight force would require an unbounded contact normal."
        )
    normal_force = per_ramp_axial / prepared.ramp_normal_x
    per_ramp_radial = normal_force * prepared.ramp_normal_r

    point_a_x = bundle.mechanism_map.geometry_spec.ramp_reference_axial_position + x
    point_a_r = bundle.mechanism_map.geometry_spec.ramp_reference_radius
    dx_a = prepared.contact_x_m - point_a_x
    dr_a = prepared.contact_r_m - point_a_r
    moment_about_a = dx_a * per_ramp_radial - dr_a * per_ramp_axial

    mass = bundle.mechanism_map.mass_geometry
    m = mass.mass_per_flyweight
    q_dot = prepared.angle_gradient_rad_per_m * point.axial_speed
    q_ddot = (
        prepared.angle_gradient_rad_per_m * point.axial_acceleration
        + prepared.angle_curvature_rad_per_m2 * point.axial_speed**2
    )
    omega = point.rpm * RPM_TO_RAD_PER_SECOND

    # Cylindrical COM acceleration for constant shaft omega (alpha = 0).
    dx_dq = -prepared.r_rel_com_m
    d2x_dq2 = -prepared.x_rel_com_m
    dr_dq = prepared.x_rel_com_m
    d2r_dq2 = -prepared.r_rel_com_m
    com_x_accel = dx_dq * q_ddot + d2x_dq2 * q_dot**2
    com_r_dot = dr_dq * q_dot
    com_r_accel = (
        dr_dq * q_ddot
        + d2r_dq2 * q_dot**2
        - prepared.com_r_m * omega**2
    )
    com_theta_accel = 2.0 * com_r_dot * omega

    # Force on flyweight from the ramp is equal/opposite the reported ramp load.
    # R_pivot + F_contact_on_flyweight = m*a => R_pivot = m*a + F_on_ramp.
    pivot_x = m * com_x_accel + per_ramp_axial
    pivot_r = m * com_r_accel + per_ramp_radial
    pivot_theta = m * com_theta_accel
    pivot_resultant = sqrt(pivot_x**2 + pivot_r**2 + pivot_theta**2)
    equivalent_centrifugal = m * omega**2 * prepared.com_r_m

    return FEAResult(
        rpm=point.rpm,
        omega_rad_s=omega,
        axial_position_m=x,
        axial_speed_m_s=point.axial_speed,
        axial_acceleration_m_s2=point.axial_acceleration,
        q_rad=prepared.q_rad,
        q_dot_rad_s=q_dot,
        q_ddot_rad_s2=q_ddot,
        contact_coordinate_m=prepared.contact_coordinate_m,
        contact_x_m=prepared.contact_x_m,
        contact_r_m=prepared.contact_r_m,
        roller_center_x_m=prepared.roller_center_x_m,
        roller_center_r_m=prepared.roller_center_r_m,
        ramp_tangent_angle_deg=prepared.ramp_tangent_angle_deg,
        ramp_normal_x=prepared.ramp_normal_x,
        ramp_normal_r=prepared.ramp_normal_r,
        flyweight_centrifugal_force_N=centrifugal,
        flyweight_axial_inertia_force_N=axial_inertia,
        flyweight_curvature_force_N=curvature,
        flyweight_total_closing_force_N=total,
        ramp_force_normal_N=normal_force,
        ramp_force_axial_N=per_ramp_axial,
        ramp_force_radial_N=per_ramp_radial,
        ramp_moment_about_point_a_Nm=moment_about_a,
        com_x_m=prepared.com_x_m,
        com_r_m=prepared.com_r_m,
        equivalent_centrifugal_force_N=equivalent_centrifugal,
        pivot_reaction_axial_N=pivot_x,
        pivot_reaction_radial_N=pivot_r,
        pivot_reaction_tangential_N=pivot_theta,
        pivot_reaction_resultant_N=pivot_resultant,
        compressive_contact=(normal_force >= 0.0),
    )


def evaluate_fea_loads(
    state: InspectorState,
    operating: OperatingPoint | None = None,
) -> FEAResult:
    point = state.operating if operating is None else operating
    if operating is None:
        prepared = _current_prepared_geometry(state)
    else:
        prepared = prepare_geometry(state, point.axial_position)
    return _resolve_fea_result(state, point, prepared)


# ---------------------------------------------------------------------------
# Sampling / export
# ---------------------------------------------------------------------------


def sample_shift_sweep(
    state: InspectorState,
    *,
    samples: int = 81,
) -> list[FEAResult]:
    if state.shift_geometry_cache is None or len(state.shift_geometry_cache) != samples:
        xs = np.linspace(
            state.bundle.mechanism_map.axial_position_min,
            state.bundle.mechanism_map.axial_position_max,
            samples,
        )
        state.shift_geometry_cache = [prepare_geometry(state, float(x)) for x in xs]

    results: list[FEAResult] = []
    for prepared in state.shift_geometry_cache:
        point = OperatingPoint(
            rpm=state.operating.rpm,
            axial_position=prepared.axial_position_m,
            axial_speed=state.operating.axial_speed,
            axial_acceleration=state.operating.axial_acceleration,
        )
        results.append(_resolve_fea_result(state, point, prepared))
    return results


def sample_rpm_sweep(
    state: InspectorState,
    *,
    samples: int = 121,
    rpm_max: float = 6000.0,
) -> list[FEAResult]:
    prepared = _current_prepared_geometry(state)
    rpms = np.linspace(0.0, rpm_max, samples)
    return [
        _resolve_fea_result(
            state,
            OperatingPoint(
                rpm=float(rpm),
                axial_position=prepared.axial_position_m,
                axial_speed=state.operating.axial_speed,
                axial_acceleration=state.operating.axial_acceleration,
            ),
            prepared,
        )
        for rpm in rpms
    ]


def _write_results(path: Path, rows: list[FEAResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].as_dict().keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.as_dict())


def export_current_state(
    *,
    state: InspectorState,
    figure,
    shift_rows: list[FEAResult] | None = None,
    rpm_rows: list[FEAResult] | None = None,
) -> None:
    output = state.output_dir
    output.mkdir(parents=True, exist_ok=True)
    current = evaluate_fea_loads(state)
    shift = sample_shift_sweep(state) if shift_rows is None else shift_rows
    rpm = sample_rpm_sweep(state) if rpm_rows is None else rpm_rows
    _write_results(output / "current_loads.csv", [current])
    _write_results(output / "shift_sweep.csv", shift)
    _write_results(output / "rpm_sweep.csv", rpm)
    figure.savefig(output / "primary_fea_load_inspector.png", dpi=180, bbox_inches="tight")

    metadata = {
        "reference_hardware": state.hardware.name,
        "ramp_mode": state.bundle.controls.ramp_mode,
        "start_angle_degrees": state.bundle.controls.start_angle_degrees,
        "end_angle_degrees": state.bundle.controls.end_angle_degrees,
        "pivot_radius_in": state.bundle.controls.pivot_radius / INCH_TO_METRE,
        "tip_mass_per_flyweight_g": (
            state.bundle.controls.tip_mass_per_flyweight * 1000.0
        ),
        "number_of_flyweights": state.hardware.number_of_flyweights,
        "contact_valid_axial_position_max_mm": (
            state.bundle.contact_valid_axial_position_max / MILLIMETRE
        ),
        "reference_axial_position_max_mm": (
            state.bundle.requested_axial_position_max / MILLIMETRE
        ),
        "contact_range_truncated": state.bundle.contact_range_truncated,
        "assumptions": [
            "frictionless finite-radius roller/ramp contact",
            "reported ramp load is force on one ramp carrier",
            "pivot reaction assumes shaft angular acceleration = 0",
            "gravity omitted from pivot-reaction reconstruction",
        ],
    }
    (output / "metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )
    print(f"Exported FEA load inspector outputs to: {output.resolve()}")


# ---------------------------------------------------------------------------
# Plotting helpers
# ---------------------------------------------------------------------------


def _scaled_arrow(
    axis,
    *,
    start_x_mm: float,
    start_r_mm: float,
    force_x: float,
    force_r: float,
    scale_mm: float,
    label: str,
    text_offset: tuple[float, float] = (5.0, 5.0),
) -> None:
    magnitude = hypot(force_x, force_r)
    if not isfinite(magnitude) or magnitude <= 1.0e-12:
        return
    dx = scale_mm * force_x / magnitude
    dr = scale_mm * force_r / magnitude
    axis.annotate(
        "",
        xy=(start_x_mm + dx, start_r_mm + dr),
        xytext=(start_x_mm, start_r_mm),
        arrowprops={"arrowstyle": "->", "linewidth": 2.0},
    )
    axis.annotate(
        f"{label}\n{magnitude:.0f} N",
        (start_x_mm + dx, start_r_mm + dr),
        xytext=text_offset,
        textcoords="offset points",
        fontsize=8,
    )


def _draw_mechanism(axis, state: InspectorState, result: FEAResult) -> None:
    axis.clear()
    bundle = state.bundle
    spec = bundle.mechanism_map.geometry_spec
    x = result.axial_position_m
    xi_values = np.linspace(bundle.ramp.x_min, bundle.ramp.x_max, 301)
    ramp_x: list[float] = []
    ramp_r: list[float] = []
    for xi in xi_values:
        rx, rr = _ramp_surface_point(bundle, axial_position=x, contact_coordinate=float(xi))
        ramp_x.append(rx / MILLIMETRE)
        ramp_r.append(rr / MILLIMETRE)
    axis.plot(ramp_x, ramp_r, linewidth=2.2, label="ramp")

    px = spec.pivot_axial_position / MILLIMETRE
    pr = spec.pivot_radius / MILLIMETRE
    cx = result.roller_center_x_m / MILLIMETRE
    cr = result.roller_center_r_m / MILLIMETRE
    contact_x = result.contact_x_m / MILLIMETRE
    contact_r = result.contact_r_m / MILLIMETRE
    com_x = result.com_x_m / MILLIMETRE
    com_r = result.com_r_m / MILLIMETRE

    axis.plot([px, cx], [pr, cr], linewidth=2.5)
    axis.add_patch(
        Circle(
            (cx, cr),
            spec.roller_radius / MILLIMETRE,
            fill=False,
            linewidth=2.0,
        )
    )
    axis.plot([px], [pr], marker="o", linestyle="none")
    axis.annotate("P pivot", (px, pr), xytext=(5, 5), textcoords="offset points")
    axis.plot([contact_x], [contact_r], marker="x", linestyle="none")
    axis.annotate("C contact", (contact_x, contact_r), xytext=(5, -13), textcoords="offset points")
    axis.plot([com_x], [com_r], marker="s", linestyle="none", markersize=5)
    axis.annotate("COM", (com_x, com_r), xytext=(5, 5), textcoords="offset points", fontsize=8)

    point_a_x = (spec.ramp_reference_axial_position + x) / MILLIMETRE
    point_a_r = spec.ramp_reference_radius / MILLIMETRE
    axis.plot([point_a_x], [point_a_r], marker="D", linestyle="none", markersize=4)
    axis.annotate("A ramp start", (point_a_x, point_a_r), xytext=(5, 5), textcoords="offset points", fontsize=8)

    arm_circle = Circle(
        (px, pr),
        spec.arm_length / MILLIMETRE,
        fill=False,
        linestyle=":",
        linewidth=1.0,
        alpha=0.45,
    )
    axis.add_patch(arm_circle)

    # Force-on-ramp arrow at contact.
    arrow_scale = max(8.0, 0.28 * spec.arm_length / MILLIMETRE)
    _scaled_arrow(
        axis,
        start_x_mm=contact_x,
        start_r_mm=contact_r,
        force_x=result.ramp_force_axial_N,
        force_r=result.ramp_force_radial_N,
        scale_mm=arrow_scale,
        label="load on ramp",
    )
    # Pivot carrier sees the opposite of the reported pivot-on-flyweight reaction.
    _scaled_arrow(
        axis,
        start_x_mm=px,
        start_r_mm=pr,
        force_x=-result.pivot_reaction_axial_N,
        force_r=-result.pivot_reaction_radial_N,
        scale_mm=0.8 * arrow_scale,
        label="load on pivot carrier",
        text_offset=(5.0, -18.0),
    )
    _scaled_arrow(
        axis,
        start_x_mm=com_x,
        start_r_mm=com_r,
        force_x=0.0,
        force_r=result.equivalent_centrifugal_force_N,
        scale_mm=0.7 * arrow_scale,
        label="centrifugal equiv.",
    )

    axis.set_aspect("equal", adjustable="box")
    axis.grid(True, alpha=0.18)
    axis.set_xlabel("Axial coordinate [mm]")
    axis.set_ylabel("Radius from shaft centre [mm]")
    axis.set_title("Primary mechanism and FEA load directions")

    all_x = ramp_x + [px, cx, contact_x, com_x]
    all_r = ramp_r + [0.0, pr, cr, contact_r, com_r]
    margin = 10.0
    axis.set_xlim(min(all_x) - margin, max(all_x) + margin)
    axis.set_ylim(min(all_r) - margin, max(all_r) + margin)


def _draw_current_bars(axis, result: FEAResult, shift_rows: list[FEAResult]) -> None:
    axis.clear()
    labels = [
        "Ramp normal",
        "Ramp axial",
        "Ramp radial",
        "Pivot resultant",
        "Centrifugal equiv.",
    ]
    values = [
        abs(result.ramp_force_normal_N),
        abs(result.ramp_force_axial_N),
        abs(result.ramp_force_radial_N),
        abs(result.pivot_reaction_resultant_N),
        abs(result.equivalent_centrifugal_force_N),
    ]
    positions = np.arange(len(labels))
    axis.barh(positions, values)
    axis.set_yticks(positions, labels)
    axis.invert_yaxis()
    axis.set_xlabel("Force magnitude [N]")
    axis.grid(True, axis="x", alpha=0.18)
    status = "compressive" if result.compressive_contact else "LIFT-OFF / tensile required"
    axis.set_title(f"Current per-flyweight / per-ramp loads — {status}")

    compressive_rows = [row for row in shift_rows if row.ramp_force_normal_N >= 0.0]
    peak_normal = max(compressive_rows, key=lambda row: row.ramp_force_normal_N) if compressive_rows else None
    peak_pivot = max(shift_rows, key=lambda row: row.pivot_reaction_resultant_N)
    peak_lines = (
        (
            f"Peak ramp normal through shift @ current RPM: "
            f"{peak_normal.ramp_force_normal_N:.1f} N at "
            f"{peak_normal.axial_position_m / MILLIMETRE:.2f} mm\n"
        )
        if peak_normal is not None
        else "Peak ramp normal through shift: no compressive contact\n"
    ) + (
        f"Peak pivot resultant through shift: {peak_pivot.pivot_reaction_resultant_N:.1f} N "
        f"at {peak_pivot.axial_position_m / MILLIMETRE:.2f} mm\n"
    )

    text = (
        f"Total CINDER flyweight closing force: {result.flyweight_total_closing_force_N:+.1f} N\n"
        f"  centrifugal: {result.flyweight_centrifugal_force_N:+.1f} N\n"
        f"  axial inertia: {result.flyweight_axial_inertia_force_N:+.1f} N\n"
        f"  q-curvature: {result.flyweight_curvature_force_N:+.1f} N\n"
        f"Per ramp: Fx={result.ramp_force_axial_N:+.1f} N, "
        f"Fr={result.ramp_force_radial_N:+.1f} N\n"
        f"Moment about A: {result.ramp_moment_about_point_a_Nm:+.3f} N m\n"
        + peak_lines
        + f"Pivot reaction: ({result.pivot_reaction_axial_N:+.1f}, "
        f"{result.pivot_reaction_radial_N:+.1f}, "
        f"{result.pivot_reaction_tangential_N:+.1f}) N\n"
        f"q={degrees(result.q_rad):.2f} deg, ramp tangent={result.ramp_tangent_angle_deg:.2f} deg"
    )
    axis.text(
        0.98,
        0.02,
        text,
        transform=axis.transAxes,
        ha="right",
        va="bottom",
        fontsize=8.5,
        bbox={"boxstyle": "round", "alpha": 0.08},
    )


def _draw_shift_sweep(axis, rows: list[FEAResult], current: FEAResult) -> None:
    axis.clear()
    x_mm = np.asarray([row.axial_position_m / MILLIMETRE for row in rows])
    axis.plot(x_mm, [row.ramp_force_normal_N for row in rows], label="ramp normal")
    axis.plot(x_mm, [row.ramp_force_axial_N for row in rows], label="ramp axial")
    axis.plot(x_mm, [row.ramp_force_radial_N for row in rows], label="ramp radial")
    axis.plot(x_mm, [row.pivot_reaction_resultant_N for row in rows], label="pivot resultant")
    axis.axvline(current.axial_position_m / MILLIMETRE, linestyle="--", linewidth=1.0)
    axis.set_xlabel("Local primary closure [mm]")
    axis.set_ylabel("Per-ramp / per-flyweight force [N]")
    axis.set_title(f"Load through contact-valid shift at {current.rpm:.0f} RPM")
    axis.grid(True, alpha=0.18)
    axis.legend(fontsize=8)


def _draw_rpm_sweep(axis, rows: list[FEAResult], current: FEAResult) -> None:
    axis.clear()
    rpm = np.asarray([row.rpm for row in rows])
    axis.plot(rpm, [row.ramp_force_normal_N for row in rows], label="ramp normal")
    axis.plot(rpm, [row.ramp_force_axial_N for row in rows], label="ramp axial")
    axis.plot(rpm, [row.ramp_force_radial_N for row in rows], label="ramp radial")
    axis.plot(rpm, [row.pivot_reaction_resultant_N for row in rows], label="pivot resultant")
    axis.axvline(current.rpm, linestyle="--", linewidth=1.0)
    axis.set_xlabel("Primary speed [RPM]")
    axis.set_ylabel("Per-ramp / per-flyweight force [N]")
    axis.set_title(
        f"Load vs RPM at x={current.axial_position_m / MILLIMETRE:.2f} mm"
    )
    axis.grid(True, alpha=0.18)
    axis.legend(fontsize=8)


def _ramp_mode_summary(bundle: MechanismBundle) -> str:
    controls = bundle.controls
    if controls.ramp_mode == RAMP_REFERENCE:
        return "reference 35→20° (locked)"
    if controls.ramp_mode == RAMP_LINEAR:
        return f"constant {controls.start_angle_degrees:.1f}°"
    return (
        f"progressive {controls.start_angle_degrees:.1f}→"
        f"{controls.end_angle_degrees:.1f}°"
    )


def _contact_range_summary(bundle: MechanismBundle) -> str:
    valid_mm = bundle.contact_valid_axial_position_max / MILLIMETRE
    requested_mm = bundle.requested_axial_position_max / MILLIMETRE
    if bundle.contact_range_truncated:
        return f"contact-valid x: 0→{valid_mm:.2f} mm (reference travel {requested_mm:.2f} mm)"
    return f"contact-valid x: full 0→{requested_mm:.2f} mm"


# ---------------------------------------------------------------------------
# Interactive UI
# ---------------------------------------------------------------------------


def create_figure(state: InspectorState):
    figure = plt.figure(figsize=(16.2, 10.2))
    grid = figure.add_gridspec(
        2,
        2,
        left=0.055,
        right=0.985,
        top=0.935,
        bottom=0.34,
        wspace=0.24,
        hspace=0.30,
    )
    mechanism_axis = figure.add_subplot(grid[0, 0])
    bar_axis = figure.add_subplot(grid[0, 1])
    shift_axis = figure.add_subplot(grid[1, 0])
    rpm_axis = figure.add_subplot(grid[1, 1])

    # Geometry controls: intentionally rebuilt only when Apply is pressed.
    radio_axis = figure.add_axes((0.03, 0.055, 0.16, 0.205))
    radio = RadioButtons(radio_axis, RAMP_MODES, active=RAMP_MODES.index(state.bundle.controls.ramp_mode))
    radio_axis.set_title("Ramp family", fontsize=9)

    slider_axes: dict[str, Any] = {}

    def add_slider(name: str, rect, label: str, vmin: float, vmax: float, value: float, step=None):
        axis = figure.add_axes(rect)
        slider = Slider(axis, label, vmin, vmax, valinit=value, valstep=step)
        slider_axes[name] = slider
        return slider

    controls = state.bundle.controls
    start_slider = add_slider(
        "start_angle",
        (0.235, 0.245, 0.29, 0.027),
        "Start / constant tangent [deg]",
        5.0,
        80.0,
        controls.start_angle_degrees,
        0.25,
    )
    end_slider = add_slider(
        "end_angle",
        (0.235, 0.205, 0.29, 0.027),
        "Progressive end tangent [deg]",
        5.0,
        80.0,
        controls.end_angle_degrees,
        0.25,
    )
    radius_slider = add_slider(
        "pivot_radius",
        (0.235, 0.165, 0.29, 0.027),
        "Pivot / initial radius r_P [in]",
        0.75,
        3.00,
        controls.pivot_radius / INCH_TO_METRE,
        0.005,
    )
    mass_slider = add_slider(
        "tip_mass",
        (0.235, 0.125, 0.29, 0.027),
        "Tip hardware mass [g / flyweight]",
        0.0,
        650.0,
        controls.tip_mass_per_flyweight * 1000.0,
        1.0,
    )

    rpm_slider = add_slider(
        "rpm",
        (0.625, 0.245, 0.31, 0.027),
        "Primary speed [RPM]",
        0.0,
        6000.0,
        state.operating.rpm,
        10.0,
    )
    shift_slider = add_slider(
        "shift",
        (0.625, 0.205, 0.31, 0.027),
        "Local primary closure [mm]",
        state.bundle.mechanism_map.axial_position_min / MILLIMETRE,
        state.bundle.mechanism_map.axial_position_max / MILLIMETRE,
        state.operating.axial_position / MILLIMETRE,
        0.05,
    )
    speed_slider = add_slider(
        "axial_speed",
        (0.625, 0.165, 0.31, 0.027),
        "Closure speed x_dot [mm/s]",
        -250.0,
        250.0,
        state.operating.axial_speed / MILLIMETRE,
        1.0,
    )
    accel_slider = add_slider(
        "axial_accel",
        (0.625, 0.125, 0.31, 0.027),
        "Closure accel x_ddot [m/s²]",
        -20.0,
        20.0,
        state.operating.axial_acceleration,
        0.05,
    )

    apply_axis = figure.add_axes((0.235, 0.066, 0.12, 0.038))
    export_axis = figure.add_axes((0.365, 0.066, 0.12, 0.038))
    reset_axis = figure.add_axes((0.625, 0.066, 0.12, 0.038))
    apply_button = Button(apply_axis, "Apply geometry")
    export_button = Button(export_axis, "Export CSV + PNG")
    reset_button = Button(reset_axis, "Reset operating")

    status_text = figure.text(
        0.51,
        0.292,
        "",
        ha="center",
        va="center",
        fontsize=9.2,
    )

    cache: dict[str, Any] = {"shift": None, "rpm": None}

    def update_operating_from_sliders() -> None:
        state.operating = OperatingPoint(
            rpm=float(rpm_slider.val),
            axial_position=float(shift_slider.val) * MILLIMETRE,
            axial_speed=float(speed_slider.val) * MILLIMETRE,
            axial_acceleration=float(accel_slider.val),
        )

    def redraw(*_args) -> None:
        update_operating_from_sliders()
        try:
            current = evaluate_fea_loads(state)
            shift_rows = sample_shift_sweep(state)
            rpm_rows = sample_rpm_sweep(state)
            cache["shift"] = shift_rows
            cache["rpm"] = rpm_rows
            _draw_mechanism(mechanism_axis, state, current)
            _draw_current_bars(bar_axis, current, shift_rows)
            _draw_shift_sweep(shift_axis, shift_rows, current)
            _draw_rpm_sweep(rpm_axis, rpm_rows, current)

            compressive = "contact OK" if current.compressive_contact else "CONTACT INADMISSIBLE"
            status_text.set_text(
                f"{_ramp_mode_summary(state.bundle)}   |   "
                f"active tangent={current.ramp_tangent_angle_deg:.1f}°   |   "
                f"{_contact_range_summary(state.bundle)}   |   "
                f"r_P={state.bundle.controls.pivot_radius / INCH_TO_METRE:.3f} in   |   "
                f"tip={state.bundle.controls.tip_mass_per_flyweight * 1000.0:.0f} g/flyweight   |   "
                f"{compressive}"
            )
        except Exception as error:  # UI should remain usable after a bad point.
            status_text.set_text(f"Current operating point failed: {error}")
        figure.canvas.draw_idle()

    def apply_geometry(_event) -> None:
        candidate = GeometryControls(
            ramp_mode=str(radio.value_selected),
            start_angle_degrees=float(start_slider.val),
            end_angle_degrees=float(end_slider.val),
            pivot_radius=float(radius_slider.val) * INCH_TO_METRE,
            tip_mass_per_flyweight=float(mass_slider.val) / 1000.0,
        )
        try:
            new_bundle = build_bundle(state.hardware, candidate)
        except Exception as error:
            status_text.set_text(f"Geometry rejected — keeping previous valid model: {error}")
            figure.canvas.draw_idle()
            return
        state.bundle = new_bundle
        state.shift_geometry_cache = None
        state.current_geometry_cache = None
        # Reflect the geometry that was actually built. Reference mode locks
        # 35→20; constant-angle mode has one angle, so the end slider follows it.
        if abs(float(start_slider.val) - new_bundle.controls.start_angle_degrees) > 1.0e-12:
            start_slider.set_val(new_bundle.controls.start_angle_degrees)
        if abs(float(end_slider.val) - new_bundle.controls.end_angle_degrees) > 1.0e-12:
            end_slider.set_val(new_bundle.controls.end_angle_degrees)
        # Alternate designs may have a shorter continuous-contact interval than
        # the reference 0.75-in travel. The explorer exposes that valid range
        # rather than rejecting the geometry outright.
        shift_slider.valmin = new_bundle.mechanism_map.axial_position_min / MILLIMETRE
        shift_slider.valmax = new_bundle.mechanism_map.axial_position_max / MILLIMETRE
        shift_slider.ax.set_xlim(shift_slider.valmin, shift_slider.valmax)
        shift_slider.set_val(float(np.clip(shift_slider.val, shift_slider.valmin, shift_slider.valmax)))
        redraw()

    def export(_event) -> None:
        update_operating_from_sliders()
        try:
            export_current_state(
                state=state,
                figure=figure,
                shift_rows=cache.get("shift"),
                rpm_rows=cache.get("rpm"),
            )
            status_text.set_text(f"Exported to {state.output_dir}")
        except Exception as error:
            status_text.set_text(f"Export failed: {error}")
        figure.canvas.draw_idle()

    def reset_operating(_event) -> None:
        rpm_slider.reset()
        shift_slider.reset()
        speed_slider.reset()
        accel_slider.reset()
        redraw()

    for slider in (rpm_slider, shift_slider, speed_slider, accel_slider):
        slider.on_changed(redraw)
    apply_button.on_clicked(apply_geometry)
    export_button.on_clicked(export)
    reset_button.on_clicked(reset_operating)

    # Keep widget references alive for the life of the figure.
    figure._fea_widgets = {
        "radio": radio,
        "sliders": slider_axes,
        "buttons": (apply_button, export_button, reset_button),
    }
    redraw()
    figure.suptitle(
        "CINDER primary fixed-pivot FEA load inspector",
        fontsize=15,
        y=0.975,
    )
    return figure


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    reference = load_reference_hardware(DEFAULT_CONFIG_PATH)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Reference fixed-pivot geometry JSON.",
    )
    parser.add_argument(
        "--ramp-mode",
        choices=("reference", "linear", "custom"),
        default="reference",
    )
    parser.add_argument("--start-angle-deg", type=float, default=35.0)
    parser.add_argument("--end-angle-deg", type=float, default=20.0)
    parser.add_argument(
        "--pivot-radius-in",
        type=float,
        default=reference.pivot_radius / INCH_TO_METRE,
    )
    parser.add_argument(
        "--tip-mass-g",
        type=float,
        default=reference.tip_mass_per_flyweight * 1000.0,
    )
    parser.add_argument("--rpm", type=float, default=3200.0)
    parser.add_argument("--shift-mm", type=float, default=0.0)
    parser.add_argument("--shift-speed-mm-s", type=float, default=0.0)
    parser.add_argument("--shift-accel-m-s2", type=float, default=0.0)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--export",
        action="store_true",
        help="Export current point and sweeps immediately.",
    )
    parser.add_argument("--save", type=Path, default=None)
    parser.add_argument("--no-show", action="store_true")
    return parser.parse_args()


def _cli_ramp_mode(value: str) -> str:
    return {
        "reference": RAMP_REFERENCE,
        "linear": RAMP_LINEAR,
        "custom": RAMP_CUSTOM,
    }[value]


def main() -> None:
    args = parse_args()
    hardware = load_reference_hardware(args.config)
    controls = GeometryControls(
        ramp_mode=_cli_ramp_mode(args.ramp_mode),
        start_angle_degrees=float(args.start_angle_deg),
        end_angle_degrees=float(args.end_angle_deg),
        pivot_radius=float(args.pivot_radius_in) * INCH_TO_METRE,
        tip_mass_per_flyweight=float(args.tip_mass_g) / 1000.0,
    )
    bundle = build_bundle(hardware, controls)
    operating = OperatingPoint(
        rpm=float(args.rpm),
        axial_position=float(np.clip(
            args.shift_mm * MILLIMETRE,
            bundle.mechanism_map.axial_position_min,
            bundle.mechanism_map.axial_position_max,
        )),
        axial_speed=float(args.shift_speed_mm_s) * MILLIMETRE,
        axial_acceleration=float(args.shift_accel_m_s2),
    )
    state = InspectorState(
        hardware=hardware,
        bundle=bundle,
        operating=operating,
        output_dir=args.output_dir,
    )
    figure = create_figure(state)
    if args.save is not None:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(args.save, dpi=180, bbox_inches="tight")
        print(f"Saved {args.save}")
    if args.export:
        export_current_state(state=state, figure=figure)
    if args.no_show:
        plt.close(figure)
    else:
        plt.show()


if __name__ == "__main__":
    main()
