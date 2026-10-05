"""Append-only audit trail of consent, preference and unsubscribe changes.

PREF-07, CMPY-07, UNSUB-07.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, Text, func, text
from sqlalchemy.dialects.postgresql import CITEXT, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CorrelationMixin, pg_enum
from app.db.enums import ChangeSource, change_source_enum


class SubscriptionEventType(str, enum.Enum):
    SUBSCRIBED = "subscribed"
    UNSUBSCRIBED = "unsubscribed"
    RESUBSCRIBED = "resubscribed"
    LIST_OPT_IN = "list_opt_in"
    LIST_OPT_OUT = "list_opt_out"
    PROFILE_UPDATED = "profile_updated"
    SUPPRESSED = "suppressed"


class SubscriptionEvent(CorrelationMixin, Base):
    __tablename__ = "subscription_events"
    __table_args__ = (
        Index("ix_subscription_events_subscriber_id_occurred_at", "subscriber_id", "occurred_at"),
        Index("ix_subscription_events_account_id_occurred_at", "account_id", "occurred_at"),
        Index(
            "ix_subscription_events_campaign_id",
            "campaign_id",
            postgresql_where=text("campaign_id IS NOT NULL"),
        ),
        Index(
            "ix_subscription_events_message_id",
            "message_id",
            postgresql_where=text("message_id IS NOT NULL"),
        ),
        Index(
            "ix_subscription_events_list_id",
            "list_id",
            postgresql_where=text("list_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE")
    )
    subscriber_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscribers.id", ondelete="SET NULL")
    )
    email: Mapped[str] = mapped_column(CITEXT, comment="Snapshot, kept if subscriber is deleted")
    event_type: Mapped[SubscriptionEventType] = mapped_column(
        pg_enum(SubscriptionEventType, "subscription_event_type")
    )
    list_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lists.id", ondelete="SET NULL")
    )
    source: Mapped[ChangeSource] = mapped_column(change_source_enum)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL")
    )
    message_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("email_messages.id", ondelete="SET NULL")
    )
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    details: Mapped[Any | None] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
