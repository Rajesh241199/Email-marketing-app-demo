"""Tests for the public, token-based preference center.

The preference-center router isn't wired into ``app.main`` (per the task's integration
boundary), so this module wires it onto the shared app at import time, the same way the
other new-domain test modules do. Registration is idempotent across repeated imports.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.accounts.models import Account
from app.db.enums import EmailFrequency
from app.main import app as main_app
from app.preferences.models import SubscriptionEvent, SubscriptionEventType
from app.preferences.router import router as preferences_router
from app.preferences.tokens import create_preference_token
from app.subscribers.models import ListMembership, MailingList, MembershipStatus, Subscriber
from app.suppressions.models import Suppression

if not getattr(main_app.state, "_preferences_wired", False):
    main_app.include_router(preferences_router)
    main_app.state._preferences_wired = True


def _make_account(db: Session) -> Account:
    account = Account(
        name="Acme Co", country_code="US", address_line1="1 Main St", city="Springfield"
    )
    db.add(account)
    db.flush()
    return account


def _make_subscriber(
    db: Session, account: Account, email: str = "subscriber@example.com"
) -> Subscriber:
    subscriber = Subscriber(account_id=account.id, email=email)
    db.add(subscriber)
    db.flush()
    return subscriber


def test_get_preferences_round_trip(client: TestClient, db_session: Session) -> None:
    account = _make_account(db_session)
    subscriber = _make_subscriber(db_session, account)
    db_session.commit()
    token = create_preference_token(subscriber.id)

    resp = client.get(f"/api/v1/preferences/{token}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["email"] == "subscriber@example.com"
    assert body["email_frequency"] == "all"
    assert body["lists"] == []
    assert body["suppressed"] is False
    assert body["unsubscribed"] is False


def test_get_preferences_invalid_token_rejected(client: TestClient) -> None:
    resp = client.get("/api/v1/preferences/not-a-real-token")
    assert resp.status_code == 401


def test_update_frequency_logs_event(client: TestClient, db_session: Session) -> None:
    account = _make_account(db_session)
    subscriber = _make_subscriber(db_session, account)
    db_session.commit()
    token = create_preference_token(subscriber.id)

    resp = client.patch(f"/api/v1/preferences/{token}", json={"email_frequency": "essential_only"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["email_frequency"] == "essential_only"

    db_session.refresh(subscriber)
    assert subscriber.email_frequency == EmailFrequency.ESSENTIAL_ONLY

    events = (
        db_session.query(SubscriptionEvent)
        .filter(SubscriptionEvent.subscriber_id == subscriber.id)
        .all()
    )
    assert len(events) == 1
    assert events[0].event_type == SubscriptionEventType.PROFILE_UPDATED


def test_topic_opt_out_then_opt_back_in(client: TestClient, db_session: Session) -> None:
    account = _make_account(db_session)
    subscriber = _make_subscriber(db_session, account)
    mailing_list = MailingList(account_id=account.id, name="Weekly Newsletter")
    db_session.add(mailing_list)
    db_session.flush()
    membership = ListMembership(list_id=mailing_list.id, subscriber_id=subscriber.id)
    db_session.add(membership)
    db_session.commit()
    token = create_preference_token(subscriber.id)

    # Opt out.
    resp = client.patch(
        f"/api/v1/preferences/{token}",
        json={"topics": [{"list_id": str(mailing_list.id), "opted_out": True}]},
    )
    assert resp.status_code == 200, resp.text
    lists = {row["list_id"]: row["status"] for row in resp.json()["lists"]}
    assert lists[str(mailing_list.id)] == "opted_out"

    db_session.refresh(membership)
    assert membership.status == MembershipStatus.OPTED_OUT

    # A direct, flag-less re-activation would be rejected by the DB trigger; confirm that
    # without going through the endpoint (sanity-checking the trigger is actually armed).
    # (We don't test this path directly here to avoid leaving the session in an aborted
    # transaction state; the endpoint test below exercises the allowed path.)

    # Opt back in - this is the explicit re-opt-in path that sets
    # SET LOCAL app.allow_resubscribe = 'on' before the UPDATE.
    resp = client.patch(
        f"/api/v1/preferences/{token}",
        json={"topics": [{"list_id": str(mailing_list.id), "opted_out": False}]},
    )
    assert resp.status_code == 200, resp.text
    lists = {row["list_id"]: row["status"] for row in resp.json()["lists"]}
    assert lists[str(mailing_list.id)] == "active"

    db_session.refresh(membership)
    assert membership.status == MembershipStatus.ACTIVE

    events = (
        db_session.query(SubscriptionEvent)
        .filter(SubscriptionEvent.subscriber_id == subscriber.id)
        .order_by(SubscriptionEvent.id)
        .all()
    )
    assert [e.event_type for e in events] == [
        SubscriptionEventType.LIST_OPT_OUT,
        SubscriptionEventType.LIST_OPT_IN,
    ]


def test_unknown_list_membership_404(client: TestClient, db_session: Session) -> None:
    account = _make_account(db_session)
    subscriber = _make_subscriber(db_session, account)
    other_list = MailingList(account_id=account.id, name="Not a member")
    db_session.add(other_list)
    db_session.commit()
    token = create_preference_token(subscriber.id)

    resp = client.patch(
        f"/api/v1/preferences/{token}",
        json={"topics": [{"list_id": str(other_list.id), "opted_out": True}]},
    )
    assert resp.status_code == 404


def test_unsubscribe_writes_suppression_and_status(client: TestClient, db_session: Session) -> None:
    account = _make_account(db_session)
    subscriber = _make_subscriber(db_session, account)
    db_session.commit()
    token = create_preference_token(subscriber.id)

    resp = client.post(f"/api/v1/preferences/{token}/unsubscribe")
    assert resp.status_code == 200, resp.text
    assert resp.json()["unsubscribed"] is True

    db_session.refresh(subscriber)
    assert subscriber.status.value == "unsubscribed"

    suppression = (
        db_session.query(Suppression)
        .filter(Suppression.account_id == account.id, Suppression.email == subscriber.email)
        .first()
    )
    assert suppression is not None
    assert suppression.reason.value == "unsubscribe"
    assert suppression.lifted_at is None

    event = (
        db_session.query(SubscriptionEvent)
        .filter(SubscriptionEvent.subscriber_id == subscriber.id)
        .first()
    )
    assert event.event_type == SubscriptionEventType.UNSUBSCRIBED

    # Preference page now reflects the unsubscribed state.
    check = client.get(f"/api/v1/preferences/{token}")
    assert check.json()["unsubscribed"] is True


def test_one_click_unsubscribe_bare_post(client: TestClient, db_session: Session) -> None:
    account = _make_account(db_session)
    subscriber = _make_subscriber(db_session, account)
    db_session.commit()
    token = create_preference_token(subscriber.id)

    resp = client.post(f"/api/v1/preferences/one-click-unsubscribe/{token}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["unsubscribed"] is True

    db_session.refresh(subscriber)
    assert subscriber.status.value == "unsubscribed"

    # Calling it again must stay idempotent: no duplicate active suppression row (the DB's
    # unique partial index on (account_id, email) WHERE lifted_at IS NULL would reject one).
    resp_again = client.post(f"/api/v1/preferences/one-click-unsubscribe/{token}")
    assert resp_again.status_code == 200, resp_again.text

    suppressions = (
        db_session.query(Suppression)
        .filter(Suppression.account_id == account.id, Suppression.email == subscriber.email)
        .all()
    )
    assert len(suppressions) == 1
