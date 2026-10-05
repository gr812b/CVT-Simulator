"""The backend's single direct dependency on CINDER.

Routes, stores, Pydantic schemas, and worker orchestration stay CINDER-free.
This module converts explicit transport primitives into the stable public
CINDER contracts and study requests, then returns JSON-safe public projections.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from functools import lru_cache
from typing import Any

import cinder
import numpy as np
from cinder.contracts import (
    SIMULATION_CASE_SCHEMA_VERSION,
    SIMULATION_RESULT_CONTRACT_VERSION,
    assembly_document_json_schema,
    component_catalog_document,
    decode_assembly_document,
    decode_simulation_case_document,
    editable_simulation_case_schema,
    project_clamping_force_response,
    project_geometry_feasibility,
    project_geometry_path,
    project_geometry_summary,
    project_radius_plane,
    project_ratio_sensitivity_field,
    project_simulation_result,
    public_conventions,
    simulation_case_document_json_schema,
    simulation_result_json_schema,
    validate_assembly_document,
    validate_simulation_case_document,
)
from cinder.model.cvt.actuation import (
    HelicalTorqueReactionForce,
    PulleyActuator,
)
from cinder.model.cvt.closure import ClosureUnknown, ClosureUnknowns
from cinder.model.cvt.geometry import BeltPulleyGeometry, BeltSectionSpec
from cinder.results.fields import build_belt_path_domain
from cinder.studies import (
    ActuationOperatingPoint,
    ActuationResponseAxis,
    ActuationStateCoordinate,
    EndpointRadiiDesignRequest,
    GeometryDesignContext,
    PulleyClampingForceStudyRequest,
    PulleyLocation,
    TargetRatioDesignRequest,
    evaluate_geometry_feasibility,
    evaluate_radius_plane,
    evaluate_ratio_sensitivity_field,
    sample_geometry_path,
    sample_pulley_clamping_force,
    solve_geometry_from_endpoint_radii,
    solve_geometry_from_target_ratios,
    summarize_geometry_design,
)
from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

from app.schemas.scene import (
    FlyweightScene,
    MechanismPose,
    MechanismScene,
    SceneFrame,
    SceneGeometry,
    ScenePreview,
)

DEFAULT_EXECUTION_PROFILE = "default"
VALIDATION_SLOTTED_SECONDARY_HELIX_PROFILE = "validation_slotted_secondary_helix"


class _BilateralHelicalTorqueReactionForce(HelicalTorqueReactionForce):
    """Signed zero-clearance helix law with support from either slot flank."""

    compressive_contact_margin = None
    has_compressive_contact = None


def _apply_execution_profile(decoded: object, execution_profile: str) -> None:
    """Apply backend-only execution policy without changing the frozen document."""

    if execution_profile == DEFAULT_EXECUTION_PROFILE:
        return
    if execution_profile != VALIDATION_SLOTTED_SECONDARY_HELIX_PROFILE:
        raise ValueError(f"Unsupported execution profile: {execution_profile!r}.")

    plant = decoded.plant
    laws = []
    changed = 0
    for law in plant.secondary_actuator.force_laws:
        if isinstance(law, _BilateralHelicalTorqueReactionForce):
            laws.append(law)
        elif isinstance(law, HelicalTorqueReactionForce):
            laws.append(_BilateralHelicalTorqueReactionForce(spec=law.spec))
            changed += 1
        else:
            laws.append(law)

    if changed != 1:
        raise RuntimeError(
            "Validation slotted-helix profile expected exactly one secondary "
            f"HelicalTorqueReactionForce; found {changed}."
        )
    object.__setattr__(plant, "secondary_actuator", PulleyActuator(*laws))


class CinderGateway:
    """Small application-facing façade over CINDER's public API."""

    def runtime_identity(self) -> dict[str, Any]:
        """Return the installed CINDER package and public contract versions."""

        return {
            "package": "cinder-cvt",
            "package_version": str(cinder.__version__),
            "simulation_case_schema_version": int(SIMULATION_CASE_SCHEMA_VERSION),
            "simulation_result_contract_version": int(
                SIMULATION_RESULT_CONTRACT_VERSION
            ),
        }

    def conventions(self) -> dict[str, Any]:
        return public_conventions().as_dict()

    def component_catalog(self) -> dict[str, Any]:
        return component_catalog_document()

    def editor_schema(self) -> dict[str, Any]:
        return editable_simulation_case_schema()

    def assembly_json_schema(self) -> dict[str, Any]:
        return assembly_document_json_schema()

    def inline_assembly_json_schema(
        self, definition: str | None = None
    ) -> dict[str, Any]:
        """Embed the canonical schema in OpenAPI without copying its fields."""
        schema = self.assembly_json_schema()

        def expand(value):
            if isinstance(value, list):
                return [expand(item) for item in value]
            if not isinstance(value, dict):
                return value
            if "$ref" in value:
                return expand(schema["$defs"][value["$ref"].rsplit("/", 1)[-1]])
            return {
                key: expand(item)
                for key, item in value.items()
                if key not in {"$defs", "$id", "$schema"}
            }

        return expand(schema if definition is None else schema["$defs"][definition])

    def validate_assembly(self, document: Mapping[str, Any]) -> dict[str, Any]:
        return validate_assembly_document(document).as_dict()

    def validate_assembly_shape(self, document: dict[str, Any]) -> dict[str, Any]:
        """Enforce the exact schema exported to the editor before persistence."""
        json.dumps(document, allow_nan=False)
        error = best_match(
            Draft202012Validator(self.assembly_json_schema()).iter_errors(document)
        )
        if error is not None:
            path = "/" + "/".join(str(part) for part in error.absolute_path)
            raise ValueError(f"{path}: {error.message}")
        return document

    def simulation_case_json_schema(self) -> dict[str, Any]:
        return simulation_case_document_json_schema()

    def simulation_result_json_schema(self) -> dict[str, Any]:
        return simulation_result_json_schema()

    def validate_simulation_case(self, document: Mapping[str, Any]) -> dict[str, Any]:
        return validate_simulation_case_document(document).as_dict()

    def run_simulation(
        self,
        document: Mapping[str, Any],
        *,
        include_reported_segments: bool = False,
        include_raw_trace: bool = False,
        execution_profile: str = DEFAULT_EXECUTION_PROFILE,
    ) -> dict[str, Any]:
        """Run one complete CINDER document and return its public projection."""

        decoded = decode_simulation_case_document(document)
        _apply_execution_profile(decoded, execution_profile)
        system = decoded.build_system()
        result = system.run(
            time_span=decoded.time_span,
            initial_state=decoded.initial_state,
            initial_mode=decoded.initial_mode,
            settings=decoded.integrator_settings,
            reporting_settings=decoded.reporting_settings,
        )
        return project_simulation_result(
            result,
            include_reported_segments=include_reported_segments,
            include_raw_trace=include_raw_trace,
        )

    def run_checkpointed(self, document, *, checkpoint, course_policy=None, **options):
        """Advance accepted chunks; reporting uses an independent solver instance.

        Administrative checkpoints preserve hybrid modes and the live closure cache.
        Only accepted states are saved. A killed process can lose its current chunk,
        never corrupt the preceding atomic checkpoint.
        """
        from dataclasses import replace

        from cinder.execution.hybrid import HybridEvent, HybridTransition
        from cinder.execution.hybrid.hybrid import HybridIntegrationResult
        from cinder.results import CVTIntegrationTrace, CVTResultBuilder

        decoded = decode_simulation_case_document(document)
        profile = options.get("execution_profile", DEFAULT_EXECUTION_PROFILE)
        _apply_execution_profile(decoded, profile)
        system = decoded.build_system()
        reporter = decode_simulation_case_document(document)
        _apply_execution_profile(reporter, profile)
        builder = CVTResultBuilder(system=reporter.build_system())
        policy = course_policy or {}
        factor = None
        secondary = document["shaft_boundaries"]["secondary"]
        if (
            document["host"]["kind"] == "secondary_shaft_angle"
            and "final_drive" in secondary
        ):
            drive = secondary["final_drive"]
            factor = drive["wheel_radius_m"] / drive["reduction_ratio"]
        start, end = decoded.time_span
        time, state, mode = start, decoded.initial_state, decoded.initial_mode
        peak = float(state[5]) * factor if factor else 0.0
        progress_peak, progress_time = peak, start
        finish = policy.get("finish_m")
        rollback = policy.get("rollback_m")
        no_progress = policy.get("no_progress_s")
        if factor is not None and (finish is not None or rollback is not None):
            base_host = system.host

            class CourseHost:
                # Delegate the existing host mechanics; add observation events only.
                state_block = base_host.state_block
                context = base_host.context
                rhs = base_host.rhs

                def events(self, **_):
                    events = []
                    if finish is not None:
                        events.append(
                            HybridEvent(
                                "course_finish",
                                lambda t, y: float(y[5]) * factor - finish,
                                direction=1,
                            )
                        )
                    if rollback is not None:
                        events.append(
                            HybridEvent(
                                "rollback_limit",
                                lambda t, y: float(y[5]) * factor - (peak - rollback),
                                direction=-1,
                            )
                        )
                    return events

                def transition(self, *, fired_event_names, **_):
                    for reason in ("course_finish", "rollback_limit"):
                        if reason in fired_event_names:
                            return HybridTransition(next_mode=None, reason=reason)
                    return None

            system.host = CourseHost()
        integrator = replace(decoded.integrator_settings, retain_dense_output=True)
        segments, transitions, reports = [], [], []
        offsets = {}
        integrated_keys = (
            "observer.primary_shaft_angle",
            "observer.primary_boundary_work",
            "observer.secondary_boundary_work",
            "observer.primary_slip_dissipation",
            "observer.secondary_slip_dissipation",
        )
        projected = None
        while time < end - 1e-10:
            # Early launch gets an early checkpoint; subsequent chunks are 0.5 s.
            next_time = min(end, time + (0.1 if time == start else 0.5))
            if no_progress is not None:
                next_time = min(next_time, progress_time + no_progress)
            trace = system.integrate_trace(
                time_span=(time, next_time),
                initial_state=state,
                initial_mode=mode,
                settings=integrator,
            )
            time, state = trace.final_time, trace.final_state
            mode = trace.segments[-1].mode
            if trace.transitions and abs(trace.transitions[-1].time - time) < 1e-10:
                transition = trace.transitions[-1].transition
                if not transition.terminates:
                    mode = transition.next_mode
            part = builder.build(trace, settings=decoded.reporting_settings)
            for segment in part.segments:
                signals = dict(segment.signals)
                for key in integrated_keys:
                    if key in signals and key in offsets:
                        signals[key] = replace(
                            signals[key], values=signals[key].values + offsets[key]
                        )
                reports.append(replace(segment, signals=signals))
            for key in integrated_keys:
                if key in reports[-1].signals:
                    offsets[key] = float(reports[-1].signals[key].values[-1])
            segments.extend(trace.segments)
            transitions.extend(trace.transitions)
            reason = trace.termination_reason if not trace.completed else "checkpoint"
            if factor is not None:
                for segment in trace.segments:
                    for t, x in zip(segment.time, segment.state[5] * factor):
                        peak = max(peak, float(x))
                        # 5 cm rejects numerical jitter without treating slow travel as stopped.
                        if peak >= progress_peak + 0.05:
                            progress_peak, progress_time = peak, float(t)
                if (
                    trace.completed
                    and no_progress is not None
                    and time >= progress_time + no_progress - 1e-9
                ):
                    reason = "no_forward_progress"
            if trace.completed and len(transitions) >= integrator.maximum_transitions:
                reason = "maximum_transitions"
            if reason == "checkpoint" and time >= end - 1e-10:
                reason = "time_limit" if finish is not None else "duration_reached"
            complete = reason in ("course_finish", "duration_reached")
            aggregate = replace(
                part,
                trace=CVTIntegrationTrace(
                    HybridIntegrationResult(
                        tuple(segments), tuple(transitions), complete, reason
                    )
                ),
                segments=tuple(reports),
                summary=replace(
                    part.summary,
                    duration=time - start,
                    segment_count=len(segments),
                    transition_count=len(transitions),
                ),
            )
            projected = project_simulation_result(
                aggregate,
                include_reported_segments=options.get(
                    "include_reported_segments", False
                ),
                include_raw_trace=options.get("include_raw_trace", False),
            )
            checkpoint(projected)
            if reason != "checkpoint":
                break
        return projected

    def _scene_geometry_spec(self, geometry):
        return self._geometry_context(geometry).build_geometry_spec(
            primary_outer_radius_at_zero_shift=_number(
                geometry, "primary_outer_radius_at_zero_shift_m"
            ),
            secondary_outer_radius_at_zero_shift=_number(
                geometry, "secondary_outer_radius_at_zero_shift_m"
            ),
        )

    def scene_preview(
        self, geometry: Mapping[str, Any], *, frame_count: int = 1
    ) -> ScenePreview:
        """Resolve a compact visual projection; no integration or job is involved.

        Belt points evaluate CINDER's public cord-path expressions. Sheave
        radius envelopes come from the same resolved spec as the studies.
        """
        spec = self._scene_geometry_spec(geometry)
        dimensions = SceneGeometry(
            belt_outer_width_m=spec.belt.outer_width,
            belt_inner_width_m=spec.belt.inner_width,
            belt_height_m=spec.belt.height,
            cord_depth_from_outer_m=spec.belt.cord_depth_from_outer,
            sheave_half_angle_rad=spec.sheave_half_angle,
            center_distance_m=spec.center_distance,
            primary_outer_radius_min_m=spec.primary_outer_radius_at_zero_shift,
            primary_outer_radius_max_m=spec.primary_outer_radius_at_max_shift,
            secondary_outer_radius_min_m=spec.secondary_outer_radius_at_max_shift,
            secondary_outer_radius_max_m=spec.secondary_outer_radius_at_zero_shift,
            deadzone_shift_m=spec.deadzone_shift,
            max_shift_m=spec.max_shift,
        )
        model = BeltPulleyGeometry(spec)
        domain = build_belt_path_domain(center_distance=spec.center_distance)
        frames = []
        for shift in np.linspace(0, spec.max_shift, frame_count):
            pose = model.evaluate(float(shift))
            signals = {
                "geometry.primary_effective_radius": pose.primary.effective,
                "geometry.secondary_effective_radius": pose.secondary.effective,
                "geometry.primary_wrap_angle": pose.primary_wrap_angle,
                "geometry.secondary_wrap_angle": pose.secondary_wrap_angle,
            }
            points, regions = [], []
            # Preserve tangent boundaries and sample each wrap sufficiently even
            # for a short primary contact arc. No closure is reimplemented here.
            u = np.linspace(0, 1, 48, endpoint=False)
            for region in domain.regions:
                x = region.x.evaluate(coordinate=u, signals=signals)
                y = region.y.evaluate(coordinate=u, signals=signals)
                points.extend(zip(x.tolist(), y.tolist(), strict=True))
                regions.extend([region.key] * len(u))
            frames.append(
                SceneFrame(
                    shift_m=float(shift),
                    primary_outer_radius_m=pose.primary.outer,
                    secondary_outer_radius_m=pose.secondary.outer,
                    belt_axial_position_m=-(
                        spec.deadzone_shift / 2 + pose.belt_axial_coordinate.value
                    ),
                    belt_path_m=points,
                    belt_regions=regions,
                )
            )
        return ScenePreview(geometry=dimensions, frames=frames)

    def tune_scene(self, assembly):
        """Preview the initial mechanism contact without a full-travel audit.

        This is a visual projection, not a substitute for save/run validation.
        """
        from cinder.contracts.document import (
            _decode_flyweight_geometry,
            _decode_pulley,
        )
        from cinder.model.cvt.actuation.fixed_pivot_flyweight import (
            PivotedRollerFollowerGeometry,
        )

        preview = self.scene_preview(assembly["geometry"])
        primary = None
        roller_point = None
        for component in assembly["pulleys"]["primary"]["components"]:
            if component["kind"] != "fixed_pivot_roller_flyweight":
                continue
            spec = _decode_flyweight_geometry(component["geometry"])
            surface = PivotedRollerFollowerGeometry(spec)
            contact = surface.contact_candidates(0)
            if not contact:
                raise ValueError(
                    "The primary roller does not contact this ramp at its initial position."
                )
            roller = min(contact, key=lambda item: item.angle)
            roller_point = (
                roller.roller_center_axial_position,
                roller.roller_center_radius,
            )
            primary = FlyweightScene(
                count=component["mass_geometry"]["number_of_flyweights"],
                pivot_m=(spec.pivot_axial_position, spec.pivot_radius),
                roller_radius_m=spec.roller_radius,
                roller_side_sign=spec.roller_side_sign,
                ramp_points_m=[
                    surface.ramp_surface_point(
                        contact_coordinate=float(x), axial_position=0
                    )
                    for x in np.linspace(
                        spec.ramp_profile.x_min, spec.ramp_profile.x_max, 80
                    )
                ],
            )
        coupling = assembly["pulleys"]["secondary"].get("helical_coupling")
        points, poses = [], []
        secondary = _decode_pulley(
            assembly["pulleys"]["secondary"], location="secondary"
        ).helical_coupling
        if coupling:
            helix = secondary.profile
            for q in np.linspace(
                helix.opening_travel_min, helix.opening_travel_max, 80
            ):
                theta = helix.evaluate(float(q)).theta
                points.append(
                    (
                        helix.radius * float(np.cos(theta)),
                        helix.radius * float(np.sin(theta)),
                        float(q),
                    )
                )
        dimensions = self._scene_geometry_spec(assembly["geometry"])
        path = BeltPulleyGeometry(dimensions)
        for shift in np.unique(
            np.append(
                np.linspace(0, dimensions.max_shift, 65), dimensions.deadzone_shift
            )
        ):
            position = path.evaluate(float(shift))
            local = position.secondary_axial_coordinate.value
            angle = (
                secondary.evaluate_from_local_coordinate(
                    axial_position=local, d_axial_position_ds=0, d2_axial_position_ds2=0
                ).theta
                if secondary
                else 0
            )
            poses.append(
                MechanismPose(
                    shift_m=float(shift),
                    primary_roller_m=roller_point if shift == 0 else None,
                    primary_ramp_shift_m=position.primary_axial_coordinate.value,
                    secondary_axial_position_m=local,
                    secondary_angle_rad=angle,
                )
            )
        preview.geometry.mechanisms = MechanismScene(
            primary=primary,
            secondary_helix_points_m=points,
            primary_has_spring=any(
                c["kind"] == "axial_spring"
                for c in assembly["pulleys"]["primary"]["components"]
            ),
            secondary_has_spring=any(
                c["kind"] == "axial_spring"
                for c in assembly["pulleys"]["secondary"]["components"]
            ),
            poses=poses,
        )
        return preview

    def assembly_scene(self, assembly):
        return self._assembly_scene(json.dumps(assembly, sort_keys=True))

    @staticmethod
    @lru_cache(maxsize=32)
    def _assembly_scene(encoded):
        from cinder.model.cvt.actuation.fixed_pivot_flyweight import (
            PivotedRollerFollowerGeometry,
        )

        assembly = json.loads(encoded)
        preview = CinderGateway().scene_preview(assembly["geometry"])
        spec = decode_assembly_document(assembly)
        mechanism = next(
            (
                law.spec.mechanism_map
                for law in spec.pulleys.primary.actuator.force_laws
                if hasattr(getattr(law, "spec", None), "mechanism_map")
            ),
            None,
        )
        primary = None
        if mechanism is not None and hasattr(mechanism, "contact_at"):
            geometry = mechanism.geometry_spec
            surface = PivotedRollerFollowerGeometry(geometry)
            primary = FlyweightScene(
                count=mechanism.mass_geometry.number_of_flyweights,
                pivot_m=(geometry.pivot_axial_position, geometry.pivot_radius),
                roller_radius_m=geometry.roller_radius,
                roller_side_sign=geometry.roller_side_sign,
                ramp_points_m=[
                    surface.ramp_surface_point(
                        contact_coordinate=float(x), axial_position=0
                    )
                    for x in np.linspace(
                        geometry.ramp_profile.x_min, geometry.ramp_profile.x_max, 80
                    )
                ],
            )
        coupling = spec.pulleys.secondary.helical_coupling
        helix_points = []
        if coupling:
            profile = coupling.profile
            for q in np.linspace(
                profile.opening_travel_min, profile.opening_travel_max, 80
            ):
                theta = profile.evaluate(float(q)).theta
                helix_points.append(
                    (
                        profile.radius * float(np.cos(theta)),
                        profile.radius * float(np.sin(theta)),
                        float(q),
                    )
                )
        poses = []
        # Keep the seating transition as an exact interpolation knot; otherwise
        # the preview moves the secondary slightly while still in the deadzone.
        scene_shifts = np.unique(
            np.append(
                np.linspace(0, spec.geometry.spec.max_shift, 65),
                spec.geometry.spec.deadzone_shift,
            )
        )
        for shift in scene_shifts:
            geometry = spec.geometry.evaluate(float(shift))
            local = geometry.primary_axial_coordinate.value
            roller = (
                mechanism.contact_at(
                    float(
                        np.clip(
                            local,
                            mechanism.axial_position_min,
                            mechanism.axial_position_max,
                        )
                    )
                )
                if primary
                else None
            )
            angle = (
                coupling.evaluate_from_local_coordinate(
                    axial_position=geometry.secondary_axial_coordinate.value,
                    d_axial_position_ds=0,
                    d2_axial_position_ds2=0,
                ).theta
                if coupling
                else 0
            )
            contact_point = (
                surface.ramp_surface_point(
                    contact_coordinate=roller.contact_coordinate, axial_position=local
                )
                if roller
                else None
            )
            normal = (
                (
                    (roller.roller_center_axial_position - contact_point[0])
                    / mechanism.geometry_spec.roller_radius,
                    (roller.roller_center_radius - contact_point[1])
                    / mechanism.geometry_spec.roller_radius,
                )
                if roller
                else None
            )
            helix_local = (
                coupling.evaluate_from_local_coordinate(
                    axial_position=geometry.secondary_axial_coordinate.value,
                    d_axial_position_ds=1.0,
                    d2_axial_position_ds2=0.0,
                )
                if coupling
                else None
            )
            poses.append(
                MechanismPose(
                    shift_m=float(shift),
                    primary_contact_m=contact_point,
                    primary_normal_axial_radial=normal,
                    secondary_helix_dtheta_dx=helix_local.dtheta_ds
                    if helix_local
                    else None,
                    primary_roller_m=(
                        roller.roller_center_axial_position,
                        roller.roller_center_radius,
                    )
                    if roller
                    else None,
                    primary_ramp_shift_m=local,
                    secondary_axial_position_m=geometry.secondary_axial_coordinate.value,
                    secondary_angle_rad=angle,
                )
            )

        def movable_torque_fraction(pulley):
            shares = [
                law.spec.movable_member_torque_fraction
                for law in pulley.actuator.force_laws
                if hasattr(getattr(law, "spec", None), "movable_member_torque_fraction")
            ]
            # A rigidly guided pulley has symmetric face loading. A helical
            # element can explicitly configure its movable member's torque share.
            return sum(shares) if shares else 0.5

        preview.geometry.mechanisms = MechanismScene(
            primary=primary,
            primary_movable_torque_fraction=movable_torque_fraction(
                spec.pulleys.primary
            ),
            secondary_movable_torque_fraction=movable_torque_fraction(
                spec.pulleys.secondary
            ),
            primary_has_spring=any(
                component["kind"] == "axial_spring"
                for component in assembly["pulleys"]["primary"]["components"]
            ),
            secondary_has_spring=any(
                component["kind"] == "axial_spring"
                for component in assembly["pulleys"]["secondary"]["components"]
            ),
            secondary_helix_points_m=helix_points,
            poses=poses,
        )
        return preview

    def force_playback(self, assembly, result, scene=None):
        """Project retained signals and CINDER contact geometry; never integrate."""
        from cinder.results.fields import build_belt_tension_field

        from app.application.force_projection import project_forces

        scene = scene or self.assembly_scene(assembly).geometry
        tension = build_belt_tension_field(
            sheave_half_angle=scene.sheave_half_angle_rad
        )
        return project_forces(result, scene, tension)

    def geometry_from_endpoint_radii(
        self, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        context = self._geometry_context(_mapping(payload.get("context"), "context"))
        design = solve_geometry_from_endpoint_radii(
            EndpointRadiiDesignRequest(
                context=context,
                primary_outer_radius_at_zero_shift=_number(
                    payload, "primary_outer_radius_at_zero_shift_m"
                ),
                secondary_outer_radius_at_zero_shift=_number(
                    payload, "secondary_outer_radius_at_zero_shift_m"
                ),
            )
        )
        return self._project_geometry_design(design, payload)

    def geometry_from_target_ratios(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        context = self._geometry_context(_mapping(payload.get("context"), "context"))
        design = solve_geometry_from_target_ratios(
            TargetRatioDesignRequest(
                context=context,
                maximum_ratio=_number(payload, "maximum_ratio"),
                minimum_ratio=_number(payload, "minimum_ratio"),
            )
        )
        return self._project_geometry_design(design, payload)

    def clamping_response(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        assembly = decode_assembly_document(
            _mapping(payload.get("assembly_document"), "assembly_document")
        )
        closure = _mapping(payload.get("closure_unknowns", {}), "closure_unknowns")
        axes_payload = payload.get("axes")
        if not isinstance(axes_payload, list):
            raise ValueError("axes must be an array.")

        request = PulleyClampingForceStudyRequest(
            cvt=assembly,
            pulley=PulleyLocation(str(payload["pulley"])),
            point=ActuationOperatingPoint(
                # This API remains a static clamping map; time is therefore
                # explicitly fixed rather than hidden behind a context default.
                time=0.0,
                shift_position=_number(payload, "shift_position_m"),
                shaft_speed=_number(payload, "shaft_speed_rad_per_s"),
                shift_speed=_number(payload, "shift_speed_m_per_s"),
                closure_unknowns=ClosureUnknowns.from_components(
                    primary_angular_acceleration=_number(
                        closure, "primary_angular_acceleration_rad_per_s2", default=0.0
                    ),
                    secondary_angular_acceleration=_number(
                        closure,
                        "secondary_angular_acceleration_rad_per_s2",
                        default=0.0,
                    ),
                    belt_acceleration=_number(
                        closure, "belt_acceleration_m_per_s2", default=0.0
                    ),
                    shift_acceleration=_number(
                        closure, "shift_acceleration_m_per_s2", default=0.0
                    ),
                    primary_torque=_number(closure, "primary_torque_Nm", default=0.0),
                    secondary_torque=_number(
                        closure, "secondary_torque_Nm", default=0.0
                    ),
                    primary_normal_resultant=_number(
                        closure, "primary_normal_resultant_N", default=0.0
                    ),
                    secondary_normal_resultant=_number(
                        closure, "secondary_normal_resultant_N", default=0.0
                    ),
                ),
            ),
            axes=tuple(
                ActuationResponseAxis(
                    coordinate=_actuation_coordinate(_string(axis, "coordinate")),
                    values=_number_list(axis, "values"),
                )
                for axis in axes_payload
                if isinstance(axis, Mapping)
            ),
        )
        if len(request.axes) != len(axes_payload):
            raise ValueError("Each actuation axis must be an object.")
        return project_clamping_force_response(sample_pulley_clamping_force(request))

    @staticmethod
    def _geometry_context(payload: Mapping[str, Any]) -> GeometryDesignContext:
        belt_payload = _mapping(payload.get("belt"), "context.belt")
        return GeometryDesignContext(
            belt=BeltSectionSpec(
                height=_number(belt_payload, "height_m"),
                outer_width=_number(belt_payload, "outer_width_m"),
                inner_width=_number(belt_payload, "inner_width_m"),
                cord_depth_from_outer=_number(belt_payload, "cord_depth_from_outer_m"),
            ),
            belt_outer_length=_number(payload, "belt_outer_length_m"),
            sheave_half_angle=_number(payload, "sheave_half_angle_rad"),
            deadzone_shift=_number(payload, "deadzone_shift_m"),
            max_shift=_number(payload, "max_shift_m"),
        )

    @staticmethod
    def _project_geometry_design(
        design: object, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        sample_count = int(payload.get("sample_count", 301))
        result: dict[str, Any] = {
            "contract_version": 1,
            "kind": "geometry_design_response",
            "summary": project_geometry_summary(summarize_geometry_design(design)),
            "path": project_geometry_path(
                sample_geometry_path(design, sample_count=sample_count)
            ),
            "feasibility": project_geometry_feasibility(
                evaluate_geometry_feasibility(
                    design,
                    minimum_primary_wrap_angle=_optional_number(
                        payload, "minimum_primary_wrap_angle_rad"
                    ),
                    minimum_secondary_wrap_angle=_optional_number(
                        payload, "minimum_secondary_wrap_angle_rad"
                    ),
                )
            ),
        }
        sampling = payload.get("field_sampling")
        if sampling is not None:
            field = _mapping(sampling, "field_sampling")
            primary_axis = np.asarray(
                _number_list(field, "primary_outer_radius_m"), dtype=float
            )
            secondary_axis = np.asarray(
                _number_list(field, "secondary_outer_radius_m"), dtype=float
            )
            geometry_spec = design.geometry_spec
            result["radius_plane"] = project_radius_plane(
                evaluate_radius_plane(
                    belt=geometry_spec.belt,
                    center_distance=design.center_distance,
                    primary_outer_radius=primary_axis,
                    secondary_outer_radius=secondary_axis,
                )
            )
            result["ratio_sensitivity"] = project_ratio_sensitivity_field(
                evaluate_ratio_sensitivity_field(
                    belt=geometry_spec.belt,
                    center_distance=design.center_distance,
                    sheave_half_angle=geometry_spec.sheave_half_angle,
                    primary_outer_radius=primary_axis,
                    secondary_outer_radius=secondary_axis,
                )
            )
        return result


def _actuation_coordinate(value: str) -> ActuationStateCoordinate | ClosureUnknown:
    state_coordinates = {
        "shift_position": ActuationStateCoordinate.SHIFT_POSITION,
        "shaft_speed": ActuationStateCoordinate.SHAFT_SPEED,
        "shift_speed": ActuationStateCoordinate.SHIFT_SPEED,
    }
    closure_coordinates = {
        "primary_angular_acceleration": ClosureUnknown.PRIMARY_ANGULAR_ACCELERATION,
        "secondary_angular_acceleration": ClosureUnknown.SECONDARY_ANGULAR_ACCELERATION,
        "belt_acceleration": ClosureUnknown.BELT_ACCELERATION,
        "shift_acceleration": ClosureUnknown.SHIFT_ACCELERATION,
        "primary_torque": ClosureUnknown.PRIMARY_TORQUE,
        "secondary_torque": ClosureUnknown.SECONDARY_TORQUE,
        "primary_normal_resultant": ClosureUnknown.PRIMARY_NORMAL_RESULTANT,
        "secondary_normal_resultant": ClosureUnknown.SECONDARY_NORMAL_RESULTANT,
    }
    try:
        return state_coordinates[value]
    except KeyError:
        try:
            return closure_coordinates[value]
        except KeyError as error:
            choices = sorted([*state_coordinates, *closure_coordinates])
            raise ValueError(
                f"Unsupported actuation coordinate {value!r}; choose one of {choices}."
            ) from error


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object.")
    return value


def _string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string.")
    return value


def _number(
    payload: Mapping[str, Any],
    key: str,
    *,
    default: float | None = None,
) -> float:
    if key not in payload:
        if default is not None:
            return default
        raise ValueError(f"{key} is required.")
    value = payload[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number.")
    return float(value)


def _optional_number(payload: Mapping[str, Any], key: str) -> float | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number or null.")
    return float(value)


def _number_list(payload: Mapping[str, Any], key: str) -> list[float]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{key} must be an array.")
    numbers: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(f"{key} must contain only numbers.")
        numbers.append(float(item))
    return numbers
