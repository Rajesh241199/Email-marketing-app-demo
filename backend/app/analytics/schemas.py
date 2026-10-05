from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class CampaignStatsRead(BaseModel):
    campaign_id: uuid.UUID
    recipients: int
    skipped: int
    sent: int
    delivered: int
    hard_bounces: int
    soft_bounces: int
    complaints: int
    unique_opens: int
    unique_clicks: int
    unsubscribes: int
    failures: int
    last_event_id: int | None
    computed_at: datetime

    model_config = {"from_attributes": True}
