"""Kinematic tune inspection. CINDER owns all geometry and contact selection.

Editing uses only the sampled contact trace already needed by the drawing.
Missing contact blocks Save/Use, but a complete preview is not a full construction
audit. The existing save/run validators perform that expensive check only when
the user submits the tune. No dynamic simulation is run here.
"""
from __future__ import annotations

from math import atan, cos, sin
from typing import TYPE_CHECKING, Any

import numpy as np

from app.schemas.scene import (
    FlyweightScene,
    MechanismPose,
    MechanismScene,
    TuneProfileTrace,
    TuneScenePreview,
)

if TYPE_CHECKING:
    from app.application.cinder_gateway import CinderGateway


def _profile_trace(
    profile: Any,
    *,
    used: tuple[float, float] | None = None,
    extra_coordinates: list[float] | None = None,
):
    # Include exact joins, usable endpoints and solved contact positions. A
    # short transition must not disappear between uniform plotting samples.
    knots = [profile.x_min, profile.x_max]
    if used:
        knots.extend(x for x in used if profile.x_min <= x <= profile.x_max)
    continuity = getattr(profile, "junction_continuity", None)
    if callable(continuity):
        knots.extend(junction.coordinate for junction in continuity())
    knots = sorted(set(knots))
    segment_samples = [
        float(x) for left, right in zip(knots, knots[1:])
        for x in np.linspace(left, right, 17)
    ]
    coordinates = np.unique(np.concatenate((
        np.linspace(profile.x_min, profile.x_max, 161), segment_samples,
        [x for x in (extra_coordinates or []) if profile.x_min <= x <= profile.x_max],
    )))
    samples = [profile.evaluate(float(x)) for x in coordinates]
    return TuneProfileTrace(
        coordinates_m=coordinates.tolist(),
        values_m=[float(p.value) for p in samples],
        slope_angles_rad=[atan(p.first_derivative) for p in samples],
        used_start_m=used[0] if used else None,
        used_end_m=used[1] if used else None,
    )


def _trace_primary(surface: Any, positions: list[float], warnings: list[str]):
    """A visual contact prefix and its first failing closure, never another root.

    This diagnostic trace does not replace the full CINDER construction audit.
    The latter also checks derivative regularity, interference and map coverage.
    """
    spec = surface.spec
    inside = sorted(set(
        x for x in positions if spec.axial_position_min <= x <= spec.axial_position_max
    ))
    outside = [x for x in positions if not spec.axial_position_min <= x <= spec.axial_position_max]
    failed = min(outside) if outside else None
    if not inside:
        warnings.append("The primary travel is outside the declared flyweight operating interval.")
        return {}, failed
    # Begin at the declared assembly position even if it precedes visible
    # travel; CINDER must select and continue the assembled branch itself.
    grid = np.unique(np.concatenate((
        np.linspace(spec.axial_position_min, max(inside), 129), inside,
    )))
    try:
        samples = surface.trace_contact_branch(grid, require_complete=False)
    except ValueError as error:
        warnings.append(f"Primary contact cannot be constructed: {error}")
        return {}, min(positions)
    if len(samples) < len(grid):
        contact_failure = float(grid[len(samples)])
        failed = contact_failure if failed is None else min(failed, contact_failure)
        warnings.append(
            "The selected primary contact branch cannot be continued at "
            f"{contact_failure * 1000:.3g} mm closure. Adjust the ramp shape or "
            "its starting position; no alternative contact branch is substituted."
        )
    if outside:
        warnings.append("Part of the primary travel lies outside the flyweight operating interval.")
    return {float(x): sample for x, sample in zip(grid, samples)}, failed


