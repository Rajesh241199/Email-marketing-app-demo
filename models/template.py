from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Integer, ForeignKey, Boolean, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from models.mixins import IDMixin, TimestampMixin

if TYPE_CHECKING:
    from .account import Account
    from .campaign import Campaign
    from .automation import AutomationStep


class Template(Base, IDMixin, TimestampMixin):
    __tablename__ = "templates"

    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    subject: Mapped[Optional[str]] = mapped_column(String(998), nullable=True)
    pre_header: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    body_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # JSON block editor structure for future visual editor
    body_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    body_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    has_unsubscribe_link: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    validation_errors: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    account: Mapped["Account"] = relationship(back_populates="templates")
    campaigns: Mapped[List["Campaign"]] = relationship(back_populates="template")
    automation_steps: Mapped[List["AutomationStep"]] = relationship(back_populates="template")

    def __repr__(self):
        return f"<Template(id={self.id}, name='{self.name}')>"
