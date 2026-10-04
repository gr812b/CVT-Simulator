"""Explicit publication snapshots; private source rows are never public API data."""

from datetime import datetime
from typing import Literal

from app.schemas.common import ApiModel
from app.schemas.physical_library import PhysicalDifference, PhysicalDocument
from app.schemas.projections import CaseValidation
from app.schemas.results import ResultMetric

PublicationKind = Literal["setups", "cvts"]
PublicationVisibility = Literal["private", "unlisted", "public"]


class PublishRequest(ApiModel):
    expected_revision_id: str
    visibility: Literal["unlisted", "public"]
    gallery_listed: bool
    snapshot_hash: str
    share_dependencies: Literal[True]


class PublicationAccessRequest(ApiModel):
    expected_access_version: int
    visibility: PublicationVisibility
    gallery_listed: bool


class PublishedDependency(ApiModel):
    kind: str
    name: str
    revision_number: int | None
    owned: bool


class PublicationPreview(ApiModel):
    source_revision_id: str
    source_revision_number: int
    document: PhysicalDocument
    dependencies: list[PublishedDependency]
    snapshot_hash: str
    validation: CaseValidation


class PublicationItem(ApiModel):
    id: str
    kind: PublicationKind
    name: str
    description: str
    author: str
    source_label: str
    source_url: str
    revision_number: int
    publication_number: int
    published_at: datetime
    visibility: PublicationVisibility
    gallery_listed: bool
    properties: list[ResultMetric]
    sample: bool = False


class PublicationDetail(ApiModel):
    item: PublicationItem
    document: PhysicalDocument
    dependencies: list[PublishedDependency]
    snapshot_hash: str
    validation: CaseValidation
    history: list[PublicationItem]


class PublicationPage(ApiModel):
    items: list[PublicationItem]
    total: int
    offset: int
    limit: int


class ManagedPublication(ApiModel):
    item: PublicationItem
    access_version: int


class ManagedPublications(ApiModel):
    items: list[ManagedPublication]


class PublicationComparison(ApiModel):
    before: PublicationItem
    after: PublicationItem
    differences: list[PhysicalDifference]
