import secrets
from datetime import datetime, timezone
from typing import Optional, Sequence
from sqlalchemy.orm import Session

from models.subscriber import Subscriber, SubscriberStatus
from models.suppression import (
    SuppressionList, SuppressionReason, UnsubscribeToken,
    PreferenceAuditLog, PreferenceChangeType, PreferenceChangeSource
)


def _now():
    return datetime.now(timezone.utc)


# ── Suppression ───────────────────────────────────────────────────────────────

def is_suppressed(db: Session, account_id: int, email: str) -> bool:
    return (
        db.query(SuppressionList)
        .filter(SuppressionList.account_id == account_id, SuppressionList.email == email.lower())
        .first()
    ) is not None


def add_to_suppression(
    db: Session,
    account_id: int,
    email: str,
    reason: SuppressionReason,
    campaign_id: Optional[int] = None,
) -> SuppressionList:
    existing = (
        db.query(SuppressionList)
        .filter(SuppressionList.account_id == account_id, SuppressionList.email == email.lower())
        .first()
    )
    if existing:
        existing.reason = reason
        existing.suppressed_at = _now()
        db.commit()
        return existing

    entry = SuppressionList(
        account_id=account_id,
        email=email.lower(),
        reason=reason,
        suppressed_at=_now(),
        source_campaign_id=campaign_id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_suppression_list(db: Session, account_id: int) -> Sequence[SuppressionList]:
    return (
        db.query(SuppressionList)
        .filter(SuppressionList.account_id == account_id)
        .order_by(SuppressionList.suppressed_at.desc())
        .all()
    )


# ── Unsubscribe Tokens ────────────────────────────────────────────────────────

def create_unsubscribe_token(
    db: Session, subscriber_id: int, campaign_id: Optional[int] = None
) -> UnsubscribeToken:
    token = secrets.token_urlsafe(32)
    ut = UnsubscribeToken(subscriber_id=subscriber_id, campaign_id=campaign_id, token=token)
    db.add(ut)
    db.commit()
    db.refresh(ut)
    return ut


def get_token(db: Session, token: str) -> Optional[UnsubscribeToken]:
    return (
        db.query(UnsubscribeToken)
        .filter(UnsubscribeToken.token == token, UnsubscribeToken.is_used == False)
        .first()
    )


def process_unsubscribe(db: Session, token: str) -> Optional[Subscriber]:
    """Mark token used, set subscriber to unsubscribed, log change."""
    ut = get_token(db, token)
    if not ut:
        return None

    subscriber = db.query(Subscriber).filter(Subscriber.id == ut.subscriber_id).first()
    if not subscriber:
        return None

    old_status = subscriber.status.value
    subscriber.status = SubscriberStatus.UNSUBSCRIBED
    subscriber.unsubscribed_at = _now()

    ut.is_used = True
    ut.used_at = _now()

    # Add to suppression list
    add_to_suppression(
        db,
        account_id=subscriber.account_id,
        email=subscriber.email,
        reason=SuppressionReason.UNSUBSCRIBED,
        campaign_id=ut.campaign_id,
    )

    db.add(PreferenceAuditLog(
        subscriber_id=subscriber.id,
        change_type=PreferenceChangeType.UNSUBSCRIBED,
        source=PreferenceChangeSource.PREFERENCE_CENTER,
        old_status=old_status,
        new_status=SubscriberStatus.UNSUBSCRIBED.value,
    ))

    db.commit()
    db.refresh(subscriber)
    return subscriber


def get_preference_center_data(db: Session, token: str) -> Optional[dict]:
    ut = get_token(db, token)
    if not ut:
        return None

    subscriber = (
        db.query(Subscriber)
        .filter(Subscriber.id == ut.subscriber_id)
        .first()
    )
    if not subscriber:
        return None

    from models.subscriber import SubscriberListMembership, SubscriberList
    memberships = (
        db.query(SubscriberList)
        .join(SubscriberListMembership, SubscriberListMembership.list_id == SubscriberList.id)
        .filter(SubscriberListMembership.subscriber_id == subscriber.id)
        .all()
    )

    return {
        "subscriber_id": subscriber.id,
        "email": subscriber.email,
        "first_name": subscriber.first_name,
        "last_name": subscriber.last_name,
        "status": subscriber.status.value,
        "lists": [{"id": l.id, "name": l.name} for l in memberships],
    }
