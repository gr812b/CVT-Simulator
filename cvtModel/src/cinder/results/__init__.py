"""Trace, inspection, and post-integration reporting APIs for CINDER."""

from .inspection import CVTStateInspection, GeometryInspection, inspect_cvt_state
from .reporting import (
    DEFAULT_REPORT_TIME_STEP_SECONDS,
    CVTIntegrationResult,
    CVTReportedSegment,
    CVTResultBuilder,
    CVTResultSummary,
    NumericSignal,
    ReportingGrid,
    ReportingSettings,
)
from .trace import CVTIntegrationTrace
from .fields import (
    BoundSpatialDomain,
    BoundSpatialField,
    FieldExpression,
    SpatialDomainDefinition,
    SpatialDomainSample,
    SpatialFieldDefinition,
    SpatialFieldSample,
    SpatialFieldSeries,
    SpatialRegionDefinition,
)

__all__ = [
    "BoundSpatialDomain",
    "BoundSpatialField",
    "FieldExpression",
    "SpatialDomainDefinition",
    "SpatialDomainSample",
    "SpatialFieldDefinition",
    "SpatialFieldSample",
    "SpatialFieldSeries",
    "SpatialRegionDefinition",
    "CVTIntegrationResult",
    "DEFAULT_REPORT_TIME_STEP_SECONDS",
    "CVTIntegrationTrace",
    "CVTReportedSegment",
    "CVTResultBuilder",
    "CVTResultSummary",
    "CVTStateInspection",
    "GeometryInspection",
    "NumericSignal",
    "ReportingGrid",
    "ReportingSettings",
    "inspect_cvt_state",
]
