import enum
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Enum, Integer, ForeignKey, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from models.mixins import IDMixin, TimestampMixin, CreatedAtMixin

if TYPE_CHECKING:
    from .account import Account
    from .template import Template
    from .subscriber import Subscriber


class AutomationStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"


class AutomationTriggerType(str, enum.Enum):
    SUBSCRIBER_ADDED_TO_LIST = "subscriber_added_to_list"
    TAG_APPLIED = "tag_applied"
    MANUAL = "manual"


class AutomationStepType(str, enum.Enum):
    EMAIL = "email"
    WAIT = "wait"


class EnrollmentStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Automation(Base, IDMixin, TimestampMixin):
    __tablename__ = "automations"

    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    trigger_type: Mapped[AutomationTriggerType] = mapped_column(
        Enum(AutomationTriggerType), nullable=False
    )
    trigger_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[AutomationStatus] = mapped_column(
        Enum(AutomationStatus), nullable=False, default=AutomationStatus.DRAFT
    )

    account: Mapped["Account"] = relationship(back_populates="automations")
    steps: Mapped[List["AutomationStep"]] = relationship(
        back_populates="automation", cascade="all, delete-orphan", order_by="AutomationStep.position"
    )
    enrollments: Mapped[List["AutomationEnrollment"]] = relationship(
        back_populates="automation", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Automation(id={self.id}, name='{self.name}', status='{self.status}')>"


class AutomationStep(Base, IDMixin, TimestampMixin):
    __tablename__ = "automation_steps"

    automation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("automations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_type: Mapped[AutomationStepType] = mapped_column(Enum(AutomationStepType), nullable=False)
    template_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("templates.id", ondelete="SET NULL"), nullable=True
    )
    wait_duration_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    automation: Mapped["Automation"] = relationship(back_populates="steps")
    template: Mapped[Optional["Template"]] = relationship(back_populates="automation_steps")


class AutomationEnrollment(Base, IDMixin, CreatedAtMixin):
    __tablename__ = "automation_enrollments"

    automation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("automations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subscriber_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscribers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    current_step_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[EnrollmentStatus] = mapped_column(
        Enum(EnrollmentStatus), nullable=False, default=EnrollmentStatus.ACTIVE
    )
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    automation: Mapped["Automation"] = relationship(back_populates="enrollments")
    subscriber: Mapped["Subscriber"] = relationship()
