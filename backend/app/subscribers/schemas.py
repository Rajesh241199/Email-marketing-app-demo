from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, EmailStr, Field

from app.db.enums import ChangeSource, EmailFrequency
from app.subscribers.models import FieldType, MembershipStatus, SubscriberStatus


class SubscriberCreate(BaseModel):
    email: EmailStr
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    external_id: str | None = Field(default=None, max_length=100)
    email_frequency: EmailFrequency = EmailFrequency.ALL


class SubscriberUpdate(BaseModel):
    # status intentionally left out: it's only ever changed through the suppression /
    # unsubscribe flows, which enforce the DB trigger's resubscribe rules. See
    # app/db/triggers.py.
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    external_id: str | None = Field(default=None, max_length=100)
    email_frequency: EmailFrequency | None = None


class SubscriberRead(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    email: EmailStr
    first_name: str | None
    last_name: str | None
    external_id: str | None
    status: SubscriberStatus
    source: ChangeSource
    consent_source: str | None
    consent_at: datetime | None
    unsubscribed_at: datetime | None
    email_frequency: EmailFrequency
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MailingListCreate(BaseModel):
    name: str = Field(max_length=150)
    description: str | None = None
    show_in_preferences: bool = True


class MailingListUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=150)
    description: str | None = None
    show_in_preferences: bool | None = None


class MailingListRead(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    name: str
    description: str | None
    show_in_preferences: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ListMembershipRead(BaseModel):
    list_id: uuid.UUID
    subscriber_id: uuid.UUID
    status: MembershipStatus
    added_at: datetime
    removed_at: datetime | None

    model_config = {"from_attributes": True}


class TagCreate(BaseModel):
    name: str = Field(max_length=100)


class TagRead(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class CustomFieldCreate(BaseModel):
    field_key: str = Field(max_length=64)
    label: str = Field(max_length=120)
    data_type: FieldType = FieldType.TEXT
    options: Any | None = None
    show_in_preferences: bool = False
    sort_order: int = 0


class CustomFieldUpdate(BaseModel):
    # field_key and data_type intentionally excluded: changing either would orphan
    # existing SubscriberFieldValue rows typed against the old data_type.
    label: str | None = Field(default=None, max_length=120)
    options: Any | None = None
    show_in_preferences: bool | None = None
    sort_order: int | None = None


class CustomFieldRead(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    field_key: str
    label: str
    data_type: FieldType
    options: Any | None
    show_in_preferences: bool
    sort_order: int
    created_at: datetime

    model_config = {"from_attributes": True}


class SubscriberFieldValueSet(BaseModel):
    """One typed value matching the target CustomField's data_type.

    The router validates/casts ``value`` against the field's data_type and stores it in
    the matching typed column only, per the ``single_typed_value`` check constraint.
    """

    value: Any


class SubscriberFieldValueRead(BaseModel):
    subscriber_id: uuid.UUID
    custom_field_id: uuid.UUID
    value_text: str | None
    value_number: Decimal | None
    value_date: date | None
    value_bool: bool | None
    updated_at: datetime

    model_config = {"from_attributes": True}
