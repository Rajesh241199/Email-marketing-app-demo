import enum
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Enum, Integer, ForeignKey, Text, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from models.mixins import IDMixin, TimestampMixin, CreatedAtMixin

if TYPE_CHECKING:
    from .account import Account
    from .subscriber import SubscriberList


class ImportStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


class ImportJob(Base, IDMixin, TimestampMixin):
    __tablename__ = "import_jobs"

    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    list_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("subscriber_lists.id", ondelete="SET NULL"), nullable=True
    )
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    stored_filename: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    status: Mapped[ImportStatus] = mapped_column(
        Enum(ImportStatus), nullable=False, default=ImportStatus.QUEUED, index=True
    )
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    imported_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invalid_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # JSON: {"col_name": "platform_field" | "ignore"}
    field_mapping: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # JSON: list of column header strings
    headers: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # JSON: list of dicts (first 5 rows)
    preview_rows: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    error_summary: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    account: Mapped["Account"] = relationship(back_populates="import_jobs")
    subscriber_list: Mapped[Optional["SubscriberList"]] = relationship()
    errors: Mapped[List["ImportJobError"]] = relationship(
        back_populates="import_job", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<ImportJob(id={self.id}, status='{self.status}')>"


class ImportJobError(Base, IDMixin, CreatedAtMixin):
    __tablename__ = "import_job_errors"

    import_job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_reason: Mapped[str] = mapped_column(String(512), nullable=False)

    import_job: Mapped["ImportJob"] = relationship(back_populates="errors")
