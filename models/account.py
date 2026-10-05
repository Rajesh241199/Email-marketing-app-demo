import enum
from datetime import datetime
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import String, Enum, Integer, ForeignKey, Boolean, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from models.mixins import IDMixin, TimestampMixin

if TYPE_CHECKING:
    from .sender import SenderIdentity
    from .subscriber import Subscriber, SubscriberList, Tag, CustomField
    from .import_job import ImportJob
    from .template import Template
    from .campaign import Campaign
    from .automation import Automation


class OnboardingStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"


class Account(Base, IDMixin, TimestampMixin):
    __tablename__ = "accounts"

    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    business_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timezone: Mapped[str] = mapped_column(String(100), nullable=False, default="UTC")
    date_format: Mapped[str] = mapped_column(String(20), nullable=False, default="MM/DD/YYYY")
    onboarding_status: Mapped[OnboardingStatus] = mapped_column(
        Enum(OnboardingStatus), nullable=False, default=OnboardingStatus.PENDING
    )

    users: Mapped[List["User"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    sender_identities: Mapped[List["SenderIdentity"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    subscribers: Mapped[List["Subscriber"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    lists: Mapped[List["SubscriberList"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    tags: Mapped[List["Tag"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    custom_fields: Mapped[List["CustomField"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    import_jobs: Mapped[List["ImportJob"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    templates: Mapped[List["Template"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    campaigns: Mapped[List["Campaign"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    automations: Mapped[List["Automation"]] = relationship(back_populates="account", cascade="all, delete-orphan")


class UserRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class UserStatus(str, enum.Enum):
    NOT_VERIFIED = "not_verified"
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class User(Base, IDMixin, TimestampMixin):
    __tablename__ = "users"

    account_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[Optional[UserRole]] = mapped_column(Enum(UserRole), nullable=True)
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus), nullable=False, default=UserStatus.NOT_VERIFIED
    )

    account: Mapped[Optional["Account"]] = relationship(back_populates="users")
    auth: Mapped[Optional["UserAuth"]] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}')>"


class UserAuth(Base, IDMixin, TimestampMixin):
    __tablename__ = "user_auth"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    password_hash: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    auth_provider: Mapped[str] = mapped_column(String(50), nullable=False, default="local")
    reset_token: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    reset_token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="auth")
