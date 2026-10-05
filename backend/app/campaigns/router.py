"""Campaign CRUD, audience rules, confirm/freeze/send lifecycle, test sends, links.

Deferred (no infra for it yet, see docs/architecture/schema-v1.md / the bootstrap plan):
actual provider dispatch (send() only queues `email_messages`, nothing transmits them),
the scheduler that would flip a SCHEDULED campaign to SENDING at `scheduled_at`, and deep
pre-send content validation (link/footer rendering checks) - confirm() checks the fields
the schema can check directly (sender verified, subject/content present, an audience
exists, scheduled time is in the future) and no more.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.models import User
from app.campaigns.eligibility import freeze_campaign
from app.campaigns.models import (
    Campaign,
    CampaignAudience,
    CampaignLink,
    CampaignRecipient,
    CampaignStatus,
    RecipientStatus,
    TestSend,
)
from app.campaigns.schemas import (
    AudienceCreate,
    AudienceRead,
    CampaignCreate,
    CampaignLinkCreate,
    CampaignLinkRead,
    CampaignRead,
    CampaignUpdate,
    FreezeResult,
    RecipientRead,
    ScheduleRequest,
    TestSendRead,
    TestSendRequest,
)
from app.core.deps import get_current_account_id, get_current_user, get_db
from app.senders.models import Sender, SenderStatus

router = APIRouter(prefix="/api/v1/campaigns", tags=["campaigns"])


def _get_campaign(db: Session, account_id: uuid.UUID, campaign_id: uuid.UUID) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.account_id != account_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaign not found")
    return campaign


def _require_draft(campaign: Campaign) -> None:
    if campaign.status != CampaignStatus.DRAFT:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Campaign must be in draft status (currently {campaign.status.value})",
        )


@router.post("", response_model=CampaignRead, status_code=status.HTTP_201_CREATED)
def create_campaign(
    body: CampaignCreate,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> Campaign:
    campaign = Campaign(account_id=account_id, **body.model_dump())
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


@router.get("", response_model=list[CampaignRead])
def list_campaigns(
    status_filter: CampaignStatus | None = None,
    limit: int = 50,
    offset: int = 0,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> list[Campaign]:
    query = db.query(Campaign).filter(Campaign.account_id == account_id)
    if status_filter is not None:
        query = query.filter(Campaign.status == status_filter)
    return (
        query.order_by(Campaign.created_at.desc()).offset(offset).limit(min(limit, 200)).all()
    )


@router.get("/{campaign_id}", response_model=CampaignRead)
def get_campaign(
    campaign_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> Campaign:
    return _get_campaign(db, account_id, campaign_id)


@router.patch("/{campaign_id}", response_model=CampaignRead)
def update_campaign(
    campaign_id: uuid.UUID,
    body: CampaignUpdate,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> Campaign:
    campaign = _get_campaign(db, account_id, campaign_id)
    _require_draft(campaign)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(campaign, field, value)
    db.commit()
    db.refresh(campaign)
    return campaign


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_campaign(
    campaign_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> None:
    campaign = _get_campaign(db, account_id, campaign_id)
    _require_draft(campaign)
    db.delete(campaign)
    db.commit()


# --- Audience rules --------------------------------------------------------------------


@router.post(
    "/{campaign_id}/audiences", response_model=AudienceRead, status_code=status.HTTP_201_CREATED
)
def add_audience_rule(
    campaign_id: uuid.UUID,
    body: AudienceCreate,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> CampaignAudience:
    campaign = _get_campaign(db, account_id, campaign_id)
    _require_draft(campaign)
    audience = CampaignAudience(campaign_id=campaign.id, **body.model_dump())
    db.add(audience)
    db.commit()
    db.refresh(audience)
    return audience


@router.get("/{campaign_id}/audiences", response_model=list[AudienceRead])
def list_audience_rules(
    campaign_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> list[CampaignAudience]:
    campaign = _get_campaign(db, account_id, campaign_id)
    return db.query(CampaignAudience).filter(CampaignAudience.campaign_id == campaign.id).all()


@router.delete("/{campaign_id}/audiences/{audience_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_audience_rule(
    campaign_id: uuid.UUID,
    audience_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> None:
    campaign = _get_campaign(db, account_id, campaign_id)
    _require_draft(campaign)
    audience = db.get(CampaignAudience, audience_id)
    if audience is None or audience.campaign_id != campaign.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Audience rule not found")
    db.delete(audience)
    db.commit()


# --- Lifecycle --------------------------------------------------------------------------


@router.post("/{campaign_id}/confirm", response_model=CampaignRead)
def confirm_campaign(
    campaign_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> Campaign:
    campaign = _get_campaign(db, account_id, campaign_id)
    _require_draft(campaign)

    errors: list[str] = []
    sender = db.get(Sender, campaign.sender_id) if campaign.sender_id else None
    if sender is None:
        errors.append("sender is required")
    elif sender.status != SenderStatus.VERIFIED:
        errors.append("sender is not verified")
    if not campaign.subject:
        errors.append("subject is required")
    if not campaign.html and not campaign.content_json:
        errors.append("content is required")
    has_audience = (
        db.query(CampaignAudience).filter(CampaignAudience.campaign_id == campaign.id).first()
        is not None
    )
    if not has_audience:
        errors.append("at least one audience rule is required")
    if errors:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, {"errors": errors})

    campaign.confirmed_by = current_user.id
    campaign.confirmed_at = datetime.now(UTC)
    db.commit()
    db.refresh(campaign)
    return campaign


@router.post("/{campaign_id}/freeze", response_model=FreezeResult)
def freeze(
    campaign_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> FreezeResult:
    campaign = _get_campaign(db, account_id, campaign_id)
    if campaign.confirmed_at is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Campaign must be confirmed first")
    if campaign.audience_frozen_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Campaign audience is already frozen")

    eligible_count, skipped_count = freeze_campaign(db, campaign)
    db.commit()
    return FreezeResult(
        eligible_count=eligible_count,
        skipped_count=skipped_count,
        audience_frozen_at=campaign.audience_frozen_at,
    )


@router.get("/{campaign_id}/recipients", response_model=list[RecipientRead])
def list_recipients(
    campaign_id: uuid.UUID,
    status_filter: RecipientStatus | None = None,
    limit: int = 50,
    offset: int = 0,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> list[CampaignRecipient]:
    campaign = _get_campaign(db, account_id, campaign_id)
    query = db.query(CampaignRecipient).filter(CampaignRecipient.campaign_id == campaign.id)
    if status_filter is not None:
        query = query.filter(CampaignRecipient.status == status_filter)
    return query.order_by(CampaignRecipient.id).offset(offset).limit(min(limit, 200)).all()


@router.post("/{campaign_id}/schedule", response_model=CampaignRead)
def schedule_campaign(
    campaign_id: uuid.UUID,
    body: ScheduleRequest,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> Campaign:
    campaign = _get_campaign(db, account_id, campaign_id)
    if campaign.confirmed_at is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Campaign must be confirmed first")
    if body.scheduled_at <= datetime.now(UTC):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "scheduled_at must be in the future")

    campaign.scheduled_at = body.scheduled_at
    campaign.status = CampaignStatus.SCHEDULED
    db.commit()
    db.refresh(campaign)
    return campaign


@router.post("/{campaign_id}/unschedule", response_model=CampaignRead)
def unschedule_campaign(
    campaign_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> Campaign:
    """BR-03: a scheduled campaign returning to draft loses its frozen audience."""
    campaign = _get_campaign(db, account_id, campaign_id)
    if campaign.status != CampaignStatus.SCHEDULED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Campaign is not scheduled")

    db.query(CampaignRecipient).filter(CampaignRecipient.campaign_id == campaign.id).delete()
    campaign.audience_frozen_at = None
    campaign.confirmed_at = None
    campaign.confirmed_by = None
    campaign.scheduled_at = None
    campaign.eligible_count = None
    campaign.status = CampaignStatus.DRAFT
    db.commit()
    db.refresh(campaign)
    return campaign


@router.post("/{campaign_id}/send", response_model=CampaignRead)
def send_campaign(
    campaign_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> Campaign:
    """Freezes the audience if needed, then queues one `email_messages` row per pending
    recipient. Nothing dispatches those rows yet - that's the deferred provider-worker piece.
    """
    campaign = _get_campaign(db, account_id, campaign_id)
    if campaign.confirmed_at is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Campaign must be confirmed first")
    if campaign.status not in (CampaignStatus.DRAFT, CampaignStatus.SCHEDULED):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Cannot send a campaign in status {campaign.status.value}"
        )

    if campaign.audience_frozen_at is None:
        freeze_campaign(db, campaign)

    from app.analytics.models import EmailMessage, EmailProvider, MessageStatus

    pending = (
        db.query(CampaignRecipient)
        .filter(
            CampaignRecipient.campaign_id == campaign.id,
            CampaignRecipient.status == RecipientStatus.PENDING,
        )
        .all()
    )
    now = datetime.now(UTC)
    for recipient in pending:
        db.add(
            EmailMessage(
                account_id=campaign.account_id,
                subscriber_id=recipient.subscriber_id,
                email=recipient.email,
                campaign_id=campaign.id,
                campaign_recipient_id=recipient.id,
                status=MessageStatus.QUEUED,
                provider=EmailProvider.SES,
            )
        )
        recipient.status = RecipientStatus.QUEUED
        recipient.status_changed_at = now

    campaign.sending_started_at = now
    campaign.status = CampaignStatus.SENDING
    db.commit()
    db.refresh(campaign)
    return campaign


@router.post("/{campaign_id}/cancel", response_model=CampaignRead)
def cancel_campaign(
    campaign_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> Campaign:
    campaign = _get_campaign(db, account_id, campaign_id)
    cancellable = (CampaignStatus.DRAFT, CampaignStatus.SCHEDULED, CampaignStatus.SENDING)
    if campaign.status not in cancellable:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Cannot cancel a campaign in status {campaign.status.value}",
        )

    db.query(CampaignRecipient).filter(
        CampaignRecipient.campaign_id == campaign.id,
        CampaignRecipient.status == RecipientStatus.PENDING,
    ).update({"status": RecipientStatus.CANCELLED})

    campaign.status = CampaignStatus.CANCELLED
    campaign.cancelled_at = datetime.now(UTC)
    db.commit()
    db.refresh(campaign)
    return campaign


# --- Test sends + links -----------------------------------------------------------------


@router.post(
    "/{campaign_id}/test-send", response_model=TestSendRead, status_code=status.HTTP_201_CREATED
)
def test_send(
    campaign_id: uuid.UUID,
    body: TestSendRequest,
    current_user: User = Depends(get_current_user),
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> TestSend:
    """Stub: records the attempt, does not actually transmit an email (no provider wired up)."""
    campaign = _get_campaign(db, account_id, campaign_id)
    test = TestSend(campaign_id=campaign.id, sent_by=current_user.id, to_emails=body.to_emails)
    db.add(test)
    db.commit()
    db.refresh(test)
    return test


@router.post(
    "/{campaign_id}/links", response_model=CampaignLinkRead, status_code=status.HTTP_201_CREATED
)
def add_link(
    campaign_id: uuid.UUID,
    body: CampaignLinkCreate,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> CampaignLink:
    campaign = _get_campaign(db, account_id, campaign_id)
    link = CampaignLink(campaign_id=campaign.id, **body.model_dump())
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


@router.get("/{campaign_id}/links", response_model=list[CampaignLinkRead])
def list_links(
    campaign_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> list[CampaignLink]:
    campaign = _get_campaign(db, account_id, campaign_id)
    return db.query(CampaignLink).filter(CampaignLink.campaign_id == campaign.id).all()


@router.delete("/{campaign_id}/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_link(
    campaign_id: uuid.UUID,
    link_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> None:
    campaign = _get_campaign(db, account_id, campaign_id)
    link = db.get(CampaignLink, link_id)
    if link is None or link.campaign_id != campaign.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")
    db.delete(link)
    db.commit()
