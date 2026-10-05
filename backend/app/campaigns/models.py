"""Campaigns, audience rules, frozen recipients, test sends and tracked links.

CMP-01..14, BR-01..04.

Send pipeline
-------------
1. ``campaign_audiences``  - the *rules* the user picked (lists, segments, tags, people).
2. ``campaign_recipients`` - the *frozen* audience: rules resolved into one row per email
   when the user confirms (``campaigns.audience_frozen_at``). Ineligible people are kept
   with status ``skipped`` and a ``skip_reason`` so the UI can explain exclusions.
3. ``email_messages``      - one row per recipient actually handed to the send queue,
   linked 1:1 to its campaign_recipient.
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
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    Base,
    CorrelationMixin,
    CreatedAtMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    pg_enum,
)
from app.db.enums import CampaignTier, campaign_tier_enum

if TYPE_CHECKING:
    from app.analytics.models import CampaignStats
    from app.senders.models import Sender
    from app.subscribers.models import MailingList
    from app.templates.models import Template


class CampaignStatus(str, enum.Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    SENDING = "sending"
    SENT = "sent"
    PARTIALLY_FAILED = "partially_failed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AudienceMode(str, enum.Enum):
    INCLUDE = "include"
    EXCLUDE = "exclude"


class RecipientStatus(str, enum.Enum):
    PENDING = "pending"  # frozen, not yet queued
    QUEUED = "queued"  # an email_messages row exists
    SKIPPED = "skipped"  # excluded at freeze time or at the pre-send re-check
    CANCELLED = "cancelled"  # campaign cancelled before this recipient was queued


class SkipReason(str, enum.Enum):
    UNSUBSCRIBED = "unsubscribed"
    SUPPRESSED = "suppressed"
    LIST_OPTED_OUT = "list_opted_out"
    FREQUENCY_PREFERENCE = "frequency_preference"
    EXCLUDED_BY_RULE = "excluded_by_rule"
    INVALID_EMAIL = "invalid_email"


class Campaign(UUIDPrimaryKeyMixin, CorrelationMixin, TimestampMixin, Base):
    """One-to-many email send. Content is copied from the template at creation."""

    __tablename__ = "campaigns"
    __table_args__ = (
        Index("ix_campaigns_account_id_status", "account_id", "status"),
        Index("ix_campaigns_account_id_created_at", "account_id", "created_at"),
        Index(
            "ix_campaigns_topic_list_id",
            "topic_list_id",
            postgresql_where=text("topic_list_id IS NOT NULL"),
        ),
        # Scheduler: "which scheduled campaigns are due?"
        Index(
            "ix_campaigns_due",
            "scheduled_at",
            postgresql_where=text("status = 'scheduled'"),
        ),
        CheckConstraint(
            "status <> 'scheduled' OR scheduled_at IS NOT NULL",
            name="scheduled_has_time",
        ),
        CheckConstraint(
            "status NOT IN ('scheduled', 'sending', 'sent', 'partially_failed', 'failed')"
            " OR (sender_id IS NOT NULL AND confirmed_at IS NOT NULL)",
            name="confirmed_before_send",
        ),
        CheckConstraint(
            "status NOT IN ('sending', 'sent', 'partially_failed', 'failed')"
            " OR (audience_frozen_at IS NOT NULL AND sending_started_at IS NOT NULL)",
            name="frozen_before_send",
        ),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(200), comment="Internal name (CMP-01)")
    status: Mapped[CampaignStatus] = mapped_column(
        pg_enum(CampaignStatus, "campaign_status"), server_default=CampaignStatus.DRAFT.value
    )
    tier: Mapped[CampaignTier] = mapped_column(
        campaign_tier_enum,
        server_default=CampaignTier.REGULAR.value,
        comment="Matched against subscribers.email_frequency (PREF-09)",
    )
    topic_list_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lists.id", ondelete="SET NULL"),
        comment=(
            "Topic this campaign counts as for preference-center opt-outs. Applies even "
            "when the audience is a segment, tag, or individual subscriber, not just a "
            "list (schema-v1.md section 4)"
        ),
    )
    sender_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("senders.id", ondelete="RESTRICT")
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("templates.id", ondelete="SET NULL"),
        comment="Template it started from; content is copied into this row",
    )
    subject: Mapped[str | None] = mapped_column(String(255))
    preheader: Mapped[str | None] = mapped_column(String(255))
    content_json: Mapped[Any | None] = mapped_column(JSONB)
    html: Mapped[str | None] = mapped_column(Text)
    plain_text: Mapped[str | None] = mapped_column(Text)
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="UTC; entered in account timezone (CMP-09)"
    )
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="Final pre-send confirmation (CMP-08)"
    )
    audience_frozen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="campaign_recipients written; audience fixed"
    )
    sending_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="Content and audience immutable from here (BR-04)"
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    eligible_count: Mapped[int | None] = mapped_column(
        comment="Recipients with status pending/queued after freeze (CMP-05)"
    )
    duplicated_from_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    sender: Mapped[Sender | None] = relationship()
    template: Mapped[Template | None] = relationship()
    topic_list: Mapped[MailingList | None] = relationship()
    audiences: Mapped[list[CampaignAudience]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan", passive_deletes=True
    )
    recipients: Mapped[list[CampaignRecipient]] = relationship(
        back_populates="campaign", passive_deletes=True, lazy="raise"
    )
    test_sends: Mapped[list[TestSend]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan", passive_deletes=True
    )
    links: Mapped[list[CampaignLink]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan", passive_deletes=True
    )
    stats: Mapped[CampaignStats | None] = relationship(
        back_populates="campaign", cascade="all, delete-orphan", passive_deletes=True
    )


class CampaignAudience(UUIDPrimaryKeyMixin, Base):
    """Audience rule (CMP-04). Exactly one target column is set per row."""

    __tablename__ = "campaign_audiences"
    __table_args__ = (
        Index("ix_campaign_audiences_campaign_id", "campaign_id"),
        Index("ix_campaign_audiences_list_id", "list_id", postgresql_where=text("list_id IS NOT NULL")),
        Index(
            "ix_campaign_audiences_segment_id",
            "segment_id",
            postgresql_where=text("segment_id IS NOT NULL"),
        ),
        Index("ix_campaign_audiences_tag_id", "tag_id", postgresql_where=text("tag_id IS NOT NULL")),
        Index(
            "ix_campaign_audiences_subscriber_id",
            "subscriber_id",
            postgresql_where=text("subscriber_id IS NOT NULL"),
        ),
        CheckConstraint(
            "num_nonnulls(list_id, segment_id, tag_id, subscriber_id) = 1",
            name="exactly_one_target",
        ),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE")
    )
    mode: Mapped[AudienceMode] = mapped_column(
        pg_enum(AudienceMode, "audience_mode"), server_default=AudienceMode.INCLUDE.value
    )
    list_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lists.id", ondelete="CASCADE")
    )
    segment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("segments.id", ondelete="CASCADE")
    )
    tag_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE")
    )
    subscriber_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscribers.id", ondelete="CASCADE")
    )

    campaign: Mapped[Campaign] = relationship(back_populates="audiences")


class CampaignRecipient(Base):
    """Frozen audience: one row per unique email, written when the campaign is confirmed.

    After ``campaigns.audience_frozen_at`` is set, rows are never added. Status only moves
    pending -> queued | skipped | cancelled. The pre-send re-check (BR-06) can still mark a
    pending row skipped if the person unsubscribed after the freeze.
    """

    __tablename__ = "campaign_recipients"
    __table_args__ = (
        Index("uq_campaign_recipients_campaign_id_email", "campaign_id", "email", unique=True),
        Index("ix_campaign_recipients_campaign_id_status", "campaign_id", "status"),
        Index("ix_campaign_recipients_subscriber_id", "subscriber_id"),
        CheckConstraint(
            "(status = 'skipped') = (skip_reason IS NOT NULL)",
            name="skip_reason_iff_skipped",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE")
    )
    subscriber_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subscribers.id", ondelete="SET NULL"),
        comment="NULL only if the subscriber was deleted later",
    )
    email: Mapped[str] = mapped_column(CITEXT, comment="Snapshot at freeze time")
    merge_data: Mapped[Any | None] = mapped_column(
        JSONB, comment="Snapshot of personalization fields at freeze time"
    )
    matched_audience_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campaign_audiences.id", ondelete="SET NULL"),
        comment="First include rule that selected this person",
    )
    status: Mapped[RecipientStatus] = mapped_column(
        pg_enum(RecipientStatus, "recipient_status"),
        server_default=RecipientStatus.PENDING.value,
    )
    skip_reason: Mapped[SkipReason | None] = mapped_column(pg_enum(SkipReason, "skip_reason"))
    frozen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    campaign: Mapped[Campaign] = relationship(back_populates="recipients")


class TestSend(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Test emails sent before confirmation (CMP-07). Not counted in campaign stats."""

    __tablename__ = "test_sends"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    sent_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    to_emails: Mapped[list[str]] = mapped_column(ARRAY(Text))
    provider_message_id: Mapped[str | None] = mapped_column(String(255))

    campaign: Mapped[Campaign] = relationship(back_populates="test_sends")


class CampaignLink(UUIDPrimaryKeyMixin, Base):
    """Tracked link in sent content, for per-link click counts."""

    __tablename__ = "campaign_links"
    __table_args__ = (Index("ix_campaign_links_campaign_id", "campaign_id"),)

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE")
    )
    url: Mapped[str] = mapped_column(Text)
    label: Mapped[str | None] = mapped_column(String(255))
    position: Mapped[int | None]

    campaign: Mapped[Campaign] = relationship(back_populates="links")
