import enum
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Enum, Integer, ForeignKey, Boolean, Text, DateTime, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from models.mixins import IDMixin, CreatedAtMixin

if TYPE_CHECKING:
    from .subscriber import Subscriber
    from .campaign import Campaign
    from .account import Account


class SuppressionReason(str, enum.Enum):
    HARD_BOUNCE = "hard_bounce"
    COMPLAINT = "complaint"
    UNSUBSCRIBED = "unsubscribed"
    MANUAL = "manual"


class PreferenceChangeType(str, enum.Enum):
    SUBSCRIBED = "subscribed"
    UNSUBSCRIBED = "unsubscribed"
    PREFERENCE_UPDATED = "preference_updated"
    SUPPRESSED = "suppressed"
    UNSUPPRESSED = "unsuppressed"
    BOUNCED = "bounced"


class PreferenceChangeSource(str, enum.Enum):
    IMPORT = "import"
    MANUAL = "manual"
    CAMPAIGN = "campaign"
    AUTOMATION = "automation"
    API = "api"
    PREFERENCE_CENTER = "preference_center"
    SYSTEM = "system"


class SuppressionList(Base, IDMixin, CreatedAtMixin):
    __tablename__ = "suppression_list"
    __table_args__ = (UniqueConstraint("account_id", "email", name="uq_suppression_account_email"),)

    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    reason: Mapped[SuppressionReason] = mapped_column(Enum(SuppressionReason), nullable=False)
    suppressed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_campaign_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )

    account: Mapped["Account"] = relationship()
    source_campaign: Mapped[Optional["Campaign"]] = relationship()

    def __repr__(self):
        return f"<SuppressionList(email='{self.email}', reason='{self.reason}')>"


class UnsubscribeToken(Base, IDMixin, CreatedAtMixin):
    __tablename__ = "unsubscribe_tokens"

    subscriber_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscribers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    is_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    subscriber: Mapped["Subscriber"] = relationship(back_populates="unsubscribe_tokens")
    campaign: Mapped[Optional["Campaign"]] = relationship()

    def __repr__(self):
        return f"<UnsubscribeToken(token='{self.token[:8]}...', used={self.is_used})>"


class PreferenceAuditLog(Base, IDMixin, CreatedAtMixin):
    __tablename__ = "preference_audit_logs"

    subscriber_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscribers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    change_type: Mapped[PreferenceChangeType] = mapped_column(
        Enum(PreferenceChangeType), nullable=False
    )
    source: Mapped[PreferenceChangeSource] = mapped_column(
        Enum(PreferenceChangeSource), nullable=False
    )
    old_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    new_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    subscriber: Mapped["Subscriber"] = relationship(back_populates="preference_logs")
