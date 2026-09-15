"""Application service for the isolated fixed-pivot primary design tool."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from math import degrees, pi
from threading import RLock
from uuid import uuid4

from .architecture import analyze_architecture_workspace
from .cinder_adapter import (
    GeometryAnalysis,
    analyze_geometry,
    evaluate_response,
    requested_ramp_surface,
)
from .models import ArchitectureDesign, OperatingCondition, PackagingZone, RampDesign

INCH = 0.0254
MM = 1.0e-3
RPM_TO_RAD_PER_SECOND = 2.0 * pi / 60.0


class PrimaryDesignError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


@dataclass(frozen=True, slots=True)
class CachedConcreteAnalysis:
    analysis_id: str
    geometry: GeometryAnalysis


class FixedPivotPrimaryDesignService:
    """Own architecture/packaging analysis and cached concrete-design mechanics."""

    def __init__(self, *, max_cached_analyses: int = 32) -> None:
        self._max_cached_analyses = max_cached_analyses
        self._cache: OrderedDict[str, CachedConcreteAnalysis] = OrderedDict()
        self._lock = RLock()

    def defaults(self) -> dict[str, object]:
        architecture = ArchitectureDesign(
            pivot_axial_position_m=0.0,
            pivot_radius_m=1.675 * INCH,
            arm_length_m=1.241 * INCH,
            roller_radius_m=6.5 * MM,
            required_travel_m=0.75 * INCH,
            number_of_flyweights=3,
            arm_mass_per_flyweight_kg=13.646e-3,
            ramp_axial_direction=-1,
            roller_side_sign=1,
            max_tip_mass_per_flyweight_kg=0.650,
        )
        ramp = RampDesign(
            kind="progressive",
            anchor_axial_from_pivot_m=1.5 * INCH,
            anchor_radial_from_pivot_m=0.2776 * INCH,
            linear_angle_deg=35.0,
            circular_start_angle_deg=35.0,
            circular_end_angle_deg=20.0,
            constant_length_m=38.0 * MM,
            linear_length_m=5.0 * MM,
            blend_length_m=3.0 * MM,
            circular_length_m=30.0 * MM,
        )
        return {
            "architecture": _architecture_document(architecture),
            "ramp": _ramp_document(ramp),
            "packaging_zones": [],
            "operating": {
                "tip_mass_per_flyweight_kg": 0.250,
                "shaft_speed_rad_s": 3800.0 * RPM_TO_RAD_PER_SECOND,
                "shift_speed_m_s": 0.0,
                "shift_acceleration_m_s2": 0.0,
            },
            "ui_limits": {
                "tip_mass_per_flyweight_kg": [0.0, 0.650],
                "shaft_speed_rad_s": [0.0, 6000.0 * RPM_TO_RAD_PER_SECOND],
            },
        }

    def analyze_architecture(
        self,
        *,
        architecture: ArchitectureDesign,
        ramp: RampDesign,
        zones: tuple[PackagingZone, ...],
        reach_sample_count: int = 361,
    ) -> dict[str, object]:
        """Analyze architecture reach and polygonal packaging constraints.

        No design search happens here.  The result is the deterministic
        workspace used by the Phase 2 editor and later by the architecture
        explorer.
        """

        try:
            ramp_x, ramp_r = requested_ramp_surface(
                architecture,
                ramp,
                sample_count=max(161, min(501, reach_sample_count)),
            )
            workspace = analyze_architecture_workspace(
                architecture,
                zones,
                ramp_surface_open_x_m=ramp_x,
                ramp_surface_open_r_m=ramp_r,
                reach_sample_count=reach_sample_count,
            )
        except (TypeError, ValueError, RuntimeError) as error:
            raise PrimaryDesignError(
                "INVALID_ARCHITECTURE_WORKSPACE",
                str(error),
            ) from error

        return {
            "architecture": _architecture_document(architecture),
            "ramp": _ramp_document(ramp),
            "zones": [_zone_document(zone) for zone in zones],
            **workspace,
        }

    def analyze_concrete(
        self,
        *,
        architecture: ArchitectureDesign,
        ramp: RampDesign,
        sample_count: int = 161,
    ) -> dict[str, object]:
        try:
            geometry = analyze_geometry(
                architecture,
                ramp,
                sample_count=sample_count,
            )
        except (TypeError, ValueError, RuntimeError) as error:
            raise PrimaryDesignError(
                "INVALID_CONTACT_GEOMETRY",
                str(error),
            ) from error

        analysis_id = uuid4().hex
        cached = CachedConcreteAnalysis(
            analysis_id=analysis_id,
            geometry=geometry,
        )
        self._store(cached)

        validity = _validity_document(geometry)
        fields: dict[str, list[float | int]] = {
            "arm_angle_deg": [degrees(point.angle_rad) for point in geometry.points],
            "angle_gradient_rad_per_m": [
                point.angle_gradient_rad_per_m for point in geometry.points
            ],
            "angle_curvature_rad_per_m2": [
                point.angle_curvature_rad_per_m2 for point in geometry.points
            ],
            "roller_center_x_m": [point.roller_center_x_m for point in geometry.points],
            "roller_center_r_m": [point.roller_center_r_m for point in geometry.points],
            "contact_x_m": [point.contact_x_m for point in geometry.points],
            "contact_r_m": [point.contact_r_m for point in geometry.points],
            "contact_coordinate_m": [point.contact_coordinate_m for point in geometry.points],
            "ramp_tangent_deg": [point.ramp_tangent_deg for point in geometry.points],
            "ramp_normal_x": [point.ramp_normal_x for point in geometry.points],
            "ramp_normal_r": [point.ramp_normal_r for point in geometry.points],
            "admissible": [1 if point.angle_rad <= 0.5 * pi + 1.0e-10 else 0 for point in geometry.points],
        }
        units = {
            "arm_angle_deg": "deg",
            "angle_gradient_rad_per_m": "rad/m",
            "angle_curvature_rad_per_m2": "rad/m^2",
            "roller_center_x_m": "m",
            "roller_center_r_m": "m",
            "contact_x_m": "m",
            "contact_r_m": "m",
            "contact_coordinate_m": "m",
            "ramp_tangent_deg": "deg",
            "ramp_normal_x": "1",
            "ramp_normal_r": "1",
            "admissible": "1",
        }

        endpoint_margins = [
            min(
                point.contact_coordinate_m - geometry.ramp.x_min,
                geometry.ramp.x_max - point.contact_coordinate_m,
            )
            for point in geometry.points
        ]
        max_q = (
            max(degrees(point.angle_rad) for point in geometry.points)
            if geometry.points
            else None
        )

        return {
            "analysis_id": analysis_id,
            "validity": validity,
            "architecture": _architecture_document(architecture),
            "ramp": _ramp_document(ramp),
            "requested_travel_m": geometry.requested_travel_m,
            "contact_valid_travel_m": geometry.contact_valid_travel_m,
            "geometry": {
                "axis_key": "shift_m",
                "axis_unit": "m",
                "axis_values": [point.shift_m for point in geometry.points],
                "units": units,
                "fields": fields,
            },
            "ramp_surface_open": {
                "x_m": list(geometry.ramp_surface_open_x_m),
                "r_m": list(geometry.ramp_surface_open_r_m),
            },
            "summary": {
                "max_arm_angle_deg": max_q,
                "q90_margin_deg": None if max_q is None else 90.0 - max_q,
                "minimum_ramp_endpoint_margin_m": (
                    min(endpoint_margins) if endpoint_margins else None
                ),
                "contact_valid_fraction": (
                    geometry.contact_valid_travel_m / geometry.requested_travel_m
                ),
                "runtime_map_compiled": geometry.runtime_map_compiled,
            },
        }

    def evaluate_concrete_response(
        self,
        *,
        analysis_id: str,
        operating: OperatingCondition,
    ) -> dict[str, object]:
        cached = self._get(analysis_id)
        try:
            fields = evaluate_response(cached.geometry, operating)
        except (TypeError, ValueError, RuntimeError) as error:
            raise PrimaryDesignError(
                "OPERATING_CONDITION_INVALID",
                str(error),
            ) from error

        units = {
            "flyweight_centrifugal_force_N": "N",
            "flyweight_axial_inertia_force_N": "N",
            "flyweight_curvature_force_N": "N",
            "flyweight_total_closing_force_N": "N",
            "ramp_force_normal_N": "N",
            "ramp_force_axial_N": "N",
            "ramp_force_radial_N": "N",
            "ramp_moment_about_anchor_Nm": "N*m",
            "com_x_m": "m",
            "com_r_m": "m",
            "equivalent_centrifugal_force_N": "N",
            "pivot_reaction_axial_N": "N",
            "pivot_reaction_radial_N": "N",
            "pivot_reaction_tangential_N": "N",
            "pivot_reaction_resultant_N": "N",
            "compressive_contact": "bool",
        }
        return {
            "analysis_id": analysis_id,
            "operating": {
                "tip_mass_per_flyweight_kg": operating.tip_mass_per_flyweight_kg,
                "shaft_speed_rad_s": operating.shaft_speed_rad_s,
                "shift_speed_m_s": operating.shift_speed_m_s,
                "shift_acceleration_m_s2": operating.shift_acceleration_m_s2,
            },
            "loads": {
                "axis_key": "shift_m",
                "axis_unit": "m",
                "axis_values": [point.shift_m for point in cached.geometry.points],
                "units": units,
                "fields": fields,
            },
        }

    def _store(self, cached: CachedConcreteAnalysis) -> None:
        with self._lock:
            self._cache[cached.analysis_id] = cached
            self._cache.move_to_end(cached.analysis_id)
            while len(self._cache) > self._max_cached_analyses:
                self._cache.popitem(last=False)

    def _get(self, analysis_id: str) -> CachedConcreteAnalysis:
        with self._lock:
            cached = self._cache.get(analysis_id)
            if cached is None:
                raise PrimaryDesignError(
                    "ANALYSIS_EXPIRED",
                    "The concrete design analysis is no longer cached; analyze the geometry again.",
                )
            self._cache.move_to_end(analysis_id)
            return cached


def _validity_document(geometry: GeometryAnalysis) -> dict[str, object]:
    warnings: list[dict[str, object]] = []

    if geometry.runtime_map_compile_error is not None:
        warnings.append(
            {
                "code": "RUNTIME_MAP_COMPILE_FAILED",
                "message": (
                    "The exact contact branch is usable for this design inspection, "
                    "but CINDER's compiled runtime q(x) spline could not preserve "
                    "a positive motion ratio. The exact branch is shown instead."
                ),
                "shift_m": None,
                "detail": geometry.runtime_map_compile_error,
            }
        )

    if not geometry.contact_range_complete:
        failure: dict[str, object] = {
            "code": geometry.failure_code or "CONTACT_BRANCH_INVALID",
            "message": geometry.failure_message
            or "The selected roller/ramp branch cannot complete the required travel.",
            "shift_m": geometry.failure_shift_m,
        }
        if geometry.double_contact_event is not None:
            event = geometry.double_contact_event
            failure["geometry"] = {
                "kind": "double_contact",
                "arm_angle_deg": degrees(event.angle_rad),
                "roller_center_x_m": event.roller_center_x_m,
                "roller_center_r_m": event.roller_center_r_m,
                "contacts": [
                    {
                        "label": "C1",
                        "contact_coordinate_m": event.contact_coordinate_1_m,
                        "x_m": event.contact_x_1_m,
                        "r_m": event.contact_r_1_m,
                    },
                    {
                        "label": "C2",
                        "contact_coordinate_m": event.contact_coordinate_2_m,
                        "x_m": event.contact_x_2_m,
                        "r_m": event.contact_r_2_m,
                    },
                ],
            }
        return {
            "valid": False,
            "failure": failure,
            "warnings": warnings,
        }

    for point in geometry.points:
        if point.angle_rad > 0.5 * pi + 1.0e-10:
            return {
                "valid": False,
                "failure": {
                    "code": "Q_EXCEEDS_90",
                    "message": "The flyweight arm would deploy past 90 degrees.",
                    "shift_m": point.shift_m,
                },
                "warnings": warnings,
            }

    max_q_deg = (
        max(degrees(point.angle_rad) for point in geometry.points)
        if geometry.points
        else None
    )
    if max_q_deg is not None and max_q_deg >= 88.0:
        warnings.append(
            {
                "code": "Q_NEAR_90",
                "message": "The flyweight approaches the 90 degree deployment limit.",
                "shift_m": geometry.points[-1].shift_m,
            }
        )

    if geometry.points:
        endpoint_margin = min(
            min(
                point.contact_coordinate_m - geometry.ramp.x_min,
                geometry.ramp.x_max - point.contact_coordinate_m,
            )
            for point in geometry.points
        )
        if endpoint_margin < 1.0e-3:
            warnings.append(
                {
                    "code": "RAMP_ENDPOINT_MARGIN_LOW",
                    "message": "The selected contact branch approaches a physical ramp endpoint.",
                    "shift_m": None,
                }
            )

    return {"valid": True, "failure": None, "warnings": warnings}


def _architecture_document(value: ArchitectureDesign) -> dict[str, object]:
    return {
        "pivot_axial_position_m": value.pivot_axial_position_m,
        "pivot_radius_m": value.pivot_radius_m,
        "arm_length_m": value.arm_length_m,
        "roller_radius_m": value.roller_radius_m,
        "required_travel_m": value.required_travel_m,
        "number_of_flyweights": value.number_of_flyweights,
        "arm_mass_per_flyweight_kg": value.arm_mass_per_flyweight_kg,
        "ramp_axial_direction": value.ramp_axial_direction,
        "roller_side_sign": value.roller_side_sign,
        "max_tip_mass_per_flyweight_kg": value.max_tip_mass_per_flyweight_kg,
    }


def _ramp_document(value: RampDesign) -> dict[str, object]:
    return {
        "kind": value.kind,
        "anchor_axial_from_pivot_m": value.anchor_axial_from_pivot_m,
        "anchor_radial_from_pivot_m": value.anchor_radial_from_pivot_m,
        "linear_angle_deg": value.linear_angle_deg,
        "circular_start_angle_deg": value.circular_start_angle_deg,
        "circular_end_angle_deg": value.circular_end_angle_deg,
        "constant_length_m": value.constant_length_m,
        "linear_length_m": value.linear_length_m,
        "blend_length_m": value.blend_length_m,
        "circular_length_m": value.circular_length_m,
    }

def _zone_document(value: PackagingZone) -> dict[str, object]:
    return {
        "id": value.id,
        "label": value.label,
        "subject": value.subject,
        "rule": value.rule,
        "polygon_m": [[point[0], point[1]] for point in value.polygon_m],
        "clearance_m": value.clearance_m,
    }

