"""Public, token-based preference center. PREF-01..09, CMPY-07.

No login: a subscriber reaches these endpoints by clicking a link in an email, carrying a
signed, non-expiring token (see ``app.preferences.tokens``) instead of a bearer session
token. Every state change is appended to ``subscription_events`` per the rules in
docs/architecture/schema-v1.md section 4.
"""

from __future__ import annotations

import ipaddress
import uuid
from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.db.enums import ChangeSource
from app.preferences.models import SubscriptionEvent, SubscriptionEventType
from app.preferences.schemas import (
    PreferencesRead,
    PreferencesUpdate,
    UnsubscribeResponse,
)
from app.preferences.tokens import decode_preference_token
from app.subscribers.models import (
    ListMembership,
    MailingList,
    MembershipStatus,
    Subscriber,
    SubscriberStatus,
)
from app.suppressions.models import Suppression, SuppressionReason

router = APIRouter(prefix="/api/v1/preferences", tags=["preferences"])


def _client_ip(request: Request) -> str | None:
    host = request.client.host if request.client else None
    try:
        ipaddress.ip_address(host) if host else None
    except ValueError:
        return None
    return host


def _get_subscriber(db: Session, token: str) -> Subscriber:
    try:
        subscriber_id = decode_preference_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid preference token") from exc
    subscriber = db.get(Subscriber, subscriber_id)
    if subscriber is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subscriber not found")
    return subscriber


def _build_preferences_read(db: Session, subscriber: Subscriber) -> PreferencesRead:
    memberships = (
        db.query(ListMembership, MailingList)
        .join(MailingList, ListMembership.list_id == MailingList.id)
        .filter(
            ListMembership.subscriber_id == subscriber.id,
            MailingList.show_in_preferences.is_(True),
        )
        .all()
    )
    suppressed = (
        db.query(Suppression)
        .filter(
            Suppression.account_id == subscriber.account_id,
            Suppression.email == subscriber.email,
            Suppression.lifted_at.is_(None),
        )
        .first()
        is not None
    )
    return PreferencesRead(
        email=subscriber.email,
        email_frequency=subscriber.email_frequency,
        lists=[
            {"list_id": mailing_list.id, "name": mailing_list.name, "status": membership.status}
            for membership, mailing_list in memberships
        ],
        suppressed=suppressed,
        unsubscribed=subscriber.status == SubscriberStatus.UNSUBSCRIBED,
    )


def _log_event(
    db: Session,
    subscriber: Subscriber,
    event_type: SubscriptionEventType,
    *,
    source: ChangeSource,
    list_id: uuid.UUID | None = None,
    request: Request | None = None,
) -> None:
    db.add(
        SubscriptionEvent(
            account_id=subscriber.account_id,
            subscriber_id=subscriber.id,
            email=subscriber.email,
            event_type=event_type,
            list_id=list_id,
            source=source,
            ip_address=_client_ip(request) if request is not None else None,
            user_agent=request.headers.get("user-agent") if request is not None else None,
        )
    )


def _unsubscribe(
    db: Session, subscriber: Subscriber, *, source: ChangeSource, request: Request | None
) -> None:
    """Full account-wide unsubscribe (shared by the confirm-step and one-click endpoints)."""
    existing = (
        db.query(Suppression)
        .filter(
            Suppression.account_id == subscriber.account_id,
            Suppression.email == subscriber.email,
            Suppression.lifted_at.is_(None),
        )
        .first()
    )
    if existing is None:
        db.add(
            Suppression(
                account_id=subscriber.account_id,
                email=subscriber.email,
                reason=SuppressionReason.UNSUBSCRIBE,
                source=source,
            )
        )
    subscriber.status = SubscriberStatus.UNSUBSCRIBED
    subscriber.unsubscribed_at = datetime.now(UTC)
    _log_event(db, subscriber, SubscriptionEventType.UNSUBSCRIBED, source=source, request=request)
    db.commit()


@router.get("/{token}", response_model=PreferencesRead)
def get_preferences(token: str, db: Session = Depends(get_db)) -> PreferencesRead:
    subscriber = _get_subscriber(db, token)
    return _build_preferences_read(db, subscriber)


@router.patch("/{token}", response_model=PreferencesRead)
def update_preferences(
    token: str, body: PreferencesUpdate, request: Request, db: Session = Depends(get_db)
) -> PreferencesRead:
    subscriber = _get_subscriber(db, token)

    if body.email_frequency is not None:
        subscriber.email_frequency = body.email_frequency
        _log_event(
            db,
            subscriber,
            SubscriptionEventType.PROFILE_UPDATED,
            source=ChangeSource.PREFERENCE_CENTER,
            request=request,
        )

    for change in body.topics or []:
        membership = db.get(ListMembership, (change.list_id, subscriber.id))
        if membership is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "List membership not found")

        if change.opted_out:
            if membership.status != MembershipStatus.OPTED_OUT:
                membership.status = MembershipStatus.OPTED_OUT
                membership.removed_at = datetime.now(UTC)
                _log_event(
                    db,
                    subscriber,
                    SubscriptionEventType.LIST_OPT_OUT,
                    source=ChangeSource.PREFERENCE_CENTER,
                    list_id=change.list_id,
                    request=request,
                )
        else:
            if membership.status == MembershipStatus.OPTED_OUT:
                # The explicit re-opt-in path: the only one allowed to bypass the
                # opted_out -> active trigger guard (app/db/triggers.py).
                db.execute(text("SET LOCAL app.allow_resubscribe = 'on'"))
                membership.status = MembershipStatus.ACTIVE
                membership.removed_at = None
                _log_event(
                    db,
                    subscriber,
                    SubscriptionEventType.LIST_OPT_IN,
                    source=ChangeSource.PREFERENCE_CENTER,
                    list_id=change.list_id,
                    request=request,
                )

    db.commit()
    db.refresh(subscriber)
    return _build_preferences_read(db, subscriber)


@router.post("/{token}/unsubscribe", response_model=UnsubscribeResponse)
def unsubscribe(
    token: str, request: Request, db: Session = Depends(get_db)
) -> UnsubscribeResponse:
    subscriber = _get_subscriber(db, token)
    _unsubscribe(db, subscriber, source=ChangeSource.PREFERENCE_CENTER, request=request)
    return UnsubscribeResponse(unsubscribed=True)


@router.post("/one-click-unsubscribe/{token}", response_model=UnsubscribeResponse)
def one_click_unsubscribe(
    token: str, request: Request, db: Session = Depends(get_db)
) -> UnsubscribeResponse:
    """RFC 8058 List-Unsubscribe=One-Click target: bare POST, no body, no confirmation."""
    subscriber = _get_subscriber(db, token)
    _unsubscribe(db, subscriber, source=ChangeSource.ONE_CLICK_UNSUBSCRIBE, request=request)
    return UnsubscribeResponse(unsubscribed=True)
