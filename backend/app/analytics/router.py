"""Authenticated campaign stats: read the derived rollup, or recompute it.

``campaign_stats`` is derived from ``email_events`` / ``email_messages`` /
``campaign_recipients`` and is safe to rebuild at any time (schema-v1.md section 7).
Application code never increments it directly - only this recompute endpoint writes it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.analytics.models import CampaignStats, EmailEvent, EmailMessage, MessageStatus
from app.analytics.schemas import CampaignStatsRead
from app.campaigns.models import Campaign, CampaignRecipient, RecipientStatus
from app.core.deps import get_current_account_id, get_db
from app.preferences.models import SubscriptionEvent, SubscriptionEventType

router = APIRouter(prefix="/api/v1/campaigns", tags=["analytics"])


def _get_campaign(db: Session, account_id: uuid.UUID, campaign_id: uuid.UUID) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.account_id != account_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaign not found")
    return campaign


def _count_messages(db: Session, campaign_id: uuid.UUID, *conditions: object) -> int:
    return (
        db.query(func.count(EmailMessage.id))
        .filter(EmailMessage.campaign_id == campaign_id, *conditions)
        .scalar()
        or 0
    )


@router.get("/{campaign_id}/stats", response_model=CampaignStatsRead)
def get_campaign_stats(
    campaign_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> CampaignStats:
    _get_campaign(db, account_id, campaign_id)
    stats = db.get(CampaignStats, campaign_id)
    if stats is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Stats not computed yet")
    return stats


@router.post("/{campaign_id}/stats/recompute", response_model=CampaignStatsRead)
def recompute_campaign_stats(
    campaign_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> CampaignStats:
    campaign = _get_campaign(db, account_id, campaign_id)

    recipients = (
        db.query(func.count(CampaignRecipient.id))
        .filter(CampaignRecipient.campaign_id == campaign.id)
        .scalar()
        or 0
    )
    skipped = (
        db.query(func.count(CampaignRecipient.id))
        .filter(
            CampaignRecipient.campaign_id == campaign.id,
            CampaignRecipient.status == RecipientStatus.SKIPPED,
        )
        .scalar()
        or 0
    )

    # "sent" / "delivered" use the *_at milestone columns rather than current status,
    # since status can move past delivered (e.g. to complained) without un-delivering it.
    sent = _count_messages(db, campaign.id, EmailMessage.accepted_at.isnot(None))
    delivered = _count_messages(db, campaign.id, EmailMessage.delivered_at.isnot(None))
    hard_bounces = _count_messages(db, campaign.id, EmailMessage.status == MessageStatus.BOUNCED)
    soft_bounces = _count_messages(
        db, campaign.id, EmailMessage.status == MessageStatus.SOFT_BOUNCED
    )
    complaints = _count_messages(db, campaign.id, EmailMessage.status == MessageStatus.COMPLAINED)
    failures = _count_messages(
        db, campaign.id, EmailMessage.status.in_([MessageStatus.FAILED, MessageStatus.REJECTED])
    )
    unique_opens = _count_messages(db, campaign.id, EmailMessage.first_opened_at.isnot(None))
    unique_clicks = _count_messages(db, campaign.id, EmailMessage.first_clicked_at.isnot(None))

    unsubscribes = (
        db.query(func.count(SubscriptionEvent.id))
        .filter(
            SubscriptionEvent.campaign_id == campaign.id,
            SubscriptionEvent.event_type == SubscriptionEventType.UNSUBSCRIBED,
        )
        .scalar()
        or 0
    )
    last_event_id = (
        db.query(func.max(EmailEvent.id)).filter(EmailEvent.campaign_id == campaign.id).scalar()
    )

    stats = db.get(CampaignStats, campaign.id)
    if stats is None:
        stats = CampaignStats(campaign_id=campaign.id)
        db.add(stats)

    stats.recipients = recipients
    stats.skipped = skipped
    stats.sent = sent
    stats.delivered = delivered
    stats.hard_bounces = hard_bounces
    stats.soft_bounces = soft_bounces
    stats.complaints = complaints
    stats.unique_opens = unique_opens
    stats.unique_clicks = unique_clicks
    stats.unsubscribes = unsubscribes
    stats.failures = failures
    stats.last_event_id = last_event_id
    stats.computed_at = datetime.now(UTC)

    db.commit()
    db.refresh(stats)
    return stats
