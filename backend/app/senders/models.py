"""Sending domains and sender identities. ONB-04, ONB-05, BR-02."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, false
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum

if TYPE_CHECKING:
    from app.accounts.models import Account


class SenderStatus(str, enum.Enum):
    UNVERIFIED = "unverified"
    VERIFICATION_PENDING = "verification_pending"
    VERIFIED = "verified"


class DomainAuthStatus(str, enum.Enum):
    NOT_STARTED = "not_started"
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"


_domain_auth_status = pg_enum(DomainAuthStatus, "domain_auth_status")


class SendingDomain(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sending_domains"
    __table_args__ = (
        Index("uq_sending_domains_account_id_domain", "account_id", "domain", unique=True),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE")
    )
    domain: Mapped[str] = mapped_column(String(253))
    dkim_status: Mapped[DomainAuthStatus] = mapped_column(
        _domain_auth_status, server_default=DomainAuthStatus.NOT_STARTED.value
    )
    spf_status: Mapped[DomainAuthStatus] = mapped_column(
        _domain_auth_status, server_default=DomainAuthStatus.NOT_STARTED.value
    )
    dmarc_status: Mapped[DomainAuthStatus] = mapped_column(
        _domain_auth_status, server_default=DomainAuthStatus.NOT_STARTED.value
    )
    provider_identity: Mapped[str | None] = mapped_column(
        String(255), comment="Provider identity reference, e.g. SES identity ARN"
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    account: Mapped[Account] = relationship(back_populates="sending_domains")
    senders: Mapped[list[Sender]] = relationship(back_populates="sending_domain")


class Sender(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """From / reply-to identity. Sending is blocked unless status is verified (BR-02)."""

    __tablename__ = "senders"
    __table_args__ = (
        Index("uq_senders_account_id_from_email", "account_id", "from_email", unique=True),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE")
    )
    sending_domain_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sending_domains.id", ondelete="SET NULL")
    )
    from_name: Mapped[str] = mapped_column(String(120))
    from_email: Mapped[str] = mapped_column(CITEXT)
    reply_to_email: Mapped[str | None] = mapped_column(CITEXT)
    status: Mapped[SenderStatus] = mapped_column(
        pg_enum(SenderStatus, "sender_status"), server_default=SenderStatus.UNVERIFIED.value
    )
    is_default: Mapped[bool] = mapped_column(server_default=false())
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    account: Mapped[Account] = relationship(back_populates="senders")
    sending_domain: Mapped[SendingDomain | None] = relationship(back_populates="senders")
