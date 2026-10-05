"""CSV import jobs, column mappings and rejected rows. SUB-02, SUB-03, SUB-IMP-01..08."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    false,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CorrelationMixin, CreatedAtMixin, UUIDPrimaryKeyMixin, pg_enum


class ImportStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


class ImportTarget(str, enum.Enum):
    EMAIL = "email"
    FIRST_NAME = "first_name"
    LAST_NAME = "last_name"
    EXTERNAL_ID = "external_id"
    CUSTOM_FIELD = "custom_field"
    IGNORE = "ignore"


class ImportJob(UUIDPrimaryKeyMixin, CorrelationMixin, CreatedAtMixin, Base):
    __tablename__ = "import_jobs"
    __table_args__ = (
        Index("ix_import_jobs_account_id_created_at", "account_id", "created_at"),
        Index(
            "ix_import_jobs_pending",
            "created_at",
            postgresql_where=text("status IN ('queued', 'processing')"),
        ),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE")
    )
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    status: Mapped[ImportStatus] = mapped_column(
        pg_enum(ImportStatus, "import_status"), server_default=ImportStatus.QUEUED.value
    )
    file_key: Mapped[str] = mapped_column(String(512), comment="Object-storage key of the CSV")
    original_filename: Mapped[str] = mapped_column(String(255))
    has_header_row: Mapped[bool] = mapped_column(server_default=true(), comment="SUB-IMP-03")
    target_list_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lists.id", ondelete="SET NULL")
    )
    update_existing: Mapped[bool] = mapped_column(
        server_default=false(),
        comment="Update profile data of existing subscribers; never overrides unsubscribe/suppression",  # noqa: E501
    )
    total_rows: Mapped[int | None]
    imported_count: Mapped[int] = mapped_column(server_default="0")
    updated_count: Mapped[int] = mapped_column(server_default="0")
    duplicate_count: Mapped[int] = mapped_column(server_default="0")
    rejected_count: Mapped[int] = mapped_column(server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    column_mappings: Mapped[list[ImportColumnMapping]] = relationship(
        back_populates="import_job",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ImportColumnMapping.column_index",
    )
    row_errors: Mapped[list[ImportRowError]] = relationship(
        back_populates="import_job", cascade="all, delete-orphan", passive_deletes=True
    )


class ImportColumnMapping(UUIDPrimaryKeyMixin, Base):
    """What each uploaded CSV column maps to (SUB-IMP-05, SUB-IMP-06, SUB-IMP-07)."""

    __tablename__ = "import_column_mappings"
    __table_args__ = (
        Index(
            "uq_import_column_mappings_job_id_column_index",
            "import_job_id",
            "column_index",
            unique=True,
        ),
        CheckConstraint(
            "(target = 'custom_field') = (custom_field_id IS NOT NULL)",
            name="custom_field_target",
        ),
    )

    import_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("import_jobs.id", ondelete="CASCADE")
    )
    column_index: Mapped[int]
    source_header: Mapped[str | None] = mapped_column(String(255))
    sample_value: Mapped[str | None] = mapped_column(Text)
    target: Mapped[ImportTarget] = mapped_column(pg_enum(ImportTarget, "import_target"))
    custom_field_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("custom_fields.id", ondelete="SET NULL"),
        comment="Set when target = custom_field",
    )

    import_job: Mapped[ImportJob] = relationship(back_populates="column_mappings")


class ImportRowError(Base):
    """Rejected rows and reasons, shown in the import summary."""

    __tablename__ = "import_row_errors"
    __table_args__ = (Index("ix_import_row_errors_import_job_id", "import_job_id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    import_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("import_jobs.id", ondelete="CASCADE")
    )
    row_number: Mapped[int]
    email: Mapped[str | None] = mapped_column(String(320))
    error_code: Mapped[str] = mapped_column(
        String(50), comment="invalid_email, missing_email, duplicate_in_file, suppressed"
    )
    raw_row: Mapped[Any | None] = mapped_column(JSONB)

    import_job: Mapped[ImportJob] = relationship(back_populates="row_errors")
