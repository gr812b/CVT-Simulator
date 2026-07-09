"""ORM schema for the versioned CVT Simulator design database.

The persistence model intentionally mirrors the public simulation boundary:

    EngineVersion       -> CINDER input_boundary
    CVTDesignVersion    -> CINDER assembly
    OutputSystemVersion -> CINDER output_boundary template
    LoadCase            -> CINDER scenario and output-boundary overrides
    ExecutionPreset     -> CINDER execution settings
    Run                 -> frozen resolved cinder_simulation_case

Mutable user-facing objects keep drafts. Released versions are immutable and are
what assemblies, gallery pages, and runs reference.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.types import JsonPayload

from app.database.base import (
    Base,
    SoftDeleteMixin,
    StringUUIDPrimaryKeyMixin,
    TimestampMixin,
    utc_now,
)

JsonDict = dict[str, Any]


class Account(StringUUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint(
            "tier in ('free', 'pro', 'team', 'enterprise')",
            name="tier_known",
        ),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    tier: Mapped[str] = mapped_column(String(32), nullable=False, default="free")

    users: Mapped[list["AccountUser"]] = relationship(back_populates="account")
    institution_affiliations: Mapped[list["AccountInstitutionAffiliation"]] = relationship(
        back_populates="account"
    )


class User(StringUUIDPrimaryKeyMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    accounts: Mapped[list["AccountUser"]] = relationship(back_populates="user")
    institution_affiliations: Mapped[list["UserInstitutionAffiliation"]] = relationship(
        back_populates="user"
    )


class AccountUser(Base):
    __tablename__ = "account_users"
    __table_args__ = (
        CheckConstraint("role in ('owner', 'admin', 'editor', 'viewer')", name="role_known"),
    )

    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)

    account: Mapped[Account] = relationship(back_populates="users")
    user: Mapped[User] = relationship(back_populates="accounts")


class Institution(StringUUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "institutions"

    name: Mapped[str] = mapped_column(String(240), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), nullable=False, unique=True, index=True)
    institution_type: Mapped[str] = mapped_column(String(40), nullable=False, default="university")
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    email_domains: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    aliases: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    account_affiliations: Mapped[list["AccountInstitutionAffiliation"]] = relationship(
        back_populates="institution"
    )
    user_affiliations: Mapped[list["UserInstitutionAffiliation"]] = relationship(
        back_populates="institution"
    )


class AccountInstitutionAffiliation(StringUUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "account_institution_affiliations"
    __table_args__ = (
        CheckConstraint(
            "verification_status in ('self_reported', 'email_domain', 'admin_verified')",
            name="verification_status_known",
        ),
        UniqueConstraint("account_id", "institution_id", "affiliation_label"),
    )

    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    institution_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    affiliation_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    affiliation_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    verification_status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="self_reported"
    )
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    account: Mapped[Account] = relationship(back_populates="institution_affiliations")
    institution: Mapped[Institution] = relationship(back_populates="account_affiliations")


class UserInstitutionAffiliation(StringUUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_institution_affiliations"
    __table_args__ = (
        CheckConstraint(
            "verification_status in ('self_reported', 'email_domain', 'admin_verified')",
            name="verification_status_known",
        ),
        UniqueConstraint("user_id", "institution_id", "affiliation_type"),
    )

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    institution_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    affiliation_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    verification_status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="self_reported"
    )
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    user: Mapped[User] = relationship(back_populates="institution_affiliations")
    institution: Mapped[Institution] = relationship(back_populates="user_affiliations")


class VersionedDraftMixin(TimestampMixin, SoftDeleteMixin):
    """Columns shared by mutable objects with immutable released versions."""

    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    slug: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    visibility: Mapped[str] = mapped_column(String(20), nullable=False, default="private")
    gallery_listed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lifecycle_status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    catalog_status: Mapped[str] = mapped_column(String(32), nullable=False, default="user_created")
    catalog_priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_label: Mapped[str | None] = mapped_column(String(240), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    draft_payload: Mapped[JsonDict | None] = mapped_column(JsonPayload, nullable=True)
    draft_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Engine(StringUUIDPrimaryKeyMixin, VersionedDraftMixin, Base):
    __tablename__ = "engines"
    __table_args__ = (
        CheckConstraint("visibility in ('private', 'unlisted', 'public')", name="visibility_known"),
    )

    released_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("engine_versions.id", ondelete="SET NULL"), nullable=True
    )
    forked_from_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("engine_versions.id", ondelete="SET NULL"), nullable=True
    )

    versions: Mapped[list["EngineVersion"]] = relationship(
        back_populates="engine", foreign_keys="EngineVersion.engine_id"
    )
    released_version: Mapped["EngineVersion | None"] = relationship(
        foreign_keys=[released_version_id], post_update=True
    )


class EngineVersion(StringUUIDPrimaryKeyMixin, Base):
    __tablename__ = "engine_versions"
    __table_args__ = (
        UniqueConstraint("engine_id", "version_number"),
        Index(
            "ix_engine_versions_input_boundary_gin",
            "input_boundary",
            postgresql_using="gin",
            postgresql_ops={"input_boundary": "jsonb_path_ops"},
        ),
    )

    engine_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("engines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    input_boundary: Mapped[JsonDict] = mapped_column(JsonPayload, nullable=False)
    summary: Mapped[JsonDict] = mapped_column(JsonPayload, nullable=False, default=dict)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload_schema_name: Mapped[str] = mapped_column(String(120), nullable=False)
    payload_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    validation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="valid")
    validation_messages: Mapped[list[JsonDict]] = mapped_column(JSON, nullable=False, default=list)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    release_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    visibility_at_release: Mapped[str] = mapped_column(String(20), nullable=False)
    attribution_institution_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("institutions.id", ondelete="SET NULL"), nullable=True
    )
    attribution_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    superseded_by_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("engine_versions.id", ondelete="SET NULL"), nullable=True
    )
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    engine: Mapped[Engine] = relationship(back_populates="versions", foreign_keys=[engine_id])


class CVTDesign(StringUUIDPrimaryKeyMixin, VersionedDraftMixin, Base):
    __tablename__ = "cvt_designs"
    __table_args__ = (
        CheckConstraint("visibility in ('private', 'unlisted', 'public')", name="visibility_known"),
    )

    released_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("cvt_design_versions.id", ondelete="SET NULL"), nullable=True
    )
    forked_from_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("cvt_design_versions.id", ondelete="SET NULL"), nullable=True
    )

    versions: Mapped[list["CVTDesignVersion"]] = relationship(
        back_populates="cvt_design", foreign_keys="CVTDesignVersion.cvt_design_id"
    )
    released_version: Mapped["CVTDesignVersion | None"] = relationship(
        foreign_keys=[released_version_id], post_update=True
    )


class CVTDesignVersion(StringUUIDPrimaryKeyMixin, Base):
    __tablename__ = "cvt_design_versions"
    __table_args__ = (
        UniqueConstraint("cvt_design_id", "version_number"),
        Index(
            "ix_cvt_design_versions_cinder_assembly_gin",
            "cinder_assembly",
            postgresql_using="gin",
            postgresql_ops={"cinder_assembly": "jsonb_path_ops"},
        ),
    )

    cvt_design_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cvt_designs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    cinder_assembly: Mapped[JsonDict] = mapped_column(JsonPayload, nullable=False)
    tuning_schema: Mapped[JsonDict] = mapped_column(JsonPayload, nullable=False, default=dict)
    summary: Mapped[JsonDict] = mapped_column(JsonPayload, nullable=False, default=dict)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload_schema_name: Mapped[str] = mapped_column(String(120), nullable=False)
    payload_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    validation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="valid")
    validation_messages: Mapped[list[JsonDict]] = mapped_column(JSON, nullable=False, default=list)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    release_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    visibility_at_release: Mapped[str] = mapped_column(String(20), nullable=False)
    attribution_institution_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("institutions.id", ondelete="SET NULL"), nullable=True
    )
    attribution_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    superseded_by_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("cvt_design_versions.id", ondelete="SET NULL"), nullable=True
    )
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    cvt_design: Mapped[CVTDesign] = relationship(
        back_populates="versions", foreign_keys=[cvt_design_id]
    )


class OutputSystem(StringUUIDPrimaryKeyMixin, VersionedDraftMixin, Base):
    __tablename__ = "output_systems"
    __table_args__ = (
        CheckConstraint("visibility in ('private', 'unlisted', 'public')", name="visibility_known"),
    )

    released_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("output_system_versions.id", ondelete="SET NULL"), nullable=True
    )
    forked_from_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("output_system_versions.id", ondelete="SET NULL"), nullable=True
    )

    versions: Mapped[list["OutputSystemVersion"]] = relationship(
        back_populates="output_system", foreign_keys="OutputSystemVersion.output_system_id"
    )
    released_version: Mapped["OutputSystemVersion | None"] = relationship(
        foreign_keys=[released_version_id], post_update=True
    )


class OutputSystemVersion(StringUUIDPrimaryKeyMixin, Base):
    __tablename__ = "output_system_versions"
    __table_args__ = (
        UniqueConstraint("output_system_id", "version_number"),
        Index(
            "ix_output_system_versions_template_gin",
            "output_boundary_template",
            postgresql_using="gin",
            postgresql_ops={"output_boundary_template": "jsonb_path_ops"},
        ),
    )

    output_system_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("output_systems.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    output_boundary_template: Mapped[JsonDict] = mapped_column(JsonPayload, nullable=False)
    summary: Mapped[JsonDict] = mapped_column(JsonPayload, nullable=False, default=dict)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload_schema_name: Mapped[str] = mapped_column(String(120), nullable=False)
    payload_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    validation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="valid")
    validation_messages: Mapped[list[JsonDict]] = mapped_column(JSON, nullable=False, default=list)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    release_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    visibility_at_release: Mapped[str] = mapped_column(String(20), nullable=False)
    attribution_institution_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("institutions.id", ondelete="SET NULL"), nullable=True
    )
    attribution_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    superseded_by_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("output_system_versions.id", ondelete="SET NULL"), nullable=True
    )
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    output_system: Mapped[OutputSystem] = relationship(
        back_populates="versions", foreign_keys=[output_system_id]
    )


class VehicleAssembly(StringUUIDPrimaryKeyMixin, VersionedDraftMixin, Base):
    __tablename__ = "vehicle_assemblies"
    __table_args__ = (
        CheckConstraint("visibility in ('private', 'unlisted', 'public')", name="visibility_known"),
    )

    released_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("vehicle_assembly_versions.id", ondelete="SET NULL"), nullable=True
    )
    forked_from_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("vehicle_assembly_versions.id", ondelete="SET NULL"), nullable=True
    )

    versions: Mapped[list["VehicleAssemblyVersion"]] = relationship(
        back_populates="vehicle_assembly",
        foreign_keys="VehicleAssemblyVersion.vehicle_assembly_id",
    )
    released_version: Mapped["VehicleAssemblyVersion | None"] = relationship(
        foreign_keys=[released_version_id], post_update=True
    )
    tunes: Mapped[list["Tune"]] = relationship(back_populates="vehicle_assembly")


class VehicleAssemblyVersion(StringUUIDPrimaryKeyMixin, Base):
    __tablename__ = "vehicle_assembly_versions"
    __table_args__ = (UniqueConstraint("vehicle_assembly_id", "version_number"),)

    vehicle_assembly_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("vehicle_assemblies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    engine_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("engine_versions.id", ondelete="RESTRICT"), nullable=False
    )
    cvt_design_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cvt_design_versions.id", ondelete="RESTRICT"), nullable=False
    )
    output_system_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("output_system_versions.id", ondelete="RESTRICT"), nullable=False
    )
    assembly_payload: Mapped[JsonDict] = mapped_column(JsonPayload, nullable=False, default=dict)
    summary: Mapped[JsonDict] = mapped_column(JsonPayload, nullable=False, default=dict)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload_schema_name: Mapped[str] = mapped_column(String(120), nullable=False)
    payload_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    validation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="valid")
    validation_messages: Mapped[list[JsonDict]] = mapped_column(JSON, nullable=False, default=list)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    release_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    visibility_at_release: Mapped[str] = mapped_column(String(20), nullable=False)
    attribution_institution_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("institutions.id", ondelete="SET NULL"), nullable=True
    )
    attribution_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    superseded_by_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("vehicle_assembly_versions.id", ondelete="SET NULL"), nullable=True
    )
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    vehicle_assembly: Mapped[VehicleAssembly] = relationship(
        back_populates="versions", foreign_keys=[vehicle_assembly_id]
    )
    engine_version: Mapped[EngineVersion] = relationship(foreign_keys=[engine_version_id])
    cvt_design_version: Mapped[CVTDesignVersion] = relationship(
        foreign_keys=[cvt_design_version_id]
    )
    output_system_version: Mapped[OutputSystemVersion] = relationship(
        foreign_keys=[output_system_version_id]
    )


class Tune(StringUUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "tunes"

    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vehicle_assembly_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("vehicle_assemblies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cvt_design_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cvt_designs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    values: Mapped[JsonDict] = mapped_column(JsonPayload, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    vehicle_assembly: Mapped[VehicleAssembly] = relationship(back_populates="tunes")


class LoadCase(StringUUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "load_cases"
    __table_args__ = (
        CheckConstraint("visibility in ('private', 'unlisted', 'public')", name="visibility_known"),
        Index(
            "ix_load_cases_payload_gin",
            "payload",
            postgresql_using="gin",
            postgresql_ops={"payload": "jsonb_path_ops"},
        ),
    )

    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    visibility: Mapped[str] = mapped_column(String(20), nullable=False, default="private")
    payload: Mapped[JsonDict] = mapped_column(JsonPayload, nullable=False)


class ExecutionPreset(StringUUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "execution_presets"

    account_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    kind: Mapped[str] = mapped_column(String(80), nullable=False, default="simulation")
    payload: Mapped[JsonDict] = mapped_column(JsonPayload, nullable=False)
    is_system_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class RunCacheEntry(StringUUIDPrimaryKeyMixin, Base):
    __tablename__ = "run_cache_entries"
    __table_args__ = (
        UniqueConstraint("contract_hash", "cinder_model_version", "contract_schema_version"),
    )

    contract_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    cinder_model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    contract_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    full_result_artifact_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    summary_scalars: Mapped[JsonDict] = mapped_column(JsonPayload, nullable=False, default=dict)
    summary_series: Mapped[JsonDict] = mapped_column(JsonPayload, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    last_accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class Run(StringUUIDPrimaryKeyMixin, Base):
    __tablename__ = "runs"

    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    vehicle_assembly_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("vehicle_assembly_versions.id", ondelete="RESTRICT"), nullable=False
    )
    engine_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("engine_versions.id", ondelete="RESTRICT"), nullable=False
    )
    cvt_design_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cvt_design_versions.id", ondelete="RESTRICT"), nullable=False
    )
    output_system_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("output_system_versions.id", ondelete="RESTRICT"), nullable=False
    )
    tune_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tunes.id", ondelete="SET NULL"), nullable=True
    )
    load_case_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("load_cases.id", ondelete="SET NULL"), nullable=True
    )
    execution_preset_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("execution_presets.id", ondelete="SET NULL"), nullable=True
    )
    tune_snapshot: Mapped[JsonDict] = mapped_column(JsonPayload, nullable=False, default=dict)
    load_case_snapshot: Mapped[JsonDict] = mapped_column(JsonPayload, nullable=False, default=dict)
    execution_snapshot: Mapped[JsonDict] = mapped_column(JsonPayload, nullable=False, default=dict)
    input_contract: Mapped[JsonDict] = mapped_column(JsonPayload, nullable=False)
    contract_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    cinder_model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    contract_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[JsonDict | None] = mapped_column(JsonPayload, nullable=True)
    summary_scalars: Mapped[JsonDict] = mapped_column(JsonPayload, nullable=False, default=dict)
    summary_series: Mapped[JsonDict] = mapped_column(JsonPayload, nullable=False, default=dict)
    cache_entry_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("run_cache_entries.id", ondelete="SET NULL"), nullable=True
    )

    cache_entry: Mapped[RunCacheEntry | None] = relationship(foreign_keys=[cache_entry_id])
    artifacts: Mapped[list["RunArtifact"]] = relationship(back_populates="run")


class RunArtifact(StringUUIDPrimaryKeyMixin, Base):
    __tablename__ = "run_artifacts"

    run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    cache_entry_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("run_cache_entries.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    artifact_kind: Mapped[str] = mapped_column(String(80), nullable=False)
    storage_backend: Mapped[str] = mapped_column(String(40), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    byte_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    inline_payload: Mapped[JsonDict | None] = mapped_column(JsonPayload, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    evictable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    run: Mapped[Run | None] = relationship(back_populates="artifacts")


class FavoriteRun(Base):
    __tablename__ = "favorite_runs"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
