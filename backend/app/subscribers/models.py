"""Subscribers, lists, tags and custom fields. SUB-01..12, PREF-02..04, PREF-09.

Preference-center state lives in three places (see docs/architecture/schema-v1.md):
  * subscribers.status          - account-wide marketing consent ("unsubscribe from all")
  * list_memberships.status     - per-topic opt-in / opt-out ("opt-down")
  * subscribers.email_frequency - how often they want to hear from the account
The account-wide ``suppressions`` table overrides all three.

Imports can never reactivate an opted-out contact: the database trigger in
``app.db.triggers`` rejects unsubscribed/suppressed -> subscribed and opted_out -> active
unless the transaction explicitly allows a re-subscription.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    false,
    func,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import CITEXT, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum
from app.db.enums import ChangeSource, EmailFrequency, change_source_enum, email_frequency_enum


class SubscriberStatus(str, enum.Enum):
    SUBSCRIBED = "subscribed"
    UNSUBSCRIBED = "unsubscribed"
    SUPPRESSED = "suppressed"


class MembershipStatus(str, enum.Enum):
    ACTIVE = "active"
    OPTED_OUT = "opted_out"


class FieldType(str, enum.Enum):
    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    BOOLEAN = "boolean"
    CHOICE = "choice"


class Subscriber(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One record per person per account (email is unique within the account)."""

    __tablename__ = "subscribers"
    __table_args__ = (
        Index("uq_subscribers_account_id_email", "account_id", "email", unique=True),
        Index("ix_subscribers_account_id_status", "account_id", "status"),
        Index("ix_subscribers_account_id_external_id", "account_id", "external_id"),
        Index("ix_subscribers_account_id_created_at", "account_id", "created_at"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE")
    )
    email: Mapped[str] = mapped_column(CITEXT)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    external_id: Mapped[str | None] = mapped_column(
        String(100), comment="Customer subscriber number / ID from CSV (SUB-IMP-06)"
    )
    status: Mapped[SubscriberStatus] = mapped_column(
        pg_enum(SubscriberStatus, "subscriber_status"),
        server_default=SubscriberStatus.SUBSCRIBED.value,
        comment="Imports never overwrite unsubscribed / suppressed (BR-05)",
    )
    source: Mapped[ChangeSource] = mapped_column(
        change_source_enum, server_default=ChangeSource.MANUAL.value
    )
    consent_source: Mapped[str | None] = mapped_column(String(255), comment="SUB-10")
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_ip: Mapped[str | None] = mapped_column(INET)
    unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_frequency: Mapped[EmailFrequency] = mapped_column(
        email_frequency_enum,
        server_default=EmailFrequency.ALL.value,
        comment="Frequency preference (PREF-09)",
    )

    list_memberships: Mapped[list[ListMembership]] = relationship(
        back_populates="subscriber", cascade="all, delete-orphan", passive_deletes=True
    )
    tags: Mapped[list[Tag]] = relationship(
        secondary="subscriber_tags", back_populates="subscribers", passive_deletes=True
    )
    field_values: Mapped[list[SubscriberFieldValue]] = relationship(
        back_populates="subscriber", cascade="all, delete-orphan", passive_deletes=True
    )


class MailingList(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """List / group (SUB-07). Also a topic in the preference center (PREF-03).

    Named MailingList in Python to avoid shadowing the built-in ``list``.
    """

    __tablename__ = "lists"
    __table_args__ = (Index("uq_lists_account_id_name", "account_id", "name", unique=True),)

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    show_in_preferences: Mapped[bool] = mapped_column(server_default=true())

    memberships: Mapped[list[ListMembership]] = relationship(
        back_populates="mailing_list", cascade="all, delete-orphan", passive_deletes=True
    )


class ListMembership(Base):
    """Subscriber <-> list. A new active row fires list_joined automations."""

    __tablename__ = "list_memberships"
    __table_args__ = (
        Index("ix_list_memberships_subscriber_id", "subscriber_id"),
        Index(
            "ix_list_memberships_list_id_active",
            "list_id",
            postgresql_where=text("status = 'active'"),
        ),
    )

    list_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lists.id", ondelete="CASCADE"), primary_key=True
    )
    subscriber_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscribers.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[MembershipStatus] = mapped_column(
        pg_enum(MembershipStatus, "membership_status"),
        server_default=MembershipStatus.ACTIVE.value,
        comment="opted_out keeps history for opt-down (PREF-04)",
    )
    source: Mapped[ChangeSource] = mapped_column(
        change_source_enum, server_default=ChangeSource.MANUAL.value
    )
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    mailing_list: Mapped[MailingList] = relationship(back_populates="memberships")
    subscriber: Mapped[Subscriber] = relationship(back_populates="list_memberships")


class Tag(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "tags"
    __table_args__ = (Index("uq_tags_account_id_name", "account_id", "name", unique=True),)

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(100))

    subscribers: Mapped[list[Subscriber]] = relationship(
        secondary="subscriber_tags", back_populates="tags", passive_deletes=True
    )


class SubscriberTag(Base):
    """Applying a tag fires tag_applied automations."""

    __tablename__ = "subscriber_tags"
    __table_args__ = (Index("ix_subscriber_tags_tag_id", "tag_id"),)

    subscriber_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscribers.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CustomField(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Account-defined subscriber field (SUB-08)."""

    __tablename__ = "custom_fields"
    __table_args__ = (
        Index("uq_custom_fields_account_id_field_key", "account_id", "field_key", unique=True),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE")
    )
    field_key: Mapped[str] = mapped_column(String(64), comment="Merge-tag key, e.g. company")
    label: Mapped[str] = mapped_column(String(120))
    data_type: Mapped[FieldType] = mapped_column(
        pg_enum(FieldType, "field_type"), server_default=FieldType.TEXT.value
    )
    options: Mapped[Any | None] = mapped_column(JSONB, comment="Allowed values for choice fields")
    show_in_preferences: Mapped[bool] = mapped_column(server_default=false(), comment="PREF-02")
    sort_order: Mapped[int] = mapped_column(server_default="0")


class SubscriberFieldValue(Base):
    """Typed value per subscriber per custom field, so segments can filter numbers and dates."""

    __tablename__ = "subscriber_field_values"
    __table_args__ = (
        Index("ix_subscriber_field_values_field_id_value_text", "custom_field_id", "value_text"),
        CheckConstraint(
            "num_nonnulls(value_text, value_number, value_date, value_bool) <= 1",
            name="single_typed_value",
        ),
    )

    subscriber_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscribers.id", ondelete="CASCADE"), primary_key=True
    )
    custom_field_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("custom_fields.id", ondelete="CASCADE"), primary_key=True
    )
    value_text: Mapped[str | None] = mapped_column(Text)
    value_number: Mapped[Decimal | None] = mapped_column(Numeric)
    value_date: Mapped[date | None] = mapped_column(Date)
    value_bool: Mapped[bool | None]
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    subscriber: Mapped[Subscriber] = relationship(back_populates="field_values")
    custom_field: Mapped[CustomField] = relationship()
