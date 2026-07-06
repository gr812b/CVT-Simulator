"""Stable external contracts layered over CINDER's mechanics-first core.

These helpers are optional adapters for saved designs, backend transport,
validation, standardized result projection, and cross-run metrics.  The core
model and execution modules deliberately do not depend on them.
"""

from .catalog import (
    ComponentDescriptor,
    ComponentParameter,
    component_catalog,
    component_catalog_document,
)
from .conventions import (
    PUBLIC_CONTRACT_VERSION,
    PublicConventions,
    PublicFieldDescriptor,
    describe_public_field,
    public_conventions,
)
from .document import (
    ASSEMBLY_DOCUMENT_TYPE,
    DesignDocumentError,
    UnsupportedDesignDocumentError,
    decode_assembly_document,
    encode_assembly_document,
)
from .projection import (
    project_assembly_validation,
    project_clamping_force_response,
    project_geometry_feasibility,
    project_geometry_path,
    project_geometry_summary,
    project_radius_plane,
    project_ratio_sensitivity_field,
    project_simulation_result,
    to_jsonable,
)
from .simulation import SimulationMetrics, summarize_simulation
from .validation import (
    AssemblyValidationOptions,
    AssemblyValidationReport,
    ValidationFinding,
    validate_assembly,
)

__all__ = [
    "ASSEMBLY_DOCUMENT_TYPE",
    "AssemblyValidationOptions",
    "AssemblyValidationReport",
    "ComponentDescriptor",
    "ComponentParameter",
    "DesignDocumentError",
    "PUBLIC_CONTRACT_VERSION",
    "PublicConventions",
    "PublicFieldDescriptor",
    "SimulationMetrics",
    "UnsupportedDesignDocumentError",
    "ValidationFinding",
    "component_catalog",
    "component_catalog_document",
    "decode_assembly_document",
    "describe_public_field",
    "encode_assembly_document",
    "project_assembly_validation",
    "project_clamping_force_response",
    "project_geometry_feasibility",
    "project_geometry_path",
    "project_geometry_summary",
    "project_radius_plane",
    "project_ratio_sensitivity_field",
    "project_simulation_result",
    "public_conventions",
    "summarize_simulation",
    "to_jsonable",
    "validate_assembly",
]
