from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from typing import Optional, Dict, Any
from models.suppression import SuppressionReason


class PreferenceCenterData(BaseModel):
    subscriber_id: int
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    status: str
    lists: list


class UnsubscribeRequest(BaseModel):
    token: str


class PreferenceUpdateRequest(BaseModel):
    token: str
    list_ids_to_keep: Optional[list] = None
    unsubscribe_all: bool = False


class SuppressionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_id: int
    email: str
    reason: SuppressionReason
    suppressed_at: datetime
    created_at: datetime
