"""Minimal static geometry design solvers and numeric field evaluators."""

from .feasibility import evaluate_geometry_feasibility
from .fields import evaluate_radius_plane, evaluate_ratio_sensitivity_field
from .path import sample_geometry_path, summarize_geometry_design
from .solve import (
    solve_geometry_from_endpoint_radii,
    solve_geometry_from_target_ratios,
)
from .types import (
    EndpointRadiiDesignRequest,
    GeometryDesignContext,
    GeometryDesignInfeasibleError,
    GeometryDesignSummary,
    GeometryEndpoint,
    GeometryFeasibilityIssue,
    GeometryFeasibilityReport,
    GeometryPathTable,
    RadiusPlaneField,
    RatioSensitivityField,
    ResolvedGeometryDesign,
    TargetRatioDesignRequest,
)

__all__ = [
    "EndpointRadiiDesignRequest",
    "GeometryDesignContext",
    "GeometryDesignInfeasibleError",
    "GeometryDesignSummary",
    "GeometryEndpoint",
    "GeometryFeasibilityIssue",
    "GeometryFeasibilityReport",
    "GeometryPathTable",
    "RadiusPlaneField",
    "RatioSensitivityField",
    "ResolvedGeometryDesign",
    "TargetRatioDesignRequest",
    "evaluate_geometry_feasibility",
    "evaluate_radius_plane",
    "evaluate_ratio_sensitivity_field",
    "sample_geometry_path",
    "solve_geometry_from_endpoint_radii",
    "solve_geometry_from_target_ratios",
    "summarize_geometry_design",
]
