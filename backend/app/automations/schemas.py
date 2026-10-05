from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.automations.models import (
    AutomationStatus,
    AutomationTrigger,
    EnrollmentStatus,
    StepType,
    WaitUnit,
)


class AutomationCreate(BaseModel):
    name: str = Field(max_length=200)
    trigger_type: AutomationTrigger
    trigger_list_id: uuid.UUID | None = None
    trigger_tag_id: uuid.UUID | None = None
    sender_id: uuid.UUID | None = None
    allow_reentry: bool = False


class AutomationUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    status: AutomationStatus | None = None
    trigger_type: AutomationTrigger | None = None
    trigger_list_id: uuid.UUID | None = None
    trigger_tag_id: uuid.UUID | None = None
    sender_id: uuid.UUID | None = None
    allow_reentry: bool | None = None


class AutomationRead(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    name: str
    status: AutomationStatus
    trigger_type: AutomationTrigger
    trigger_list_id: uuid.UUID | None
    trigger_tag_id: uuid.UUID | None
    sender_id: uuid.UUID | None
    allow_reentry: bool
    activated_at: datetime | None
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AutomationStepCreate(BaseModel):
    position: int | None = Field(default=None, ge=0)
    step_type: StepType
    wait_amount: int | None = Field(default=None, gt=0)
    wait_unit: WaitUnit | None = None
    template_id: uuid.UUID | None = None
    subject: str | None = Field(default=None, max_length=255)
    preheader: str | None = Field(default=None, max_length=255)
    content_json: Any | None = None
    html: str | None = None


class AutomationStepUpdate(BaseModel):
    position: int | None = Field(default=None, ge=0)
    step_type: StepType | None = None
    wait_amount: int | None = Field(default=None, gt=0)
    wait_unit: WaitUnit | None = None
    template_id: uuid.UUID | None = None
    subject: str | None = Field(default=None, max_length=255)
    preheader: str | None = Field(default=None, max_length=255)
    content_json: Any | None = None
    html: str | None = None


class AutomationStepRead(BaseModel):
    id: uuid.UUID
    automation_id: uuid.UUID
    position: int
    step_type: StepType
    wait_amount: int | None
    wait_unit: WaitUnit | None
    template_id: uuid.UUID | None
    subject: str | None
    preheader: str | None
    content_json: Any | None
    html: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AutomationEnrollmentRead(BaseModel):
    id: uuid.UUID
    automation_id: uuid.UUID
    subscriber_id: uuid.UUID
    current_step_id: uuid.UUID | None
    status: EnrollmentStatus
    next_run_at: datetime | None
    entered_at: datetime
    completed_at: datetime | None
    exit_reason: str | None

    model_config = {"from_attributes": True}
