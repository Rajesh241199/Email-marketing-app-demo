from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from models.campaign import CampaignStatus, AudienceType


class CampaignAudienceIn(BaseModel):
    audience_type: AudienceType
    audience_id: Optional[int] = None


class CampaignCreate(BaseModel):
    name: str
    sender_id: Optional[int] = None
    template_id: Optional[int] = None
    subject: Optional[str] = None
    pre_header: Optional[str] = None
    audiences: Optional[List[CampaignAudienceIn]] = None


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    sender_id: Optional[int] = None
    template_id: Optional[int] = None
    subject: Optional[str] = None
    pre_header: Optional[str] = None
    audiences: Optional[List[CampaignAudienceIn]] = None
    scheduled_at: Optional[datetime] = None


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_id: int
    name: str
    sender_id: Optional[int]
    template_id: Optional[int]
    subject: Optional[str]
    pre_header: Optional[str]
    status: CampaignStatus
    scheduled_at: Optional[datetime]
    sent_at: Optional[datetime]
    total_recipients: int
    sent_count: int
    delivered_count: int
    opened_count: int
    clicked_count: int
    bounced_count: int
    unsubscribed_count: int
    failed_count: int
    created_at: datetime
    updated_at: datetime
