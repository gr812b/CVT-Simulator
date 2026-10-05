"""Immutable named tune/scenario revisions and durable completion notices."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, StringUUIDPrimaryKeyMixin, TimestampMixin, utc_now
from app.database.types import JsonPayload


class Experiment(StringUUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "experiments"

    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("accounts.id"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(240))
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    cvt_object_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("cvt_designs.id", ondelete="RESTRICT"), index=True
    )
    current_revision_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("experiment_revisions.id", ondelete="RESTRICT")
    )


class ExperimentRevision(StringUUIDPrimaryKeyMixin, Base):
    __tablename__ = "experiment_revisions"
    __table_args__ = (UniqueConstraint("experiment_id", "number"),)

    experiment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("experiments.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    document: Mapped[dict] = mapped_column(JsonPayload)
    content_hash: Mapped[str] = mapped_column(String(64))
    change_note: Mapped[str] = mapped_column(String(2000), default="")
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class RunNotification(StringUUIDPrimaryKeyMixin, Base):
    __tablename__ = "run_notifications"
    __table_args__ = (UniqueConstraint("run_id", "user_id"),)

    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("accounts.id"), index=True
    )
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CVTDefaultTune(Base):
    """A CVT revision's preferred tune; runs freeze the chosen tune revision."""

    __tablename__ = "cvt_default_tunes"
    cvt_revision_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("cvt_design_versions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tune_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("experiments.id", ondelete="RESTRICT"), nullable=False
    )
