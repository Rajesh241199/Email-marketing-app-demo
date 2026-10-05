"""Tests for the public webhook + tracking endpoints.

Wires the events router onto the shared app at import time (see the note in
test_preferences.py). All endpoints here are public (no auth), matching provider
webhooks and pixel/redirect links embedded in emails.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.accounts.models import Account
from app.analytics.models import EmailEvent, EmailMessage, EmailProvider, MessageStatus
from app.automations.models import Automation, AutomationTrigger
from app.events.router import router as events_router
from app.main import app as main_app
from app.subscribers.models import MailingList, Subscriber, SubscriberStatus
from app.suppressions.models import Suppression

if not getattr(main_app.state, "_events_wired", False):
    main_app.include_router(events_router)
    main_app.state._events_wired = True


def _make_account(db: Session) -> Account:
    account = Account(
        name="Acme Co", country_code="US", address_line1="1 Main St", city="Springfield"
    )
    db.add(account)
    db.flush()
    return account


def _make_automation(db: Session, account: Account) -> Automation:
    """A message must have exactly one origin (campaign or automation); use a bare
    automation so these tests don't need the campaigns domain's full send pipeline."""
    mailing_list = MailingList(account_id=account.id, name="Origin list")
    db.add(mailing_list)
    db.flush()
    automation = Automation(
        account_id=account.id,
        name="Test automation",
        trigger_type=AutomationTrigger.LIST_JOINED,
        trigger_list_id=mailing_list.id,
    )
    db.add(automation)
    db.flush()
    return automation


def _make_message(
    db: Session,
    account: Account,
    *,
    subscriber: Subscriber | None = None,
    provider_message_id: str = "ses-1",
) -> EmailMessage:
    automation = _make_automation(db, account)
    message = EmailMessage(
        account_id=account.id,
        subscriber_id=subscriber.id if subscriber else None,
        email=subscriber.email if subscriber else "nobody@example.com",
        automation_id=automation.id,
        provider=EmailProvider.SES,
        provider_message_id=provider_message_id,
        status=MessageStatus.ACCEPTED,
        accepted_at=datetime.now(UTC),
    )
    db.add(message)
    db.flush()
    return message


def test_webhook_dedup_applies_side_effects_once(
    client: TestClient, db_session: Session
) -> None:
    account = _make_account(db_session)
    message = _make_message(db_session, account)
    db_session.commit()

    body = {
        "provider": "ses",
        "provider_event_id": "evt-1",
        "provider_message_id": message.provider_message_id,
        "event_type": "delivery",
        "occurred_at": datetime.now(UTC).isoformat(),
    }
    first = client.post("/api/v1/events/webhook", json=body)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "processed"

    second = client.post("/api/v1/events/webhook", json=body)
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "duplicate"

    events = db_session.query(EmailEvent).filter(EmailEvent.message_id == message.id).all()
    assert len(events) == 1

    db_session.refresh(message)
    assert message.status == MessageStatus.DELIVERED
    assert message.delivered_at is not None


def test_webhook_unknown_message_is_ignored(client: TestClient, db_session: Session) -> None:
    resp = client.post(
        "/api/v1/events/webhook",
        json={
            "provider": "ses",
            "provider_event_id": "evt-unknown",
            "provider_message_id": "does-not-exist",
            "event_type": "delivery",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
    assert db_session.query(EmailEvent).count() == 0


def test_permanent_bounce_creates_suppression_and_suppresses_subscriber(
    client: TestClient, db_session: Session
) -> None:
    account = _make_account(db_session)
    subscriber = Subscriber(account_id=account.id, email="bouncy@example.com")
    db_session.add(subscriber)
    db_session.flush()
    message = _make_message(
        db_session, account, subscriber=subscriber, provider_message_id="ses-bounce"
    )
    db_session.commit()

    resp = client.post(
        "/api/v1/events/webhook",
        json={
            "provider": "ses",
            "provider_event_id": "evt-bounce",
            "provider_message_id": message.provider_message_id,
            "event_type": "bounce",
            "bounce_type": "permanent",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )
    assert resp.status_code == 200, resp.text

    db_session.refresh(message)
    assert message.status == MessageStatus.BOUNCED
    assert message.bounced_at is not None

    suppression = (
        db_session.query(Suppression)
        .filter(Suppression.account_id == account.id, Suppression.email == subscriber.email)
        .first()
    )
    assert suppression is not None
    assert suppression.reason.value == "hard_bounce"

    db_session.refresh(subscriber)
    assert subscriber.status == SubscriberStatus.SUPPRESSED


def test_transient_bounce_does_not_suppress(client: TestClient, db_session: Session) -> None:
    account = _make_account(db_session)
    message = _make_message(db_session, account, provider_message_id="ses-soft")
    db_session.commit()

    resp = client.post(
        "/api/v1/events/webhook",
        json={
            "provider": "ses",
            "provider_event_id": "evt-soft",
            "provider_message_id": message.provider_message_id,
            "event_type": "bounce",
            "bounce_type": "transient",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )
    assert resp.status_code == 200, resp.text

    db_session.refresh(message)
    assert message.status == MessageStatus.SOFT_BOUNCED

    assert (
        db_session.query(Suppression)
        .filter(Suppression.account_id == account.id, Suppression.email == message.email)
        .first()
        is None
    )


def test_tracking_pixel_returns_gif_and_records_open(
    client: TestClient, db_session: Session
) -> None:
    account = _make_account(db_session)
    message = _make_message(db_session, account, provider_message_id="ses-open")
    db_session.commit()

    resp = client.get(f"/api/v1/events/track/open/{message.id}.gif")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/gif"
    assert len(resp.content) > 0

    db_session.refresh(message)
    assert message.first_opened_at is not None

    events = db_session.query(EmailEvent).filter(EmailEvent.message_id == message.id).all()
    assert len(events) == 1
    assert events[0].provider == EmailProvider.TRACKING

    first_opened_at = message.first_opened_at
    # Loading the pixel again must not move first_opened_at (first-open only).
    client.get(f"/api/v1/events/track/open/{message.id}.gif")
    db_session.refresh(message)
    assert message.first_opened_at == first_opened_at


def test_tracking_click_redirects_and_records_click(
    client: TestClient, db_session: Session
) -> None:
    account = _make_account(db_session)
    message = _make_message(db_session, account, provider_message_id="ses-click")
    db_session.commit()

    # link_id is omitted: it would have to reference a real campaign_links row (FK), and
    # this message has an automation origin, not a campaign one.
    resp = client.get(
        f"/api/v1/events/track/click/{message.id}",
        params={"url": "https://example.com/landing"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "https://example.com/landing"

    db_session.refresh(message)
    assert message.first_clicked_at is not None
