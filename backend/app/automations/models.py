"""Trigger > wait > email automations. AUT-01..09, BR-06.

Every email step re-checks eligibility (suppression, status, frequency) immediately before
creating its email_messages row; an ineligible subscriber exits with exit_reason set.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, false, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum


class AutomationStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"


class AutomationTrigger(str, enum.Enum):
    LIST_JOINED = "list_joined"
    TAG_APPLIED = "tag_applied"


class StepType(str, enum.Enum):
    EMAIL = "email"
    WAIT = "wait"


class WaitUnit(str, enum.Enum):
    HOURS = "hours"
    DAYS = "days"


class EnrollmentStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    EXITED = "exited"


class Automation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "automations"
    __table_args__ = (
        Index("ix_automations_account_id_status", "account_id", "status"),
        # "A subscriber joined list X / got tag Y: which active automations fire?"
        Index(
            "ix_automations_active_trigger_list",
            "trigger_list_id",
            postgresql_where=text("status = 'active' AND trigger_list_id IS NOT NULL"),
        ),
        Index(
            "ix_automations_active_trigger_tag",
            "trigger_tag_id",
            postgresql_where=text("status = 'active' AND trigger_tag_id IS NOT NULL"),
        ),
        # Exactly the target that matches the trigger type is set.
        CheckConstraint(
            "(trigger_type = 'list_joined' AND trigger_list_id IS NOT NULL"
            " AND trigger_tag_id IS NULL)"
            " OR (trigger_type = 'tag_applied' AND trigger_tag_id IS NOT NULL"
            " AND trigger_list_id IS NULL)",
            name="trigger_target_matches_type",
        ),
        CheckConstraint(
            "status <> 'active' OR sender_id IS NOT NULL", name="active_has_sender"
        ),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[AutomationStatus] = mapped_column(
        pg_enum(AutomationStatus, "automation_status"),
        server_default=AutomationStatus.DRAFT.value,
    )
    trigger_type: Mapped[AutomationTrigger] = mapped_column(
        pg_enum(AutomationTrigger, "automation_trigger")
    )
    trigger_list_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lists.id", ondelete="CASCADE")
    )
    trigger_tag_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE")
    )
    sender_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("senders.id", ondelete="SET NULL")
    )
    allow_reentry: Mapped[bool] = mapped_column(server_default=false(), comment="AUT-09")
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    steps: Mapped[list[AutomationStep]] = relationship(
        back_populates="automation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AutomationStep.position",
    )
    enrollments: Mapped[list[AutomationEnrollment]] = relationship(
        back_populates="automation", cascade="all, delete-orphan", passive_deletes=True
    )


class AutomationStep(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "automation_steps"
    __table_args__ = (
        Index(
            "uq_automation_steps_automation_id_position", "automation_id", "position", unique=True
        ),
        CheckConstraint(
            "(step_type = 'wait' AND wait_amount > 0 AND wait_unit IS NOT NULL"
            " AND template_id IS NULL AND content_json IS NULL)"
            " OR (step_type = 'email' AND wait_amount IS NULL AND wait_unit IS NULL"
            " AND (template_id IS NOT NULL OR content_json IS NOT NULL))",
            name="step_fields_match_type",
        ),
    )

    automation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automations.id", ondelete="CASCADE")
    )
    position: Mapped[int]
    step_type: Mapped[StepType] = mapped_column(pg_enum(StepType, "step_type"))
    wait_amount: Mapped[int | None]
    wait_unit: Mapped[WaitUnit | None] = mapped_column(pg_enum(WaitUnit, "wait_unit"))
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("templates.id", ondelete="SET NULL")
    )
    subject: Mapped[str | None] = mapped_column(String(255))
    preheader: Mapped[str | None] = mapped_column(String(255))
    content_json: Mapped[Any | None] = mapped_column(JSONB)
    html: Mapped[str | None] = mapped_column(Text)

    automation: Mapped[Automation] = relationship(back_populates="steps")


class AutomationEnrollment(UUIDPrimaryKeyMixin, Base):
    """A subscriber moving through an automation (AUT-08)."""

    __tablename__ = "automation_enrollments"
    __table_args__ = (
        Index(
            "uq_automation_enrollments_automation_id_subscriber_id",
            "automation_id",
            "subscriber_id",
            unique=True,
        ),
        Index("ix_automation_enrollments_subscriber_id", "subscriber_id"),
        Index("ix_automation_enrollments_current_step_id", "current_step_id"),
        # Worker: "which enrollments have a step due?"
        Index(
            "ix_automation_enrollments_due",
            "next_run_at",
            postgresql_where=text("status = 'active'"),
        ),
        CheckConstraint(
            "status <> 'active' OR next_run_at IS NOT NULL", name="active_has_next_run"
        ),
    )

    automation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automations.id", ondelete="CASCADE")
    )
    subscriber_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscribers.id", ondelete="CASCADE")
    )
    current_step_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automation_steps.id", ondelete="SET NULL")
    )
    status: Mapped[EnrollmentStatus] = mapped_column(
        pg_enum(EnrollmentStatus, "enrollment_status"),
        server_default=EnrollmentStatus.ACTIVE.value,
    )
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="Worker picks up due steps"
    )
    entered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exit_reason: Mapped[str | None] = mapped_column(
        String(50), comment="e.g. unsubscribed, suppressed, automation_paused"
    )

    automation: Mapped[Automation] = relationship(back_populates="enrollments")
