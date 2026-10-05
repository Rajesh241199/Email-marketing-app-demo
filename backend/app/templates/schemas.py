from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.templates.models import BlockKind


class ContentBlockCreate(BaseModel):
    kind: BlockKind
    name: str = Field(max_length=200)
    content_json: Any = None
    html: str | None = None
    is_default: bool = False


class ContentBlockUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    content_json: Any | None = None
    html: str | None = None
    is_default: bool | None = None


class ContentBlockRead(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    kind: BlockKind
    name: str
    content_json: Any
    html: str | None
    is_default: bool
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TemplateCreate(BaseModel):
    name: str = Field(max_length=200)
    subject: str | None = Field(default=None, max_length=255)
    preheader: str | None = Field(default=None, max_length=255)
    header_block_id: uuid.UUID | None = None
    footer_block_id: uuid.UUID | None = None
    content_json: Any = None
    html: str | None = None
    plain_text: str | None = None


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    subject: str | None = Field(default=None, max_length=255)
    preheader: str | None = Field(default=None, max_length=255)
    header_block_id: uuid.UUID | None = None
    footer_block_id: uuid.UUID | None = None
    content_json: Any | None = None
    html: str | None = None
    plain_text: str | None = None


class TemplateRead(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    name: str
    subject: str | None
    preheader: str | None
    header_block_id: uuid.UUID | None
    footer_block_id: uuid.UUID | None
    content_json: Any
    html: str | None
    plain_text: str | None
    duplicated_from_id: uuid.UUID | None
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MediaAssetRead(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    file_key: str
    url: str
    filename: str
    content_type: str
    size_bytes: int
    width: int | None
    height: int | None
    alt_text: str | None
    created_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
