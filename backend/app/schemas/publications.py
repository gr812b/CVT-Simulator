"""Frozen public configuration snapshots and version history."""

from datetime import datetime
from typing import Literal

from app.schemas.common import ApiModel
from app.schemas.physical_library import PhysicalDifference, PhysicalDocument
from app.schemas.projections import CaseValidation
from app.schemas.results import ResultMetric

PublicationKind = Literal["setups", "cvts", "engines", "belts"]
PublicationVisibility = Literal["public"]


class PublishedDependency(ApiModel):
    kind: str
    name: str
    revision_number: int | None
    owned: bool


class PublicationItem(ApiModel):
    source_revision_id: str
    source_object_id: str
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
