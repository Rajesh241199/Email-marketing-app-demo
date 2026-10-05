from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.analytics.models import BounceType, EmailEventType, EmailProvider


class WebhookEventIn(BaseModel):
    """Flat simplification of a real provider (SES/SNS) delivery notification.

    A real integration would verify an SNS envelope/signature and unwrap the message; here
    the webhook body is already the flat shape the processor needs, which is the
    deliberate simplification for this bootstrap pass.
    """

    provider: EmailProvider
    provider_event_id: str
    provider_message_id: str | None = None
    event_type: EmailEventType
    occurred_at: datetime
    bounce_type: BounceType | None = None
    link_id: uuid.UUID | None = None
    payload: dict[str, Any] | None = None


class WebhookResult(BaseModel):
    status: str
    reason: str | None = None
