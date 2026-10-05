import enum
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Enum, Integer, ForeignKey, Text, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from models.mixins import IDMixin, TimestampMixin, CreatedAtMixin

if TYPE_CHECKING:
    from .account import Account
    from .sender import SenderIdentity
    from .template import Template
    from .subscriber import Subscriber


class CampaignStatus(str, enum.Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    SENDING = "sending"
    SENT = "sent"
    PARTIALLY_FAILED = "partially_failed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AudienceType(str, enum.Enum):
    LIST = "list"
    TAG = "tag"
    ALL = "all"


class RecipientStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    OPENED = "opened"
    CLICKED = "clicked"
    BOUNCED = "bounced"
    COMPLAINED = "complained"
    UNSUBSCRIBED = "unsubscribed"
    FAILED = "failed"


class Campaign(Base, IDMixin, TimestampMixin):
    __tablename__ = "campaigns"

    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sender_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("sender_identities.id", ondelete="SET NULL"), nullable=True
    )
    template_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("templates.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String(998), nullable=True)
    pre_header: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    body_html_snapshot: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[CampaignStatus] = mapped_column(
        Enum(CampaignStatus), nullable=False, default=CampaignStatus.DRAFT, index=True
    )
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    total_recipients: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    delivered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    opened_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clicked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bounced_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unsubscribed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    account: Mapped["Account"] = relationship(back_populates="campaigns")
    sender: Mapped[Optional["SenderIdentity"]] = relationship(back_populates="campaigns")
    template: Mapped[Optional["Template"]] = relationship(back_populates="campaigns")
    audiences: Mapped[List["CampaignAudience"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )
    recipients: Mapped[List["CampaignRecipient"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Campaign(id={self.id}, name='{self.name}', status='{self.status}')>"


class CampaignAudience(Base, IDMixin, CreatedAtMixin):
    __tablename__ = "campaign_audiences"

    campaign_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    audience_type: Mapped[AudienceType] = mapped_column(Enum(AudienceType), nullable=False)
    audience_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    campaign: Mapped["Campaign"] = relationship(back_populates="audiences")


class CampaignRecipient(Base, IDMixin, CreatedAtMixin):
    __tablename__ = "campaign_recipients"

    campaign_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subscriber_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscribers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[RecipientStatus] = mapped_column(
        Enum(RecipientStatus), nullable=False, default=RecipientStatus.PENDING
    )
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    clicked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    bounced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    bounced_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    failed_reason: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    campaign: Mapped["Campaign"] = relationship(back_populates="recipients")
    subscriber: Mapped["Subscriber"] = relationship(back_populates="campaign_recipients")
