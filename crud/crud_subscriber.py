from datetime import datetime, timezone
from typing import Optional, Sequence, List, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, func

from models.subscriber import (
    Subscriber, SubscriberStatus, SubscriberListMembership,
    SubscriberTag, SubscriberCustomFieldValue
)
from models.suppression import PreferenceAuditLog, PreferenceChangeType, PreferenceChangeSource
from schemas.subscriber import SubscriberCreate, SubscriberUpdate


def _now():
    return datetime.now(timezone.utc)


def get_subscriber(db: Session, subscriber_id: int) -> Optional[Subscriber]:
    return (
        db.query(Subscriber)
        .options(
            joinedload(Subscriber.list_memberships).joinedload(SubscriberListMembership.subscriber_list),
            joinedload(Subscriber.tag_associations).joinedload(SubscriberTag.tag),
            joinedload(Subscriber.custom_field_values),
        )
        .filter(Subscriber.id == subscriber_id)
        .first()
    )


def get_subscriber_by_email(db: Session, account_id: int, email: str) -> Optional[Subscriber]:
    return (
        db.query(Subscriber)
        .filter(Subscriber.account_id == account_id, Subscriber.email == email.lower().strip())
        .first()
    )


def list_subscribers(
    db: Session,
    account_id: int,
    *,
    page: int = 1,
    per_page: int = 50,
    q: Optional[str] = None,
    status: Optional[SubscriberStatus] = None,
    list_id: Optional[int] = None,
    tag_id: Optional[int] = None,
    consent_source: Optional[str] = None,
) -> Tuple[int, Sequence[Subscriber]]:
    query = db.query(Subscriber).filter(Subscriber.account_id == account_id)

    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Subscriber.email.ilike(like),
                Subscriber.first_name.ilike(like),
                Subscriber.last_name.ilike(like),
            )
        )
    if status:
        query = query.filter(Subscriber.status == status)
    if consent_source:
        query = query.filter(Subscriber.consent_source == consent_source)
    if list_id:
        query = query.join(
            SubscriberListMembership,
            SubscriberListMembership.subscriber_id == Subscriber.id,
        ).filter(SubscriberListMembership.list_id == list_id)
    if tag_id:
        query = query.join(
            SubscriberTag,
            SubscriberTag.subscriber_id == Subscriber.id,
        ).filter(SubscriberTag.tag_id == tag_id)

    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return total, items


def create_subscriber(
    db: Session, account_id: int, data: SubscriberCreate
) -> Tuple[Subscriber, bool]:
    """Returns (subscriber, created) — created=False means it was a duplicate."""
    email = data.email.lower().strip()
    existing = get_subscriber_by_email(db, account_id, email)
    if existing:
        return existing, False

    subscriber = Subscriber(
        account_id=account_id,
        email=email,
        first_name=data.first_name,
        last_name=data.last_name,
        status=data.status,
        consent_source=data.consent_source,
        consent_at=data.consent_at or _now(),
    )
    db.add(subscriber)
    db.flush()

    _sync_list_memberships(db, subscriber, data.list_ids or [])
    _sync_tags(db, subscriber, data.tag_ids or [])
    _sync_custom_fields(db, subscriber, data.custom_fields or [])

    _log_preference(db, subscriber.id, PreferenceChangeType.SUBSCRIBED, PreferenceChangeSource.MANUAL)

    db.commit()
    db.refresh(subscriber)
    return subscriber, True


