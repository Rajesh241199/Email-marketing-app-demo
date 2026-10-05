from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, EmailStr, ConfigDict, field_validator
from typing import Optional, List, Any
from models.subscriber import SubscriberStatus, CustomFieldType


# ── List ──────────────────────────────────────────────────────────────────────

class ListCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ListUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class ListOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_id: int
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime


# ── Tag ───────────────────────────────────────────────────────────────────────

class TagCreate(BaseModel):
    name: str


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_id: int
    name: str
    created_at: datetime


# ── Custom Field ──────────────────────────────────────────────────────────────

class CustomFieldCreate(BaseModel):
    field_name: str
    field_slug: str
    field_type: CustomFieldType = CustomFieldType.TEXT
    is_required: bool = False

    @field_validator("field_slug")
    @classmethod
    def slug_lowercase(cls, v: str) -> str:
        return v.lower().replace(" ", "_")


class CustomFieldUpdate(BaseModel):
    field_name: Optional[str] = None
    is_required: Optional[bool] = None


class CustomFieldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_id: int
    field_name: str
    field_slug: str
    field_type: CustomFieldType
    is_required: bool
    created_at: datetime


# ── Custom Field Value ────────────────────────────────────────────────────────

class CustomFieldValueIn(BaseModel):
    custom_field_id: int
    value: Optional[str] = None


class CustomFieldValueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    custom_field_id: int
    value: Optional[str]


# ── Subscriber ────────────────────────────────────────────────────────────────

class SubscriberCreate(BaseModel):
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    status: SubscriberStatus = SubscriberStatus.SUBSCRIBED
    consent_source: Optional[str] = None
    consent_at: Optional[datetime] = None
    list_ids: Optional[List[int]] = None
    tag_ids: Optional[List[int]] = None
    custom_fields: Optional[List[CustomFieldValueIn]] = None


class SubscriberUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    status: Optional[SubscriberStatus] = None
    consent_source: Optional[str] = None
    consent_at: Optional[datetime] = None
    list_ids: Optional[List[int]] = None
    tag_ids: Optional[List[int]] = None
    custom_fields: Optional[List[CustomFieldValueIn]] = None


class SubscriberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_id: int
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    status: SubscriberStatus
    consent_source: Optional[str]
    consent_at: Optional[datetime]
    unsubscribed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class SubscriberDetail(SubscriberOut):
    tags: List[TagOut] = []
    lists: List[ListOut] = []
    custom_field_values: List[CustomFieldValueOut] = []


class SubscriberListPage(BaseModel):
    total: int
    page: int
    per_page: int
    items: List[SubscriberOut]


# ── Bulk operations ───────────────────────────────────────────────────────────

class BulkIdsRequest(BaseModel):
    ids: List[int]


# ── Preference audit ──────────────────────────────────────────────────────────

class PreferenceLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    change_type: str
    source: str
    old_status: Optional[str]
    new_status: Optional[str]
    created_at: datetime
