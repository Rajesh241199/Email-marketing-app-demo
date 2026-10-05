"""Pydantic schemas for segments.

``conditions`` is a free-form JSONB column on the model, but the API only supports a
minimal condition DSL (see ``app/segments/evaluator.py`` for the matching evaluator):

    {"field": "status", "op": "eq", "value": "subscribed"}
    {"field": "tag", "op": "has", "value": "<tag_id>"}
    {"field": "list", "op": "has", "value": "<list_id>"}
    {"field": "custom_field", "op": "eq"|"neq"|"contains", "value": ...,
     "custom_field_id": "<uuid>"}

A segment's ``conditions`` is a JSON array of these rule objects, combined with
``match_type`` (ALL -> AND every rule, ANY -> OR every rule). This shape is intentionally
small and is the contract other domains (e.g. campaigns) should rely on.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from app.segments.models import SegmentMatch


class StatusCondition(BaseModel):
    field: Literal["status"] = "status"
    op: Literal["eq"] = "eq"
    value: str


class TagCondition(BaseModel):
    field: Literal["tag"] = "tag"
    op: Literal["has"] = "has"
    value: uuid.UUID


class ListCondition(BaseModel):
    field: Literal["list"] = "list"
    op: Literal["has"] = "has"
    value: uuid.UUID


class CustomFieldCondition(BaseModel):
    field: Literal["custom_field"] = "custom_field"
    op: Literal["eq", "neq", "contains"]
    value: Any
    custom_field_id: uuid.UUID


SegmentCondition = Annotated[
    StatusCondition | TagCondition | ListCondition | CustomFieldCondition,
    Field(discriminator="field"),
]


class SegmentCreate(BaseModel):
    name: str = Field(max_length=150)
    match_type: SegmentMatch = SegmentMatch.ALL
    conditions: list[SegmentCondition] = Field(default_factory=list)


class SegmentUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=150)
    match_type: SegmentMatch | None = None
    conditions: list[SegmentCondition] | None = None


class SegmentRead(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    name: str
    match_type: SegmentMatch
    conditions: list[dict[str, Any]]
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SegmentPreview(BaseModel):
    count: int
    sample_subscriber_ids: list[uuid.UUID]