def update_subscriber(
    db: Session, subscriber_id: int, data: SubscriberUpdate
) -> Optional[Subscriber]:
    subscriber = db.query(Subscriber).filter(Subscriber.id == subscriber_id).first()
    if not subscriber:
        return None

    old_status = subscriber.status

    update_data = data.model_dump(exclude_unset=True, exclude={"list_ids", "tag_ids", "custom_fields"})
    if "status" in update_data and update_data["status"] == SubscriberStatus.UNSUBSCRIBED:
        update_data["unsubscribed_at"] = _now()

    for key, value in update_data.items():
        setattr(subscriber, key, value)

    if data.list_ids is not None:
        _sync_list_memberships(db, subscriber, data.list_ids)
    if data.tag_ids is not None:
        _sync_tags(db, subscriber, data.tag_ids)
    if data.custom_fields is not None:
        _sync_custom_fields(db, subscriber, data.custom_fields)

    if "status" in update_data and update_data["status"] != old_status:
        _log_preference(
            db, subscriber.id,
            PreferenceChangeType.UNSUBSCRIBED if update_data["status"] == SubscriberStatus.UNSUBSCRIBED
            else PreferenceChangeType.SUBSCRIBED,
            PreferenceChangeSource.MANUAL,
            old_status=old_status.value,
            new_status=update_data["status"].value if hasattr(update_data["status"], "value") else str(update_data["status"]),
        )

    db.commit()
    db.refresh(subscriber)
    return subscriber


def delete_subscriber(db: Session, subscriber_id: int) -> bool:
    subscriber = db.query(Subscriber).filter(Subscriber.id == subscriber_id).first()
    if not subscriber:
        return False
    db.delete(subscriber)
    db.commit()
    return True


def bulk_delete(db: Session, account_id: int, ids: List[int]) -> int:
    deleted = (
        db.query(Subscriber)
        .filter(Subscriber.account_id == account_id, Subscriber.id.in_(ids))
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted


def bulk_unsubscribe(db: Session, account_id: int, ids: List[int]) -> int:
    now = _now()
    updated = (
        db.query(Subscriber)
        .filter(
            Subscriber.account_id == account_id,
            Subscriber.id.in_(ids),
            Subscriber.status == SubscriberStatus.SUBSCRIBED,
        )
        .update(
            {"status": SubscriberStatus.UNSUBSCRIBED, "unsubscribed_at": now},
            synchronize_session=False,
        )
    )
    db.commit()
    return updated


def get_preference_history(db: Session, subscriber_id: int) -> Sequence[PreferenceAuditLog]:
    return (
        db.query(PreferenceAuditLog)
        .filter(PreferenceAuditLog.subscriber_id == subscriber_id)
        .order_by(PreferenceAuditLog.created_at.desc())
        .all()
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _sync_list_memberships(db: Session, subscriber: Subscriber, list_ids: List[int]):
    db.query(SubscriberListMembership).filter(
        SubscriberListMembership.subscriber_id == subscriber.id
    ).delete(synchronize_session=False)
    for lid in list_ids:
        db.add(SubscriberListMembership(subscriber_id=subscriber.id, list_id=lid))


def _sync_tags(db: Session, subscriber: Subscriber, tag_ids: List[int]):
    db.query(SubscriberTag).filter(
        SubscriberTag.subscriber_id == subscriber.id
    ).delete(synchronize_session=False)
    for tid in tag_ids:
        db.add(SubscriberTag(subscriber_id=subscriber.id, tag_id=tid))


def _sync_custom_fields(db: Session, subscriber: Subscriber, fields):
    for cf in fields:
        existing = (
            db.query(SubscriberCustomFieldValue)
            .filter(
                SubscriberCustomFieldValue.subscriber_id == subscriber.id,
                SubscriberCustomFieldValue.custom_field_id == cf.custom_field_id,
            )
            .first()
        )
        if existing:
            existing.value = cf.value
        else:
            db.add(SubscriberCustomFieldValue(
                subscriber_id=subscriber.id,
                custom_field_id=cf.custom_field_id,
                value=cf.value,
            ))


def _log_preference(
    db: Session,
    subscriber_id: int,
    change_type: PreferenceChangeType,
    source: PreferenceChangeSource,
    old_status: Optional[str] = None,
    new_status: Optional[str] = None,
    metadata: Optional[dict] = None,
):
    log = PreferenceAuditLog(
        subscriber_id=subscriber_id,
        change_type=change_type,
        source=source,
        old_status=old_status,
        new_status=new_status,
        metadata_json=metadata,
    )
    db.add(log)
