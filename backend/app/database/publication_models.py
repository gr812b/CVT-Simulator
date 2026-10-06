"""Fixed publication bundles and durable attribution for independent copies."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, StringUUIDPrimaryKeyMixin, utc_now
from app.database.types import JsonPayload


class PhysicalPublication(StringUUIDPrimaryKeyMixin, Base):
    __tablename__ = "physical_publications"
    __table_args__ = (
        UniqueConstraint("kind", "source_revision_id", name="uq_publication_source_revision"),
        Index("ix_publications_gallery", "visibility", "gallery_listed", "published_at"),
    )
    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("accounts.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    source_object_id: Mapped[str] = mapped_column(String(36), index=True)
    source_revision_id: Mapped[str] = mapped_column(String(36))
    revision_number: Mapped[int] = mapped_column(Integer)
    publication_number: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(String(4000))
    author: Mapped[str] = mapped_column(String(240))
    source_label: Mapped[str] = mapped_column(String(240))
    source_url: Mapped[str] = mapped_column(String(500))
    document: Mapped[dict] = mapped_column(JsonPayload)
    dependencies: Mapped[list] = mapped_column(JsonPayload)
    tuning_schema: Mapped[dict] = mapped_column(JsonPayload)
    validation: Mapped[dict] = mapped_column(JsonPayload)
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    visibility: Mapped[str] = mapped_column(String(20))
    gallery_listed: Mapped[bool] = mapped_column(Boolean)
    access_version: Mapped[int] = mapped_column(Integer, default=1)
    sample: Mapped[bool] = mapped_column(Boolean, default=False)


class ConfigurationCopy(StringUUIDPrimaryKeyMixin, Base):
    __tablename__ = "configuration_copies"
    __table_args__ = (
        UniqueConstraint("account_id", "request_key", name="uq_configuration_copy_request"),
    )
    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("accounts.id"), index=True)
    request_key: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(20))
    object_id: Mapped[str] = mapped_column(String(36), index=True)
    publication_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("physical_publications.id")
    )
    run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("runs.id"))
    scenario_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("experiments.id"))
    copied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
