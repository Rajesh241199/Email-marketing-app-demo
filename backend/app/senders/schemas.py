from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.senders.models import DomainAuthStatus, SenderStatus


class SendingDomainCreate(BaseModel):
    domain: str = Field(max_length=253)


class SendingDomainRead(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    domain: str
    dkim_status: DomainAuthStatus
    spf_status: DomainAuthStatus
    dmarc_status: DomainAuthStatus
    provider_identity: str | None
    verified_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SenderCreate(BaseModel):
    from_name: str = Field(max_length=120)
    from_email: EmailStr
    reply_to_email: EmailStr | None = None
    sending_domain_id: uuid.UUID | None = None
    is_default: bool = False


class SenderUpdate(BaseModel):
    from_name: str | None = Field(default=None, max_length=120)
    reply_to_email: EmailStr | None = None
    is_default: bool | None = None


class SenderRead(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    sending_domain_id: uuid.UUID | None
    from_name: str
    from_email: EmailStr
    reply_to_email: EmailStr | None
    status: SenderStatus
    is_default: bool
    verified_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
