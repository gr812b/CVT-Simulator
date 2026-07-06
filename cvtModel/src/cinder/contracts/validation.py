"""Assembly-level preflight validation for external CINDER users.

Assembly constructors keep hard mathematical invariants.  This module adds
engineering-facing checks that are useful before a study or simulation run:
profile travel coverage, springs leaving compression, optional wrap thresholds,
and explicit model-scope warnings.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
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

    def as_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "location": self.location,
        }


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
    if assembly.contact.friction_coefficient == 0.0:
        findings.append(
            _warning(
                "contact.zero_friction_coefficient",
                "The contact friction coefficient is zero, so traction capacity will be zero.",
                "contact.friction_coefficient",
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
        pulley=assembly.pulleys.input,
        location="pulleys.input",
        local_positions=tuple(
            point.primary_axial_coordinate.value for point in endpoints
        ),
        opening_travels=None,
        findings=findings,
    )
    _validate_pulley(
        pulley=assembly.pulleys.output,
        location="pulleys.output",
        local_positions=tuple(
            point.secondary_axial_coordinate.value for point in endpoints
        ),
        opening_travels=tuple(
            assembly.pulleys.output.helical_coupling.opening_offset
            + assembly.pulleys.output.helical_coupling.opening_per_axial_position
            * point.secondary_axial_coordinate.value
            for point in endpoints
        ),
        findings=findings,
    )

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
                        "Helix profile does not cover the output pulley opening-travel range.",
                        law_location,
                    )
                )


def _warning(code: str, message: str, location: str) -> ValidationFinding:
    return ValidationFinding("warning", code, message, location)


def _error(code: str, message: str, location: str) -> ValidationFinding:
    return ValidationFinding("error", code, message, location)
