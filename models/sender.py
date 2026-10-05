import enum
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Enum, Integer, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from models.mixins import IDMixin, TimestampMixin

if TYPE_CHECKING:
    from .account import Account
    from .campaign import Campaign


class VerificationStatus(str, enum.Enum):
    UNVERIFIED = "unverified"
    VERIFICATION_PENDING = "verification_pending"
    VERIFIED = "verified"


class DomainAuthStatus(str, enum.Enum):
    NOT_CHECKED = "not_checked"
    CONFIGURED = "configured"
    FAILED = "failed"


class SenderIdentity(Base, IDMixin, TimestampMixin):
    __tablename__ = "sender_identities"

    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sender_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sender_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    reply_to_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus), nullable=False, default=VerificationStatus.UNVERIFIED
    )
    domain_auth_status: Mapped[DomainAuthStatus] = mapped_column(
        Enum(DomainAuthStatus), nullable=False, default=DomainAuthStatus.NOT_CHECKED
    )
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    account: Mapped["Account"] = relationship(back_populates="sender_identities")
    campaigns: Mapped[List["Campaign"]] = relationship(back_populates="sender")

    def __repr__(self):
        return f"<SenderIdentity(id={self.id}, email='{self.sender_email}')>"
