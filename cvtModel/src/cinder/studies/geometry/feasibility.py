"""Structured checks for resolved static geometry designs."""

from __future__ import annotations

from math import isfinite

from .types import (
    GeometryFeasibilityIssue,
    GeometryFeasibilityReport,
    ResolvedGeometryDesign,
)


def evaluate_geometry_feasibility(
    design: ResolvedGeometryDesign,
    *,
    minimum_primary_wrap_angle: float | None = None,
    minimum_secondary_wrap_angle: float | None = None,
) -> GeometryFeasibilityReport:
    """Evaluate optional wrap-angle requirements for one resolved design.

    Construction already guarantees the model's hard geometric conditions:
    belt closure, non-overlapping pulley envelopes, positive effective radii,
    and physical belt containment. This function therefore reports optional
    engineering warnings rather than repeating construction-time validation.
    """

    _validate_optional_threshold(
        "minimum_primary_wrap_angle", minimum_primary_wrap_angle
    )
    _validate_optional_threshold(
        "minimum_secondary_wrap_angle", minimum_secondary_wrap_angle
    )

    issues: list[GeometryFeasibilityIssue] = []
    maximum = design.maximum_ratio_endpoint
    minimum = design.minimum_ratio_endpoint

    if minimum_primary_wrap_angle is not None:
        endpoint = min(
            (maximum, minimum),
            key=lambda value: value.primary_wrap_angle,
        )
        if endpoint.primary_wrap_angle < minimum_primary_wrap_angle:
            issues.append(
                GeometryFeasibilityIssue(
                    code="primary_wrap_angle_below_threshold",
                    severity="warning",
                    message=(
                        "Primary wrap angle falls below the supplied design "
                        "threshold."
                    ),
                    shift=endpoint.shift,
                )
            )

    if minimum_secondary_wrap_angle is not None:
        endpoint = min(
            (maximum, minimum),
            key=lambda value: value.secondary_wrap_angle,
        )
        if endpoint.secondary_wrap_angle < minimum_secondary_wrap_angle:
            issues.append(
                GeometryFeasibilityIssue(
                    code="secondary_wrap_angle_below_threshold",
                    severity="warning",
                    message=(
                        "Secondary wrap angle falls below the supplied design "
                        "threshold."
                    ),
                    shift=endpoint.shift,
                )
            )

    return GeometryFeasibilityReport(
        is_feasible=not any(issue.severity == "error" for issue in issues),
        issues=tuple(issues),
    )


def _validate_optional_threshold(name: str, value: float | None) -> None:
    if value is None:
        return
    if not isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be finite and positive when supplied.")
