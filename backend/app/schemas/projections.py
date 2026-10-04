"""Typed transport projections used by editor and result clients.

CINDER remains the source of assembly/simulation schemas and field metadata.
These envelopes describe the JSON emitted by the adapter, not mechanics.
"""

from typing import Any, Literal

from pydantic import ConfigDict, with_config
from typing_extensions import NotRequired, TypedDict


@with_config(ConfigDict(extra="allow"))
class EditableField(TypedDict):
    path_template: str
    label: str
    description: str
    value_kind: Literal[
        "number", "integer", "boolean", "string", "enum", "object", "array"
    ]
    section: str
    dimension: NotRequired[str]
    canonical_unit: NotRequired[str]
    required: bool
    minimum: NotRequired[float]
    maximum: NotRequired[float]
    enum_values: list[str]
    when: NotRequired[dict[str, str]]
    exposure: Literal["design", "scenario", "advanced_execution"]


@with_config(ConfigDict(extra="allow"))
class ComponentParameter(TypedDict):
    key: str
    label: str
    canonical_unit: str
    dimension: NotRequired[str]
    value_kind: Literal["number", "object"]
    required: bool
    description: str
    minimum: NotRequired[float]
    maximum: NotRequired[float]


@with_config(ConfigDict(extra="allow"))
class Component(TypedDict):
    kind: str
    label: str
    description: str
    supported_mounts: list[str]
    parameters: list[ComponentParameter]


@with_config(ConfigDict(extra="allow"))
class ComponentCatalog(TypedDict):
    document_type: str
    contract_version: int
    components: list[Component]


@with_config(ConfigDict(extra="allow"))
class EditorDocument(TypedDict):
    fields: list[EditableField]
    supported_discriminators: dict[str, list[str]]
    component_catalog: ComponentCatalog


@with_config(ConfigDict(extra="allow"))
class ValidationFinding(TypedDict):
    severity: Literal["error", "warning"]
    code: str
    message: str
    location: str
    document_path: NotRequired[str]


@with_config(ConfigDict(extra="allow"))
class CaseValidation(TypedDict):
    is_valid: bool
    findings: list[ValidationFinding]


@with_config(ConfigDict(extra="forbid"))
class TuneParameter(TypedDict):
    key: str
    label: str
    description: NotRequired[str]
    group: Literal["primary", "ramp", "secondary", "helix"]
    kind: Literal["number", "ramp"]
    unit: str
    path: NotRequired[str]
    dimension: NotRequired[str]
    min: NotRequired[float]
    max: NotRequired[float]
    default: NotRequired[Any]


@with_config(ConfigDict(extra="allow"))
class TuningSchema(TypedDict):
    parameters: list[TuneParameter]


@with_config(ConfigDict(extra="allow"))
class PreviewColumn(TypedDict):
    key: str
    label: str
    canonical_unit: str
    dimension: str
    group: str
    description: str
    values: list[float | None]


@with_config(ConfigDict(extra="allow"))
class RunPreview(TypedDict):
    profile_name: str
    profile_version: int
    original_row_count: int
    preview_row_count: int
    axis_key: str | None
    columns: list[PreviewColumn]


@with_config(ConfigDict(extra="forbid"))
class ValidationMetric(TypedDict):
    bias: float | None
    mae: float | None
    rmse: float | None
    maxAbs: float | None
    count: int


@with_config(ConfigDict(extra="allow"))
class ProjectedField(TypedDict):
    key: str
    label: str
    dimension: str
    canonical_unit: str
    values: Any


@with_config(ConfigDict(extra="allow"))
class ProjectedScalar(TypedDict):
    key: str
    label: str
    dimension: str
    canonical_unit: str
    value: float | None


@with_config(ConfigDict(extra="allow"))
class GeometrySummary(TypedDict):
    kind: Literal["geometry_summary"]
    scalars: list[ProjectedScalar]


@with_config(ConfigDict(extra="allow"))
class GeometryPath(TypedDict):
    kind: Literal["geometry_path"]
    shape: list[int]
    axis_keys: list[str]
    columns: list[ProjectedField]


@with_config(ConfigDict(extra="allow"))
class GeometryFinding(TypedDict):
    severity: Literal["error", "warning"]
    code: str
    message: str
    shift_m: float | None


@with_config(ConfigDict(extra="allow"))
class GeometryFeasibility(TypedDict):
    is_feasible: bool
    findings: list[GeometryFinding]


@with_config(ConfigDict(extra="allow"))
class GeometryStudy(TypedDict):
    kind: Literal["geometry_design_response"]
    summary: GeometrySummary
    path: GeometryPath
    feasibility: GeometryFeasibility
