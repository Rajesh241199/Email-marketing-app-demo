from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from models.automation import AutomationStatus, AutomationTriggerType, AutomationStepType


class AutomationStepCreate(BaseModel):
    step_type: AutomationStepType
    template_id: Optional[int] = None
    wait_duration_hours: Optional[int] = None
    position: int = 0


class AutomationCreate(BaseModel):
    name: str
    trigger_type: AutomationTriggerType
    trigger_config: Optional[Dict[str, Any]] = None
    steps: Optional[List[AutomationStepCreate]] = None


class AutomationUpdate(BaseModel):
    name: Optional[str] = None
    trigger_config: Optional[Dict[str, Any]] = None
    status: Optional[AutomationStatus] = None


class AutomationStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    step_type: AutomationStepType
    template_id: Optional[int]
    wait_duration_hours: Optional[int]
    position: int


class AutomationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_id: int
    name: str
    trigger_type: AutomationTriggerType
    trigger_config: Optional[Dict[str, Any]]
    status: AutomationStatus
    created_at: datetime
    updated_at: datetime
    steps: List[AutomationStepOut] = []
