"""Public provider-webhook and open/click tracking endpoints.

No auth: providers call the webhook directly, and tracking pixels/links are embedded in
emails sent to recipients who never log in. Idempotency (ON CONFLICT DO NOTHING on
``(provider, provider_event_id)``) is what keeps a redelivered webhook or a pixel loaded
twice from double-counting - see docs/architecture/schema-v1.md section 7.
"""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.analytics.models import (
    BounceType,
    EmailEvent,
    EmailEventType,
    EmailMessage,
    EmailProvider,
    MessageStatus,
)
from app.core.deps import get_db
from app.db.enums import ChangeSource
from app.events.schemas import WebhookEventIn, WebhookResult
from app.subscribers.models import Subscriber, SubscriberStatus
from app.suppressions.models import Suppression, SuppressionReason

router = APIRouter(prefix="/api/v1/events", tags=["events"])

# 1x1 transparent GIF, served as-is for the open-tracking pixel.
_TRANSPARENT_GIF = base64.b64decode("R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==")


def _insert_event(
    db: Session,
    *,
    account_id: uuid.UUID,
    message: EmailMessage | None,
    provider: EmailProvider,
    provider_event_id: str,
    event_type: EmailEventType,
    occurred_at: datetime,
    bounce_type: BounceType | None,
    link_id: uuid.UUID | None,
    payload: dict | None,
) -> bool:
    """Insert, skipping duplicates. Returns True only if a new row was actually inserted."""
    stmt = (
        pg_insert(EmailEvent.__table__)
        .values(
            account_id=account_id,
            message_id=message.id if message is not None else None,
            campaign_id=message.campaign_id if message is not None else None,
            provider=provider,
            provider_event_id=provider_event_id,
            event_type=event_type,
            bounce_type=bounce_type,
            link_id=link_id,
            occurred_at=occurred_at,
            payload=payload,
        )
        .on_conflict_do_nothing(index_elements=["provider", "provider_event_id"])
    )
    result = db.execute(stmt)
    db.flush()
    return result.rowcount > 0


def _suppress(db: Session, message: EmailMessage, reason: SuppressionReason) -> None:
    existing = (
        db.query(Suppression)
        .filter(
            Suppression.account_id == message.account_id,
            Suppression.email == message.email,
            Suppression.lifted_at.is_(None),
        )
        .first()
    )
    if existing is None:
        db.add(
            Suppression(
                account_id=message.account_id,
                email=message.email,
                reason=reason,
                source=ChangeSource.PROVIDER_EVENT,
            )
        )
    if message.subscriber_id is not None:
        subscriber = db.get(Subscriber, message.subscriber_id)
        if subscriber is not None:
            subscriber.status = SubscriberStatus.SUPPRESSED


def _apply_side_effects(
    db: Session,
    message: EmailMessage,
    event_type: EmailEventType,
    occurred_at: datetime,
    bounce_type: BounceType | None,
) -> None:
    if event_type == EmailEventType.DELIVERY:
        message.status = MessageStatus.DELIVERED
        message.delivered_at = occurred_at
    elif event_type == EmailEventType.BOUNCE:
        if bounce_type == BounceType.PERMANENT:
            message.status = MessageStatus.BOUNCED
            message.bounced_at = occurred_at
            _suppress(db, message, SuppressionReason.HARD_BOUNCE)
        else:
            message.status = MessageStatus.SOFT_BOUNCED
    elif event_type == EmailEventType.COMPLAINT:
        message.status = MessageStatus.COMPLAINED
        message.complained_at = occurred_at
        _suppress(db, message, SuppressionReason.COMPLAINT)
    elif event_type == EmailEventType.REJECT:
        message.status = MessageStatus.REJECTED
    elif event_type == EmailEventType.OPEN:
        if message.first_opened_at is None:
            message.first_opened_at = occurred_at
    elif event_type == EmailEventType.CLICK:
        if message.first_clicked_at is None:
            message.first_clicked_at = occurred_at
    # SEND / DELIVERY_DELAY / UNSUBSCRIBE: no derived-state side effect defined in scope.


@router.post("/webhook", response_model=WebhookResult)
def receive_webhook(body: WebhookEventIn, db: Session = Depends(get_db)) -> WebhookResult:
    message: EmailMessage | None = None
    if body.provider_message_id is not None:
        message = (
            db.query(EmailMessage)
            .filter(
                EmailMessage.provider == body.provider,
                EmailMessage.provider_message_id == body.provider_message_id,
            )
            .first()
        )

    if message is None:
        # email_events.account_id is NOT NULL and the only way we know the account here is
        # via the message the event is about; a real SES/SNS payload carries account
        # context independently, which this simplified flat body does not. Without a
        # resolvable message we have nothing safe to insert, so the event is dropped.
        return WebhookResult(status="ignored", reason="unknown provider_message_id")

    inserted = _insert_event(
        db,
        account_id=message.account_id,
        message=message,
        provider=body.provider,
        provider_event_id=body.provider_event_id,
        event_type=body.event_type,
        occurred_at=body.occurred_at,
        bounce_type=body.bounce_type,
        link_id=body.link_id,
        payload=body.payload,
    )
    if inserted:
        _apply_side_effects(db, message, body.event_type, body.occurred_at, body.bounce_type)
    db.commit()
    return WebhookResult(status="processed" if inserted else "duplicate")


@router.get("/track/open/{message_id}.gif")
def track_open(message_id: int, db: Session = Depends(get_db)) -> Response:
    occurred_at = datetime.now(UTC)
    minute_bucket = occurred_at.strftime("%Y%m%d%H%M")
    provider_event_id = f"open:{message_id}:{minute_bucket}"

    message = db.get(EmailMessage, message_id)
    if message is not None:
        inserted = _insert_event(
            db,
            account_id=message.account_id,
            message=message,
            provider=EmailProvider.TRACKING,
            provider_event_id=provider_event_id,
            event_type=EmailEventType.OPEN,
            occurred_at=occurred_at,
            bounce_type=None,
            link_id=None,
            payload=None,
        )
        if inserted:
            _apply_side_effects(db, message, EmailEventType.OPEN, occurred_at, None)
        db.commit()

    return Response(content=_TRANSPARENT_GIF, media_type="image/gif")


@router.get("/track/click/{message_id}")
def track_click(
    message_id: int,
    url: str,
    link_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    occurred_at = datetime.now(UTC)
    minute_bucket = occurred_at.strftime("%Y%m%d%H%M")
    provider_event_id = f"click:{message_id}:{link_id}:{minute_bucket}"

    message = db.get(EmailMessage, message_id)
    if message is not None:
        inserted = _insert_event(
            db,
            account_id=message.account_id,
            message=message,
            provider=EmailProvider.TRACKING,
            provider_event_id=provider_event_id,
            event_type=EmailEventType.CLICK,
            occurred_at=occurred_at,
            bounce_type=None,
            link_id=link_id,
            payload=None,
        )
        if inserted:
            _apply_side_effects(db, message, EmailEventType.CLICK, occurred_at, None)
        db.commit()

    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)
