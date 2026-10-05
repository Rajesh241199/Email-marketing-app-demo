from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.db.enums import EmailFrequency
from app.subscribers.models import MembershipStatus


class ListMembershipRead(BaseModel):
    list_id: uuid.UUID
    name: str
    status: MembershipStatus

    model_config = {"from_attributes": True}


class PreferencesRead(BaseModel):
    email: str
    email_frequency: EmailFrequency
    lists: list[ListMembershipRead]
    suppressed: bool
    unsubscribed: bool


class TopicChange(BaseModel):
    list_id: uuid.UUID
    opted_out: bool


class PreferencesUpdate(BaseModel):
    email_frequency: EmailFrequency | None = None
    topics: list[TopicChange] | None = Field(default=None)


class UnsubscribeResponse(BaseModel):
    unsubscribed: bool = True
