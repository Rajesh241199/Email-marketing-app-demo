"""Account-wide do-not-send list. BR-01, BR-06, CMPY-03.

Keyed by email (not subscriber_id) so it survives subscriber deletion and re-import.

Every "unsubscribe from all", hard bounce, spam complaint and manual block writes a row
here and sets subscribers.status accordingly. The row is the durable record: if the
subscriber is deleted and later re-imported, the insert trigger in app.db.triggers stores
them as suppressed again. A suppression is only lifted (lifted_at) by an explicit
re-subscription.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin, pg_enum
from app.db.enums import ChangeSource, change_source_enum


class SuppressionReason(str, enum.Enum):
    HARD_BOUNCE = "hard_bounce"
    COMPLAINT = "complaint"
    UNSUBSCRIBE = "unsubscribe"
    MANUAL = "manual"


class Suppression(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "suppressions"
    __table_args__ = (
        Index("ix_suppressions_account_id_email", "account_id", "email"),
        Index(
            "ix_suppressions_email_event_id",
            "email_event_id",
            postgresql_where=text("email_event_id IS NOT NULL"),
        ),
        # At most one active suppression per email per account.
        Index(
            "uq_suppressions_active_email",
            "account_id",
            "email",
            unique=True,
            postgresql_where=text("lifted_at IS NULL"),
        ),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE")
    )
    email: Mapped[str] = mapped_column(CITEXT)
    reason: Mapped[SuppressionReason] = mapped_column(
        pg_enum(SuppressionReason, "suppression_reason")
    )
    source: Mapped[ChangeSource] = mapped_column(change_source_enum)
    email_event_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("email_events.id", ondelete="SET NULL"),
        comment="Bounce / complaint event that caused it",
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    lifted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="Only via explicit re-subscription (CMPY-03)"
    )
