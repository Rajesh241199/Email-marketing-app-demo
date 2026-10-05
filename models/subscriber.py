import enum
from datetime import datetime
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import (
    String, Enum, Integer, ForeignKey, Boolean, Text,
    DateTime, UniqueConstraint, JSON
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from models.mixins import IDMixin, TimestampMixin, CreatedAtMixin

if TYPE_CHECKING:
    from .account import Account
    from .campaign import CampaignRecipient
    from .suppression import UnsubscribeToken, PreferenceAuditLog


class SubscriberStatus(str, enum.Enum):
    SUBSCRIBED = "subscribed"
    UNSUBSCRIBED = "unsubscribed"
    BOUNCED = "bounced"
    SUPPRESSED = "suppressed"


class CustomFieldType(str, enum.Enum):
    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    BOOLEAN = "boolean"
    URL = "url"


# ── Association tables ────────────────────────────────────────────────────────

class SubscriberListMembership(Base, CreatedAtMixin):
    __tablename__ = "subscriber_list_memberships"

    subscriber_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscribers.id", ondelete="CASCADE"), primary_key=True
    )
    list_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscriber_lists.id", ondelete="CASCADE"), primary_key=True
    )

    subscriber: Mapped["Subscriber"] = relationship(back_populates="list_memberships")
    subscriber_list: Mapped["SubscriberList"] = relationship(back_populates="memberships")


class SubscriberTag(Base, CreatedAtMixin):
    __tablename__ = "subscriber_tags"

    subscriber_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscribers.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )

    subscriber: Mapped["Subscriber"] = relationship(back_populates="tag_associations")
    tag: Mapped["Tag"] = relationship(back_populates="subscriber_associations")


# ── Core models ───────────────────────────────────────────────────────────────

class SubscriberList(Base, IDMixin, TimestampMixin):
    __tablename__ = "subscriber_lists"

    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    account: Mapped["Account"] = relationship(back_populates="lists")
    memberships: Mapped[List["SubscriberListMembership"]] = relationship(
        back_populates="subscriber_list", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<SubscriberList(id={self.id}, name='{self.name}')>"


class Tag(Base, IDMixin, TimestampMixin):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("account_id", "name", name="uq_tag_account_name"),)

    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    account: Mapped["Account"] = relationship(back_populates="tags")
    subscriber_associations: Mapped[List["SubscriberTag"]] = relationship(
        back_populates="tag", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Tag(id={self.id}, name='{self.name}')>"


class CustomField(Base, IDMixin, TimestampMixin):
    __tablename__ = "custom_fields"
    __table_args__ = (UniqueConstraint("account_id", "field_slug", name="uq_cf_account_slug"),)

    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    field_slug: Mapped[str] = mapped_column(String(100), nullable=False)
    field_type: Mapped[CustomFieldType] = mapped_column(
        Enum(CustomFieldType), nullable=False, default=CustomFieldType.TEXT
    )
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    account: Mapped["Account"] = relationship(back_populates="custom_fields")
    values: Mapped[List["SubscriberCustomFieldValue"]] = relationship(
        back_populates="custom_field", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<CustomField(id={self.id}, slug='{self.field_slug}')>"


class SubscriberCustomFieldValue(Base, IDMixin, TimestampMixin):
    __tablename__ = "subscriber_custom_field_values"
    __table_args__ = (
        UniqueConstraint("subscriber_id", "custom_field_id", name="uq_scfv_sub_field"),
    )

    subscriber_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscribers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    custom_field_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("custom_fields.id", ondelete="CASCADE"), nullable=False
    )
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    subscriber: Mapped["Subscriber"] = relationship(back_populates="custom_field_values")
    custom_field: Mapped["CustomField"] = relationship(back_populates="values")


class Subscriber(Base, IDMixin, TimestampMixin):
    __tablename__ = "subscribers"
    __table_args__ = (UniqueConstraint("account_id", "email", name="uq_subscriber_account_email"),)

    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[SubscriberStatus] = mapped_column(
        Enum(SubscriberStatus), nullable=False, default=SubscriberStatus.SUBSCRIBED, index=True
    )
    consent_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    consent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    unsubscribed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    account: Mapped["Account"] = relationship(back_populates="subscribers")
    list_memberships: Mapped[List["SubscriberListMembership"]] = relationship(
        back_populates="subscriber", cascade="all, delete-orphan"
    )
    tag_associations: Mapped[List["SubscriberTag"]] = relationship(
        back_populates="subscriber", cascade="all, delete-orphan"
    )
    custom_field_values: Mapped[List["SubscriberCustomFieldValue"]] = relationship(
        back_populates="subscriber", cascade="all, delete-orphan"
    )
    campaign_recipients: Mapped[List["CampaignRecipient"]] = relationship(
        back_populates="subscriber"
    )
    unsubscribe_tokens: Mapped[List["UnsubscribeToken"]] = relationship(
        back_populates="subscriber", cascade="all, delete-orphan"
    )
    preference_logs: Mapped[List["PreferenceAuditLog"]] = relationship(
        back_populates="subscriber", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Subscriber(id={self.id}, email='{self.email}')>"
