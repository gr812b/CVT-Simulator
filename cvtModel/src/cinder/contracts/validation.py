"""Assembly-level preflight validation for external CINDER users.

Assembly constructors keep hard mathematical invariants.  This module adds
engineering-facing checks that are useful before a study or simulation run:
profile travel coverage, springs leaving compression, optional wrap thresholds,
and explicit model-scope warnings.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
import re
from typing import Literal

from cinder.model.cvt.actuation import (
    AxialSpringForce,
    CentrifugalRampForce,
    HelicalTorqueReactionForce,
)
from cinder.model.system import CVTAssemblySpec, PulleySpec


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    """One stable, display-neutral assembly validation result."""

    severity: Literal["error", "warning"]
    code: str
    message: str
    location: str
    document_path: str | None = None

    def as_dict(self) -> dict[str, str]:
        payload = {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "location": self.location,
        }
        if self.document_path is not None:
            payload["document_path"] = self.document_path
        return payload


@dataclass(frozen=True, slots=True)
class AssemblyValidationOptions:
    """Optional engineering thresholds; omitted values apply no threshold."""

    minimum_primary_wrap_angle_rad: float | None = None
    minimum_secondary_wrap_angle_rad: float | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("minimum_primary_wrap_angle_rad", self.minimum_primary_wrap_angle_rad),
            ("minimum_secondary_wrap_angle_rad", self.minimum_secondary_wrap_angle_rad),
        ):
            if value is not None and (not isfinite(value) or value <= 0.0):
                raise ValueError(f"{name} must be finite and positive when supplied.")


@dataclass(frozen=True, slots=True)
class AssemblyValidationReport:
    """Structured preflight findings without a UI or transport dependency."""

    is_valid: bool
    findings: tuple[ValidationFinding, ...]

    @property
    def errors(self) -> tuple[ValidationFinding, ...]:
        return tuple(item for item in self.findings if item.severity == "error")

    @property
    def warnings(self) -> tuple[ValidationFinding, ...]:
        return tuple(item for item in self.findings if item.severity == "warning")

    def as_dict(self) -> dict[str, object]:
        return {
            "is_valid": self.is_valid,
            "findings": [finding.as_dict() for finding in self.findings],
        }


def validate_assembly(
    assembly: CVTAssemblySpec,
    *,
    options: AssemblyValidationOptions | None = None,
    document_path_prefix: str | None = None,
) -> AssemblyValidationReport:
    """Validate an already constructed CVT assembly for common design hazards.

    This is intentionally non-mutating and does not duplicate constructor
    checks.  An assembly that reaches this function is already mathematically
    constructible; findings call out the most likely run-time/profile and
    engineering issues a frontend should show before a simulation starts.
    """

    if not isinstance(assembly, CVTAssemblySpec):
        raise TypeError("assembly must be a CVTAssemblySpec.")
    options = AssemblyValidationOptions() if options is None else options
    if not isinstance(options, AssemblyValidationOptions):
        raise TypeError("options must be an AssemblyValidationOptions instance.")

    findings: list[ValidationFinding] = []
    geometry = assembly.geometry
    spec = geometry.spec
    endpoints = (geometry.evaluate(0.0), geometry.evaluate(spec.max_shift))

    if spec.max_shift == spec.deadzone_shift:
        findings.append(
            _warning(
                "geometry.no_active_shift_travel",
                "The geometry has no active shift travel after the primary deadzone.",
                "geometry",
            )
        )
    if assembly.contact.static_friction_coefficient == 0.0:
        findings.append(
            _warning(
                "contact.zero_friction_coefficient",
                "The contact friction coefficient is zero, so traction capacity will be zero.",
                "contact.static_friction_coefficient",
            )
        )

    if options.minimum_primary_wrap_angle_rad is not None:
        minimum = min(point.primary_wrap_angle for point in endpoints)
        if minimum < options.minimum_primary_wrap_angle_rad:
            findings.append(
                _warning(
                    "geometry.primary_wrap_below_threshold",
                    "Primary wrap angle falls below the supplied engineering threshold.",
                    "geometry.primary_wrap_angle",
                )
            )
    if options.minimum_secondary_wrap_angle_rad is not None:
        minimum = min(point.secondary_wrap_angle for point in endpoints)
        if minimum < options.minimum_secondary_wrap_angle_rad:
            findings.append(
                _warning(
                    "geometry.secondary_wrap_below_threshold",
                    "Secondary wrap angle falls below the supplied engineering threshold.",
                    "geometry.secondary_wrap_angle",
                )
            )

    _validate_pulley(
        pulley=assembly.pulleys.primary,
        location="pulleys.primary",
        local_positions=tuple(
            point.primary_axial_coordinate.value for point in endpoints
        ),
        opening_travels=(
            tuple(
                assembly.pulleys.primary.helical_coupling.opening_offset
                + assembly.pulleys.primary.helical_coupling.opening_per_axial_position
                * point.primary_axial_coordinate.value
                for point in endpoints
            )
            if assembly.pulleys.primary.helical_coupling is not None
            else None
        ),
        findings=findings,
    )
    _validate_pulley(
        pulley=assembly.pulleys.secondary,
        location="pulleys.secondary",
        local_positions=tuple(
            point.secondary_axial_coordinate.value for point in endpoints
        ),
        opening_travels=(
            tuple(
                assembly.pulleys.secondary.helical_coupling.opening_offset
                + assembly.pulleys.secondary.helical_coupling.opening_per_axial_position
                * point.secondary_axial_coordinate.value
                for point in endpoints
            )
            if assembly.pulleys.secondary.helical_coupling is not None
            else None
        ),
        findings=findings,
    )

    if document_path_prefix is not None:
        findings = [
            replace(
                finding,
                document_path=_document_path_for_location(
                    finding.location, prefix=document_path_prefix
                ),
            )
            for finding in findings
        ]

    return AssemblyValidationReport(
        is_valid=not any(item.severity == "error" for item in findings),
        findings=tuple(findings),
    )


def _validate_pulley(
    *,
    pulley: PulleySpec,
    location: str,
    local_positions: tuple[float, float],
    opening_travels: tuple[float, float] | None,
    findings: list[ValidationFinding],
) -> None:
    local_min, local_max = min(local_positions), max(local_positions)
    for index, force_law in enumerate(pulley.actuator.force_laws):
        law_location = f"{location}.components[{index}]"
        if isinstance(force_law, CentrifugalRampForce):
            profile = force_law.spec.radial_displacement_profile
            if profile.x_min > local_min or profile.x_max < local_max:
                findings.append(
                    _error(
                        "actuation.profile_does_not_cover_local_travel",
                        "Centrifugal-ramp profile does not cover the pulley local travel range.",
                        law_location,
                    )
                )
        if isinstance(force_law, AxialSpringForce):
            spec = force_law.spec
            compression_values = tuple(
                spec.initial_compression + spec.compression_per_axial_position * value
                for value in local_positions
            )
            if min(compression_values) < 0.0:
                findings.append(
                    _warning(
                        "actuation.spring_leaves_compression",
                        "An axial compression spring becomes tensile over part of the available travel.",
                        law_location,
                    )
                )
        if isinstance(force_law, HelicalTorqueReactionForce):
            if pulley.helical_coupling is None or opening_travels is None:
                findings.append(
                    _error(
                        "actuation.helix_coupling_missing",
                        "Helical torque reaction requires a matching helical coupling.",
                        law_location,
                    )
                )
                continue
            profile = pulley.helical_coupling.profile
            opening_min, opening_max = min(opening_travels), max(opening_travels)
            if (
                profile.opening_travel_min > opening_min
                or profile.opening_travel_max < opening_max
            ):
                findings.append(
                    _error(
                        "actuation.helix_profile_does_not_cover_opening_travel",
                        "Helix profile does not cover the pulley opening-travel range.",
                        law_location,
                    )
                )


def _warning(code: str, message: str, location: str) -> ValidationFinding:
    return ValidationFinding("warning", code, message, location)


def _error(code: str, message: str, location: str) -> ValidationFinding:
    return ValidationFinding("error", code, message, location)


def validate_assembly_document(
    document: object,
    *,
    options: AssemblyValidationOptions | None = None,
) -> AssemblyValidationReport:
    """Validate one serialized assembly document with JSON-pointer findings.

    Decoding remains the single source of constructor truth.  A malformed
    document returns a structured error rather than leaking an exception into
    a backend route; a successfully decoded document receives the normal
    engineering preflight checks.
    """

    from .document import DesignDocumentError, decode_assembly_document

    try:
        assembly = decode_assembly_document(document)
    except (DesignDocumentError, TypeError, ValueError) as error:
        return AssemblyValidationReport(
            is_valid=False,
            findings=(
                ValidationFinding(
                    severity="error",
                    code="document.decode_error",
                    message=str(error),
                    location="document",
                    document_path="",
                ),
            ),
        )
    return validate_assembly(assembly, options=options, document_path_prefix="")


def validate_simulation_case_document(
    document: object,
    *,
    options: AssemblyValidationOptions | None = None,
) -> AssemblyValidationReport:
    """Validate a full public simulation document with document-path findings."""

    from .simulation_document import (
        DecodedSimulationCase,
        decode_simulation_case_document,
    )

    try:
        decoded: DecodedSimulationCase = decode_simulation_case_document(document)
    except (TypeError, ValueError) as error:
        return AssemblyValidationReport(
            is_valid=False,
            findings=(
                ValidationFinding(
                    severity="error",
                    code="document.decode_error",
                    message=str(error),
                    location="document",
                    document_path="",
                ),
            ),
        )

    return validate_assembly(
        decoded.assembly,
        options=options,
        document_path_prefix="/assembly",
    )


def _document_path_for_location(location: str, *, prefix: str) -> str:
    """Map stable validation locations to a concrete public JSON Pointer."""

    root = prefix.rstrip("/")
    if location == "geometry" or location.startswith("geometry."):
        if (
            location == "geometry.primary_wrap_angle"
            or location == "geometry.secondary_wrap_angle"
        ):
            return f"{root}/geometry"
        return f"{root}/" + location.replace(".", "/")
    if location.startswith("contact."):
        return f"{root}/" + location.replace(".", "/")
    match = re.fullmatch(r"pulleys\.(primary|secondary)\.components\[(\d+)\]", location)
    if match is not None:
        return f"{root}/pulleys/{match.group(1)}/components/{match.group(2)}"
    return root or ""