def build_tune_preview(gateway: CinderGateway, assembly: dict) -> TuneScenePreview:
    from cinder.contracts.document import _decode_flyweight_geometry, _decode_pulley
    from cinder.model.cvt.actuation.fixed_pivot_flyweight import PivotedRollerFollowerGeometry
    from cinder.model.cvt.geometry import BeltPulleyGeometry

    gateway.validate_assembly_shape(assembly)
    # Preview feedback is derived from the same contact samples we render.
    # Do not compile/audit the dynamic map here on every debounced edit. Save
    # and run submission independently invoke their full CINDER validators.
    validation = {"is_valid": True, "findings": []}
    preview = gateway.scene_preview(assembly['geometry'], frame_count=65)
    dimensions = gateway._scene_geometry_spec(assembly['geometry'])
    path = BeltPulleyGeometry(dimensions)
    shifts = np.unique([*(f.shift_m for f in preview.frames), dimensions.deadzone_shift])
    positions = {float(s): path.evaluate(float(s)) for s in shifts}
    warnings: list[str] = []
    primary = None
    surface = None
    primary_trace = None
    contacts = {}
    primary_failure = None
    primary_components = assembly['pulleys']['primary']['components']
    secondary_components = assembly['pulleys']['secondary']['components']
    flyweights = [c for c in primary_components if c['kind'] == 'fixed_pivot_roller_flyweight']
    if len(flyweights) > 1:
        raise ValueError('The tune preview supports one fixed-pivot mechanism per primary.')
    if flyweights:
        component = flyweights[0]
        spec = _decode_flyweight_geometry(component['geometry'])
        surface = PivotedRollerFollowerGeometry(spec)
        primary_trace = _profile_trace(spec.ramp_profile)
        # Physical ramp geometry at its reference pose; do not call the contact
        # solver at an out-of-range artificial zero position just to draw it.
        primary = FlyweightScene(
            count=component['mass_geometry']['number_of_flyweights'],
            pivot_m=(spec.pivot_axial_position, spec.pivot_radius),
            roller_radius_m=spec.roller_radius,
            roller_side_sign=spec.roller_side_sign,
            ramp_points_m=[
                (spec.ramp_reference_axial_position + spec.ramp_axial_direction * x,
                 spec.ramp_reference_radius + y)
                for x, y in zip(primary_trace.coordinates_m, primary_trace.values_m)
            ],
        )
        contacts, primary_failure = _trace_primary(
            surface, [p.primary_axial_coordinate.value for p in positions.values()], warnings
        )
        if contacts:
            coordinates = [p.contact_coordinate for p in contacts.values()]
            primary_trace = _profile_trace(
                spec.ramp_profile, used=(min(coordinates), max(coordinates)),
                extra_coordinates=coordinates,
            )

    secondary = _decode_pulley(
        assembly['pulleys']['secondary'], location='secondary'
    ).helical_coupling
    helix_points = []
    secondary_trace = None
    openings = {}
    if secondary:
        helix = secondary.profile
        for shift, position in positions.items():
            openings[shift] = float(
                secondary.opening_offset
                + secondary.opening_per_axial_position * position.secondary_axial_coordinate.value
            )
        secondary_trace = _profile_trace(
            helix.circumferential_profile,
            used=(min(openings.values()), max(openings.values())),
        )
        for opening in np.linspace(helix.opening_travel_min, helix.opening_travel_max, 161):
            theta = helix.evaluate(float(opening)).theta
            helix_points.append((helix.radius * cos(theta), helix.radius * sin(theta), float(opening)))

    poses = []
    for shift, position in positions.items():
        local_p = position.primary_axial_coordinate.value
        local_s = position.secondary_axial_coordinate.value
        contact = contacts.get(local_p)
        contact_point = normal = None
        if contact is not None and surface is not None:
            contact_point = surface.ramp_surface_point(
                contact_coordinate=contact.contact_coordinate, axial_position=local_p
            )
            normal = (
                (contact.roller_center_axial_position - contact_point[0]) / surface.spec.roller_radius,
                (contact.roller_center_radius - contact_point[1]) / surface.spec.roller_radius,
            )
        helix_sample = secondary.evaluate_from_local_coordinate(
            axial_position=local_s, d_axial_position_ds=1, d2_axial_position_ds2=0
        ) if secondary else None
        poses.append(MechanismPose(
            shift_m=shift,
            primary_contact_m=contact_point,
            primary_normal_axial_radial=normal,
            primary_roller_m=(contact.roller_center_axial_position, contact.roller_center_radius)
                if contact is not None else None,
            primary_ramp_shift_m=local_p,
            secondary_axial_position_m=local_s,
            secondary_angle_rad=helix_sample.theta if helix_sample else 0,
            secondary_helix_dtheta_dx=helix_sample.dtheta_ds if helix_sample else None,
        ))
    preview.geometry.mechanisms = MechanismScene(
        primary=primary,
        secondary_helix_points_m=helix_points,
        primary_has_spring=any(c['kind'] == 'axial_spring' for c in primary_components),
        secondary_has_spring=any(c['kind'] == 'axial_spring' for c in secondary_components),
        poses=poses,
    )
    visible_contacts = [contacts.get(positions[f.shift_m].primary_axial_coordinate.value) for f in preview.frames]
    # Every rendered pose must have contact. Keep this tied to the preview,
    # not to a second, denser construction audit. A missing prefix stays hidden
    # and disables submission; the full Save audit can still find other issues.
    missing_pose = next((
        pose.primary_ramp_shift_m for pose in poses
        if primary is not None and pose.primary_roller_m is None
    ), None)
    if missing_pose is not None:
        primary_failure = missing_pose if primary_failure is None else min(primary_failure, missing_pose)
    if primary_failure is not None:
        validation["is_valid"] = False
        validation["findings"].append({
            "severity": "error",
            "code": "actuation.primary_contact_incomplete",
            "message": (
                "Continuous primary roller contact is required through the full "
                f"travel. Contact is unavailable near {primary_failure * 1000:.3g} mm closure."
            ),
            "location": "pulleys.primary",
        })
    return TuneScenePreview(
        validation=validation, primary_contact_failure_m=primary_failure,
        geometry=preview.geometry, frames=preview.frames,
        primary_profile=primary_trace, secondary_profile=secondary_trace,
        primary_arm_angles_rad=[p.angle if p else None for p in visible_contacts],
        primary_contact_coordinates_m=[p.contact_coordinate if p else None for p in visible_contacts],
        secondary_opening_m=[openings.get(f.shift_m) for f in preview.frames],
        warnings=warnings,
    )
