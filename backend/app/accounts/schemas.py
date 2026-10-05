from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AccountRead(BaseModel):
    id: uuid.UUID
    name: str
    website: str | None
    country_code: str
    address_line1: str
    address_line2: str | None
    city: str
    region: str | None
    postal_code: str | None
    timezone: str
    date_format: str
    time_format: str
    logo_key: str | None
    brand_color: str | None
    onboarding_completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    website: str | None = Field(default=None, max_length=255)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    address_line1: str | None = Field(default=None, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    postal_code: str | None = Field(default=None, max_length=20)
    timezone: str | None = Field(default=None, max_length=64)
    date_format: str | None = Field(default=None, max_length=20)
    time_format: str | None = Field(default=None, max_length=5)
    brand_color: str | None = Field(default=None, min_length=7, max_length=7)


class OnboardingStatus(BaseModel):
    onboarding_completed: bool
    has_verified_sender: bool
    send_ready: bool
