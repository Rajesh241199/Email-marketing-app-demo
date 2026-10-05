"""Per-recipient messages, provider/tracking events and derived campaign rollups.

PRD 4.3, 5.2, CMP-13, CMP-14.

Source of truth
---------------
``email_events`` is the append-only source of truth for what happened to a message.
``email_messages.status`` / ``*_at`` columns and ``campaign_stats`` are *derived* from it
by the event processor and can be rebuilt at any time. Application code never increments
``campaign_stats`` directly.

Message lifecycle
-----------------
queued -> submitting -> accepted -> delivered -> (complained)
                     \\-> rejected           \\-> bounced / soft_bounced
         \\-> failed (our side, retries exhausted)   \\-> cancelled (before submit)

``accepted`` means the provider API returned a message ID. It is NOT delivered: only a
provider ``delivery`` event moves a message to ``delivered``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CorrelationMixin, pg_enum

if TYPE_CHECKING:
    from app.campaigns.models import Campaign


class MessageStatus(str, enum.Enum):
    QUEUED = "queued"  # row created, waiting for a worker
    SUBMITTING = "submitting"  # worker is calling the provider API
    ACCEPTED = "accepted"  # provider returned a message ID; NOT yet delivered
    DELIVERED = "delivered"  # provider delivery event received
    SOFT_BOUNCED = "soft_bounced"  # transient bounce reported
    BOUNCED = "bounced"  # permanent (hard) bounce -> suppression
    COMPLAINED = "complained"  # spam complaint -> suppression
    REJECTED = "rejected"  # provider refused the message after accepting the request
    FAILED = "failed"  # our side: retries exhausted, never accepted (CMP-14)
    CANCELLED = "cancelled"  # campaign cancelled before submission


class EmailProvider(str, enum.Enum):
    SES = "ses"
    TRACKING = "tracking"  # our own open-pixel / click-redirect endpoints


class EmailEventType(str, enum.Enum):
    SEND = "send"
    DELIVERY = "delivery"
    DELIVERY_DELAY = "delivery_delay"
    BOUNCE = "bounce"
    COMPLAINT = "complaint"
    REJECT = "reject"
    OPEN = "open"
    CLICK = "click"
    UNSUBSCRIBE = "unsubscribe"


class BounceType(str, enum.Enum):
    PERMANENT = "permanent"
    TRANSIENT = "transient"
    UNDETERMINED = "undetermined"


_ACCEPTED_OR_LATER = "'accepted', 'delivered', 'soft_bounced', 'bounced', 'complained', 'rejected'"


class EmailMessage(CorrelationMixin, Base):
    """One email to one recipient, from a campaign (via campaign_recipients) or an automation."""

    __tablename__ = "email_messages"
    __table_args__ = (
        # Idempotency: a campaign recipient / automation step run produces at most one message.
        Index(
            "uq_email_messages_campaign_recipient_id",
            "campaign_recipient_id",
            unique=True,
            postgresql_where=text("campaign_recipient_id IS NOT NULL"),
        ),
        Index(
            "uq_email_messages_enrollment_id_step_id",
            "enrollment_id",
            "automation_step_id",
            unique=True,
            postgresql_where=text("enrollment_id IS NOT NULL"),
        ),
        Index("ix_email_messages_campaign_id_status", "campaign_id", "status"),
        Index(
            "ix_email_messages_automation_id",
            "automation_id",
            postgresql_where=text("automation_id IS NOT NULL"),
        ),
        Index("ix_email_messages_subscriber_id", "subscriber_id"),
        Index(
            "ix_email_messages_automation_step_id",
            "automation_step_id",
            postgresql_where=text("automation_step_id IS NOT NULL"),
        ),
        Index("ix_email_messages_account_id_queued_at", "account_id", "queued_at"),
        # Send workers: "what is waiting to go out?"
        Index(
            "ix_email_messages_pending",
            "queued_at",
            postgresql_where=text("status IN ('queued', 'submitting')"),
        ),
        # Exactly one origin: a campaign (through its frozen recipient) or an automation.
        CheckConstraint(
            "(campaign_id IS NOT NULL AND campaign_recipient_id IS NOT NULL"
            " AND automation_id IS NULL)"
            " OR (automation_id IS NOT NULL AND campaign_id IS NULL"
            " AND campaign_recipient_id IS NULL)",
            name="one_origin",
        ),
        CheckConstraint(
            f"status NOT IN ({_ACCEPTED_OR_LATER})"
            " OR (provider_message_id IS NOT NULL AND accepted_at IS NOT NULL)",
            name="accepted_has_provider_id",
        ),
        CheckConstraint(
            "status <> 'delivered' OR delivered_at IS NOT NULL",
            name="delivered_has_timestamp",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE")
    )
    subscriber_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscribers.id", ondelete="SET NULL")
    )
    email: Mapped[str] = mapped_column(CITEXT, comment="Recipient snapshot")
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE")
    )
    campaign_recipient_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("campaign_recipients.id", ondelete="CASCADE")
    )
    automation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automations.id", ondelete="CASCADE")
    )
    automation_step_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automation_steps.id", ondelete="SET NULL")
    )
    enrollment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automation_enrollments.id", ondelete="SET NULL")
    )
    status: Mapped[MessageStatus] = mapped_column(
        pg_enum(MessageStatus, "message_status"), server_default=MessageStatus.QUEUED.value
    )
    provider: Mapped[EmailProvider] = mapped_column(
        pg_enum(EmailProvider, "email_provider"), server_default=EmailProvider.SES.value
    )
    provider_message_id: Mapped[str | None] = mapped_column(
        String(255), comment="Set when the provider accepts the message"
    )
    attempt_count: Mapped[int] = mapped_column(
        SmallInteger, server_default="0", comment="Bounded retries (CMP-14)"
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="Backoff for temporary provider failures"
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bounced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    complained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_clicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    events: Mapped[list[EmailEvent]] = relationship(back_populates="message", lazy="raise")


# Provider message IDs are unique per provider.
Index(
    "uq_email_messages_provider_message_id",
    EmailMessage.provider,
    EmailMessage.provider_message_id,
    unique=True,
    postgresql_where=text("provider_message_id IS NOT NULL"),
)


class EmailEvent(CorrelationMixin, Base):
    """Append-only provider and tracking events. The source of truth for delivery analytics.

    Idempotency: provider webhooks are redelivered. ``(provider, provider_event_id)`` is
    unique, so the processor inserts with ON CONFLICT DO NOTHING and only updates derived
    state when a row was actually inserted. Tracking events get a generated
    provider_event_id (e.g. hash of message + type + link + minute bucket).

    Largest table: plan monthly range partitioning on occurred_at.
    """

    __tablename__ = "email_events"
    __table_args__ = (
        Index(
            "uq_email_events_provider_event_id",
            "provider",
            "provider_event_id",
            unique=True,
        ),
        Index("ix_email_events_message_id", "message_id"),
        Index("ix_email_events_campaign_id_event_type", "campaign_id", "event_type"),
        Index(
            "ix_email_events_link_id",
            "link_id",
            postgresql_where=text("link_id IS NOT NULL"),
        ),
        Index(
            "ix_email_events_account_id_event_type_occurred_at",
            "account_id",
            "event_type",
            "occurred_at",
        ),
        CheckConstraint(
            "event_type = 'bounce' OR bounce_type IS NULL", name="bounce_type_only_on_bounce"
        ),
        CheckConstraint("event_type = 'click' OR link_id IS NULL", name="link_only_on_click"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE")
    )
    message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("email_messages.id", ondelete="CASCADE"),
        comment="NULL only if the provider reports an unknown message",
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        comment="Copied from the message so campaign reports avoid a join",
    )
    provider: Mapped[EmailProvider] = mapped_column(pg_enum(EmailProvider, "email_provider"))
    provider_event_id: Mapped[str] = mapped_column(
        String(255), comment="Provider's event ID; dedupes webhook redeliveries"
    )
    event_type: Mapped[EmailEventType] = mapped_column(pg_enum(EmailEventType, "email_event_type"))
    bounce_type: Mapped[BounceType | None] = mapped_column(pg_enum(BounceType, "bounce_type"))
    link_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaign_links.id", ondelete="SET NULL")
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    payload: Mapped[Any | None] = mapped_column(JSONB)

    message: Mapped[EmailMessage | None] = relationship(back_populates="events")


class CampaignStats(Base):
    """DERIVED rollup of email_events / email_messages for reports and the dashboard.

    Written only by the stats aggregator; safe to truncate and rebuild. ``last_event_id``
    is the high-water mark of email_events already folded in, so rebuilds are incremental.
    """

    __tablename__ = "campaign_stats"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), primary_key=True
    )
    recipients: Mapped[int] = mapped_column(server_default="0", comment="Frozen, not skipped")
    skipped: Mapped[int] = mapped_column(server_default="0")
    sent: Mapped[int] = mapped_column(server_default="0", comment="Accepted by the provider")
    delivered: Mapped[int] = mapped_column(server_default="0")
    hard_bounces: Mapped[int] = mapped_column(server_default="0")
    soft_bounces: Mapped[int] = mapped_column(server_default="0")
    complaints: Mapped[int] = mapped_column(server_default="0")
    unique_opens: Mapped[int] = mapped_column(server_default="0")
    unique_clicks: Mapped[int] = mapped_column(server_default="0")
    unsubscribes: Mapped[int] = mapped_column(server_default="0")
    failures: Mapped[int] = mapped_column(server_default="0", comment="failed + rejected")
    last_event_id: Mapped[int | None] = mapped_column(
        BigInteger, comment="Highest email_events.id included"
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    campaign: Mapped[Campaign] = relationship(back_populates="stats")
