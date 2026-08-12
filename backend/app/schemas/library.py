"""Transport schemas for database-backed library objects.

These schemas intentionally expose the design database's lifecycle primitives
without mirroring CINDER's internal contracts. Model bodies remain JSON payloads;
identity, catalog status, drafts, released versions, and stale/deprecated state
are explicit API fields.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from .common import ApiModel, JsonObject

LibraryResource = Literal[
    "engines",
    "cvt-designs",
    "output-systems",
    "vehicle-assemblies",
]

Visibility = Literal["private", "unlisted", "public"]
LifecycleStatus = Literal["active", "deprecated", "archived"]
CatalogStatus = Literal[
    "user_created",
    "official",
    "ots_part",
    "seeded_example",
    "admin_curated",
    "community",
]
ValidationStatus = Literal["valid", "needs_migration", "deprecated", "unsupported", "invalid"]


class CreateLibraryObjectRequest(ApiModel):
    account_id: str
    name: str
    slug: str | None = None
    description: str | None = None
    visibility: Visibility = "private"
    gallery_listed: bool = False
    catalog_status: CatalogStatus = "user_created"
    catalog_priority: int = 0
    is_default: bool = False
    source_label: str | None = None
    source_url: str | None = None
    source_notes: str | None = None
    draft_payload: JsonObject | None = None


class UpdateLibraryDraftRequest(ApiModel):
    name: str | None = None
    slug: str | None = None
    description: str | None = None
    visibility: Visibility | None = None
    gallery_listed: bool | None = None
    catalog_status: CatalogStatus | None = None
    catalog_priority: int | None = None
    is_default: bool | None = None
    source_label: str | None = None
    source_url: str | None = None
    source_notes: str | None = None
    draft_payload: JsonObject | None = None


class ReleaseLibraryObjectRequest(ApiModel):
    created_by_user_id: str | None = None
    release_notes: str | None = None
    visibility_at_release: Visibility | None = None
    payload: JsonObject | None = None
    summary: JsonObject = Field(default_factory=dict)
    payload_schema_name: str | None = None
    payload_schema_version: int = 1
    validation_status: ValidationStatus = "valid"
    validation_messages: list[JsonObject] = Field(default_factory=list)
    attribution_institution_id: str | None = None
    attribution_label: str | None = None
    tuning_schema: JsonObject | None = None
    engine_version_id: str | None = None
    cvt_design_version_id: str | None = None
    output_system_version_id: str | None = None
    assembly_payload: JsonObject | None = None


class ForkLibraryVersionRequest(ApiModel):
    account_id: str
    name: str | None = None
    slug: str | None = None
    description: str | None = None
    visibility: Visibility = "private"
    created_by_user_id: str | None = None


class ArchiveLibraryObjectRequest(ApiModel):
    lifecycle_status: LifecycleStatus = "archived"


class DeprecateVersionRequest(ApiModel):
    validation_status: ValidationStatus = "deprecated"
    superseded_by_version_id: str | None = None
    message: str | None = None


class LibraryObjectResponse(ApiModel):
    id: str
    resource: LibraryResource
    account_id: str
    name: str
    slug: str | None
    description: str | None
    visibility: Visibility
    gallery_listed: bool
    lifecycle_status: LifecycleStatus
    catalog_status: CatalogStatus
    catalog_priority: int
    is_default: bool
    source_label: str | None
    source_url: str | None
    source_notes: str | None
    draft_payload: JsonObject | None
    draft_updated_at: datetime | None
    released_version_id: str | None
    forked_from_version_id: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class LibraryVersionResponse(ApiModel):
    id: str
    resource: LibraryResource
    object_id: str
    version_number: int
    payload: JsonObject
    # Resource-specific aliases make the public API self-describing while
    # preserving the generic ``payload`` field used by shared tooling.
    input_boundary: JsonObject | None = None
    cinder_assembly: JsonObject | None = None
    output_boundary_template: JsonObject | None = None
    assembly_payload: JsonObject | None = None
    tuning_schema: JsonObject | None = None
    summary: JsonObject
    payload_hash: str
    schema_version: int
    payload_schema_name: str
    payload_schema_version: int
    validation_status: ValidationStatus
    validation_messages: list[JsonObject]
    created_by_user_id: str | None
    created_at: datetime
    release_notes: str | None
    visibility_at_release: Visibility
    attribution_institution_id: str | None
    attribution_label: str | None
    superseded_by_version_id: str | None
    deprecated_at: datetime | None
    engine_version_id: str | None = None
    cvt_design_version_id: str | None = None
    output_system_version_id: str | None = None


class LibraryObjectDetailResponse(ApiModel):
    object: LibraryObjectResponse
    released_version: LibraryVersionResponse | None = None
    versions: list[LibraryVersionResponse] = Field(default_factory=list)


class LibraryObjectListResponse(ApiModel):
    items: list[LibraryObjectResponse]


class InstitutionResponse(ApiModel):
    id: str
    name: str
    slug: str
    institution_type: str
    country_code: str | None
    region: str | None
    website_url: str | None
    email_domains: list[str]
    aliases: list[str]
    is_verified: bool


class InstitutionListResponse(ApiModel):
    items: list[InstitutionResponse]


class CreateTuneRequest(ApiModel):
    account_id: str
    vehicle_assembly_id: str
    cvt_design_id: str
    name: str
    values: JsonObject
    notes: str | None = None


class UpdateTuneRequest(ApiModel):
    name: str | None = None
    values: JsonObject | None = None
    notes: str | None = None


class TuneResponse(ApiModel):
    id: str
    account_id: str
    vehicle_assembly_id: str
    cvt_design_id: str
    name: str
    values: JsonObject
    notes: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class TuneListResponse(ApiModel):
    items: list[TuneResponse]


class CreateLoadCaseRequest(ApiModel):
    account_id: str
    name: str
    kind: str
    visibility: Visibility = "private"
    payload: JsonObject


class UpdateLoadCaseRequest(ApiModel):
    name: str | None = None
    kind: str | None = None
    visibility: Visibility | None = None
    payload: JsonObject | None = None


class LoadCaseResponse(ApiModel):
    id: str
    account_id: str
    name: str
    kind: str
    visibility: Visibility
    payload: JsonObject
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class LoadCaseListResponse(ApiModel):
    items: list[LoadCaseResponse]


class CreateExecutionPresetRequest(ApiModel):
    account_id: str | None = None
    name: str
    kind: str = "simulation"
    payload: JsonObject
    is_system_default: bool = False


class UpdateExecutionPresetRequest(ApiModel):
    name: str | None = None
    kind: str | None = None
    payload: JsonObject | None = None
    is_system_default: bool | None = None


class ExecutionPresetResponse(ApiModel):
    id: str
    account_id: str | None
    name: str
    kind: str
    payload: JsonObject
    is_system_default: bool
    created_at: datetime
    updated_at: datetime


class ExecutionPresetListResponse(ApiModel):
    items: list[ExecutionPresetResponse]
