"""Stable public contracts layered over CINDER's mechanics-first core.

These optional adapters own saved documents, validation, editable-field
metadata, standardized projections, and metrics.  Core model/execution modules
deliberately remain independent of JSON, HTTP, and frontend concerns.
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
from .editable_schema import (
    EditableFieldDescriptor,
    editable_simulation_case_schema,
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
from .schema import simulation_case_document_json_schema
from .simulation import SimulationMetrics, summarize_simulation
from .simulation_document import (
    SIMULATION_CASE_DOCUMENT_TYPE,
    DecodedSimulationCase,
    UnsupportedSimulationDocumentError,
    decode_simulation_case_document,
    encode_simulation_case_document,
)
from .validation import (
    AssemblyValidationOptions,
    AssemblyValidationReport,
    ValidationFinding,
    validate_assembly,
    validate_assembly_document,
    validate_simulation_case_document,
)

__all__ = [
    "ASSEMBLY_DOCUMENT_TYPE",
    "SIMULATION_CASE_DOCUMENT_TYPE",
    "AssemblyValidationOptions",
    "AssemblyValidationReport",
    "ComponentDescriptor",
    "ComponentParameter",
    "DecodedSimulationCase",
    "DesignDocumentError",
    "EditableFieldDescriptor",
    "PUBLIC_CONTRACT_VERSION",
    "PublicConventions",
    "PublicFieldDescriptor",
    "SimulationMetrics",
    "UnsupportedDesignDocumentError",
    "UnsupportedSimulationDocumentError",
    "ValidationFinding",
    "component_catalog",
    "component_catalog_document",
    "decode_assembly_document",
    "decode_simulation_case_document",
    "describe_public_field",
    "editable_simulation_case_schema",
    "encode_assembly_document",
    "encode_simulation_case_document",
    "project_assembly_validation",
    "project_clamping_force_response",
    "project_geometry_feasibility",
    "project_geometry_path",
    "project_geometry_summary",
    "project_radius_plane",
    "project_ratio_sensitivity_field",
    "project_simulation_result",
    "public_conventions",
    "simulation_case_document_json_schema",
    "summarize_simulation",
    "to_jsonable",
    "validate_assembly",
    "validate_assembly_document",
    "validate_simulation_case_document",
]
