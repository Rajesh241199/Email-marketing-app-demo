"""Account (tenant) and business profile. ONB-03, ONB-07, ONB-08, CMPY-04."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CHAR, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.auth.models import User
    from app.senders.models import Sender, SendingDomain


class Account(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One business using the platform. Every business-owned row carries account_id."""

    __tablename__ = "accounts"

    name: Mapped[str] = mapped_column(String(200), comment="Business name used in the email footer")
    website: Mapped[str | None] = mapped_column(String(255))
    country_code: Mapped[str] = mapped_column(CHAR(2), comment="ISO 3166-1 alpha-2")
    address_line1: Mapped[str] = mapped_column(String(255))
    address_line2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(120))
    region: Mapped[str | None] = mapped_column(String(120))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    timezone: Mapped[str] = mapped_column(
        String(64), server_default="UTC", comment="IANA timezone for scheduling and display (BR-07)"
    )
    date_format: Mapped[str] = mapped_column(String(20), server_default="DD/MM/YYYY")
    time_format: Mapped[str] = mapped_column(String(5), server_default="24h")
    logo_key: Mapped[str | None] = mapped_column(String(512), comment="Object-storage key (PREF-08)")
    brand_color: Mapped[str | None] = mapped_column(CHAR(7))
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="Set when send-readiness checks first pass (ONB-07, ONB-09)"
    )

    users: Mapped[list[User]] = relationship(back_populates="account", passive_deletes=True)
    senders: Mapped[list[Sender]] = relationship(back_populates="account", passive_deletes=True)
    sending_domains: Mapped[list[SendingDomain]] = relationship(
        back_populates="account", passive_deletes=True
    )
