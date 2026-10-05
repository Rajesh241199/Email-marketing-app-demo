from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.campaigns.models import AudienceMode, CampaignStatus, RecipientStatus, SkipReason
from app.db.enums import CampaignTier


class CampaignCreate(BaseModel):
    name: str = Field(max_length=200)
    sender_id: uuid.UUID | None = None
    template_id: uuid.UUID | None = None
    tier: CampaignTier = CampaignTier.REGULAR
    topic_list_id: uuid.UUID | None = None
    subject: str | None = Field(default=None, max_length=255)
    preheader: str | None = Field(default=None, max_length=255)
    content_json: Any | None = None
    html: str | None = None
    plain_text: str | None = None


class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    sender_id: uuid.UUID | None = None
    template_id: uuid.UUID | None = None
    tier: CampaignTier | None = None
    topic_list_id: uuid.UUID | None = None
    subject: str | None = Field(default=None, max_length=255)
    preheader: str | None = Field(default=None, max_length=255)
    content_json: Any | None = None
    html: str | None = None
    plain_text: str | None = None


class CampaignRead(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    name: str
    status: CampaignStatus
    tier: CampaignTier
    topic_list_id: uuid.UUID | None
    sender_id: uuid.UUID | None
    template_id: uuid.UUID | None
    subject: str | None
    preheader: str | None
    scheduled_at: datetime | None
    confirmed_at: datetime | None
    audience_frozen_at: datetime | None
    sending_started_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    eligible_count: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AudienceCreate(BaseModel):
    mode: AudienceMode = AudienceMode.INCLUDE
    list_id: uuid.UUID | None = None
    segment_id: uuid.UUID | None = None
    tag_id: uuid.UUID | None = None
    subscriber_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def exactly_one_target(self) -> AudienceCreate:
        targets = [self.list_id, self.segment_id, self.tag_id, self.subscriber_id]
        if sum(t is not None for t in targets) != 1:
            raise ValueError(
                "Exactly one of list_id, segment_id, tag_id, subscriber_id must be set"
            )
        return self


class AudienceRead(BaseModel):
    id: uuid.UUID
    mode: AudienceMode
    list_id: uuid.UUID | None
    segment_id: uuid.UUID | None
    tag_id: uuid.UUID | None
    subscriber_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class RecipientRead(BaseModel):
    id: int
    email: str
    status: RecipientStatus
    skip_reason: SkipReason | None
    subscriber_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class FreezeResult(BaseModel):
    eligible_count: int
    skipped_count: int
    audience_frozen_at: datetime


class ScheduleRequest(BaseModel):
    scheduled_at: datetime


class TestSendRequest(BaseModel):
    to_emails: list[str] = Field(min_length=1, max_length=10)


class TestSendRead(BaseModel):
    id: uuid.UUID
    to_emails: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class CampaignLinkCreate(BaseModel):
    url: str
    label: str | None = Field(default=None, max_length=255)
    position: int | None = None


class CampaignLinkRead(BaseModel):
    id: uuid.UUID
    url: str
    label: str | None
    position: int | None

    model_config = {"from_attributes": True}
