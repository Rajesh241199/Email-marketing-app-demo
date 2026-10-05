from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Any, Dict


class TemplateCreate(BaseModel):
    name: str
    subject: Optional[str] = None
    pre_header: Optional[str] = None
    body_html: Optional[str] = None
    body_json: Optional[Dict[str, Any]] = None
    body_text: Optional[str] = None


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    pre_header: Optional[str] = None
    body_html: Optional[str] = None
    body_json: Optional[Dict[str, Any]] = None
    body_text: Optional[str] = None
    is_archived: Optional[bool] = None


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_id: int
    name: str
    subject: Optional[str]
    pre_header: Optional[str]
    body_html: Optional[str]
    body_json: Optional[Dict[str, Any]]
    body_text: Optional[str]
    has_unsubscribe_link: bool
    is_valid: bool
    validation_errors: Optional[List[str]]
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class TemplateValidationResult(BaseModel):
    is_valid: bool
    errors: List[str]


class TemplatePreviewRequest(BaseModel):
    first_name: Optional[str] = "Subscriber"
    last_name: Optional[str] = ""
    email: Optional[str] = "subscriber@example.com"
    custom_fields: Optional[Dict[str, str]] = None


class TemplateListPage(BaseModel):
    total: int
    page: int
    per_page: int
    items: List[TemplateOut]
