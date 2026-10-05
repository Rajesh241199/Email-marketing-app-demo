import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.enums import CampaignTier, EmailFrequency
from app.senders.models import Sender, SenderStatus
from app.subscribers.models import (
    ListMembership,
    MailingList,
    MembershipStatus,
    Subscriber,
    SubscriberStatus,
)
from app.suppressions.models import ChangeSource, Suppression, SuppressionReason

REGISTER_BODY = {
    "account": {
        "name": "Acme Co",
        "country_code": "US",
        "address_line1": "1 Main St",
        "city": "Springfield",
    },
    "user": {"email": "owner@acme.example", "password": "correct-horse-battery"},
}


def _register(client: TestClient) -> tuple[dict, uuid.UUID]:
    resp = client.post("/api/v1/auth/register", json=REGISTER_BODY)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    account_id = uuid.UUID(body["user"]["account_id"])
    return headers, account_id


def _verified_sender(db: Session, account_id: uuid.UUID) -> Sender:
    sender = Sender(
        account_id=account_id,
        from_name="Acme",
        from_email="hello@acme.example",
        status=SenderStatus.VERIFIED,
        verified_at=datetime.now(UTC),
    )
    db.add(sender)
    db.commit()
    db.refresh(sender)
    return sender


def _subscriber(
    db: Session,
    account_id: uuid.UUID,
    email: str,
    status: SubscriberStatus = SubscriberStatus.SUBSCRIBED,
    email_frequency: EmailFrequency = EmailFrequency.ALL,
) -> Subscriber:
    sub = Subscriber(
        account_id=account_id, email=email, status=status, email_frequency=email_frequency
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


def _list(db: Session, account_id: uuid.UUID, name: str = "Newsletter") -> MailingList:
    lst = MailingList(account_id=account_id, name=name)
    db.add(lst)
    db.commit()
    db.refresh(lst)
    return lst


def test_create_confirm_freeze_send_happy_path(client: TestClient, db_session: Session) -> None:
    headers, account_id = _register(client)
    sender = _verified_sender(db_session, account_id)
    mailing_list = _list(db_session, account_id)
    sub = _subscriber(db_session, account_id, "a@example.com")
    db_session.add(
        ListMembership(
            list_id=mailing_list.id, subscriber_id=sub.id, status=MembershipStatus.ACTIVE
        )
    )
    db_session.commit()

    create = client.post(
        "/api/v1/campaigns",
        headers=headers,
        json={
            "name": "October newsletter",
            "sender_id": str(sender.id),
            "subject": "Hello!",
            "html": "<p>hi</p>",
        },
    )
    assert create.status_code == 201, create.text
    campaign_id = create.json()["id"]
    assert create.json()["status"] == "draft"

    audience = client.post(
        f"/api/v1/campaigns/{campaign_id}/audiences",
        headers=headers,
        json={"mode": "include", "list_id": str(mailing_list.id)},
    )
    assert audience.status_code == 201, audience.text

    confirm = client.post(f"/api/v1/campaigns/{campaign_id}/confirm", headers=headers)
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["confirmed_at"] is not None

    freeze = client.post(f"/api/v1/campaigns/{campaign_id}/freeze", headers=headers)
    assert freeze.status_code == 200, freeze.text
    assert freeze.json() == {
        "eligible_count": 1,
        "skipped_count": 0,
        "audience_frozen_at": freeze.json()["audience_frozen_at"],
    }

    recipients = client.get(f"/api/v1/campaigns/{campaign_id}/recipients", headers=headers)
    assert recipients.status_code == 200
    assert len(recipients.json()) == 1
    assert recipients.json()[0]["email"] == "a@example.com"
    assert recipients.json()[0]["status"] == "pending"

    send = client.post(f"/api/v1/campaigns/{campaign_id}/send", headers=headers)
    assert send.status_code == 200, send.text
    assert send.json()["status"] == "sending"

    recipients_after = client.get(f"/api/v1/campaigns/{campaign_id}/recipients", headers=headers)
    assert recipients_after.json()[0]["status"] == "queued"


def test_confirm_without_sender_fails(client: TestClient, db_session: Session) -> None:
    headers, account_id = _register(client)
    create = client.post(
        "/api/v1/campaigns", headers=headers, json={"name": "No sender", "html": "<p>hi</p>"}
    )
    campaign_id = create.json()["id"]
    audience_list = _list(db_session, account_id)
    client.post(
        f"/api/v1/campaigns/{campaign_id}/audiences",
        headers=headers,
        json={"mode": "include", "list_id": str(audience_list.id)},
    )

    confirm = client.post(f"/api/v1/campaigns/{campaign_id}/confirm", headers=headers)
    assert confirm.status_code == 400
    assert "sender" in confirm.text


def test_freeze_excludes_suppressed_and_unsubscribed(
    client: TestClient, db_session: Session
) -> None:
    headers, account_id = _register(client)
    sender = _verified_sender(db_session, account_id)
    mailing_list = _list(db_session, account_id)

    eligible = _subscriber(db_session, account_id, "eligible@example.com")
    unsub = _subscriber(
        db_session, account_id, "unsub@example.com", status=SubscriberStatus.UNSUBSCRIBED
    )
    suppressed_sub = _subscriber(db_session, account_id, "suppressed@example.com")
    db_session.add(
        Suppression(
            account_id=account_id,
            email="suppressed@example.com",
            reason=SuppressionReason.MANUAL,
            source=ChangeSource.MANUAL,
        )
    )
    for s in (eligible, unsub, suppressed_sub):
        db_session.add(
            ListMembership(
                list_id=mailing_list.id, subscriber_id=s.id, status=MembershipStatus.ACTIVE
            )
        )
    db_session.commit()

    create = client.post(
        "/api/v1/campaigns",
        headers=headers,
        json={
            "name": "Filtered send",
            "sender_id": str(sender.id),
            "subject": "Hi",
            "html": "<p>hi</p>",
        },
    )
    campaign_id = create.json()["id"]
    client.post(
        f"/api/v1/campaigns/{campaign_id}/audiences",
        headers=headers,
        json={"mode": "include", "list_id": str(mailing_list.id)},
    )
    client.post(f"/api/v1/campaigns/{campaign_id}/confirm", headers=headers)
    freeze = client.post(f"/api/v1/campaigns/{campaign_id}/freeze", headers=headers)
    assert freeze.json()["eligible_count"] == 1
    assert freeze.json()["skipped_count"] == 2

    recipients = client.get(f"/api/v1/campaigns/{campaign_id}/recipients", headers=headers).json()
    by_email = {r["email"]: r for r in recipients}
    assert by_email["eligible@example.com"]["status"] == "pending"
    assert by_email["unsub@example.com"]["skip_reason"] == "unsubscribed"
    assert by_email["suppressed@example.com"]["skip_reason"] == "suppressed"


def test_freeze_respects_topic_opt_out_for_tag_audience(
    client: TestClient, db_session: Session
) -> None:
    """The schema-v1.md section 10 decision: campaigns.topic_list_id makes topic opt-outs
    apply even to a tag-targeted audience, not just list campaigns."""
    from app.subscribers.models import SubscriberTag, Tag

    headers, account_id = _register(client)
    sender = _verified_sender(db_session, account_id)
    topic_list = _list(db_session, account_id, name="Product updates")
    tag = Tag(account_id=account_id, name="vip")
    db_session.add(tag)
    db_session.commit()

    opted_in = _subscriber(db_session, account_id, "in@example.com")
    opted_out = _subscriber(db_session, account_id, "out@example.com")
    for s in (opted_in, opted_out):
        db_session.add(SubscriberTag(subscriber_id=s.id, tag_id=tag.id))
    db_session.add(
        ListMembership(
            list_id=topic_list.id, subscriber_id=opted_in.id, status=MembershipStatus.ACTIVE
        )
    )
    db_session.add(
        ListMembership(
            list_id=topic_list.id, subscriber_id=opted_out.id, status=MembershipStatus.OPTED_OUT
        )
    )
    db_session.commit()

    create = client.post(
        "/api/v1/campaigns",
        headers=headers,
        json={
            "name": "Tag campaign with topic",
            "sender_id": str(sender.id),
            "subject": "Hi",
            "html": "<p>hi</p>",
            "topic_list_id": str(topic_list.id),
        },
    )
    campaign_id = create.json()["id"]
    client.post(
        f"/api/v1/campaigns/{campaign_id}/audiences",
        headers=headers,
        json={"mode": "include", "tag_id": str(tag.id)},
    )
    client.post(f"/api/v1/campaigns/{campaign_id}/confirm", headers=headers)
    freeze = client.post(f"/api/v1/campaigns/{campaign_id}/freeze", headers=headers)
    assert freeze.json()["eligible_count"] == 1
    assert freeze.json()["skipped_count"] == 1

    recipients = client.get(f"/api/v1/campaigns/{campaign_id}/recipients", headers=headers).json()
    by_email = {r["email"]: r for r in recipients}
    assert by_email["in@example.com"]["status"] == "pending"
    assert by_email["out@example.com"]["skip_reason"] == "list_opted_out"


def test_freeze_respects_frequency_tier(client: TestClient, db_session: Session) -> None:
    headers, account_id = _register(client)
    sender = _verified_sender(db_session, account_id)
    mailing_list = _list(db_session, account_id)
    essential_only = _subscriber(
        db_session,
        account_id,
        "essential@example.com",
        email_frequency=EmailFrequency.ESSENTIAL_ONLY,
    )
    db_session.add(
        ListMembership(
            list_id=mailing_list.id, subscriber_id=essential_only.id, status=MembershipStatus.ACTIVE
        )
    )
    db_session.commit()

    create = client.post(
        "/api/v1/campaigns",
        headers=headers,
        json={
            "name": "Regular tier campaign",
            "sender_id": str(sender.id),
            "subject": "Hi",
            "html": "<p>hi</p>",
            "tier": CampaignTier.REGULAR.value,
        },
    )
    campaign_id = create.json()["id"]
    client.post(
        f"/api/v1/campaigns/{campaign_id}/audiences",
        headers=headers,
        json={"mode": "include", "list_id": str(mailing_list.id)},
    )
    client.post(f"/api/v1/campaigns/{campaign_id}/confirm", headers=headers)
    freeze = client.post(f"/api/v1/campaigns/{campaign_id}/freeze", headers=headers)
    assert freeze.json()["skipped_count"] == 1
    recipients = client.get(f"/api/v1/campaigns/{campaign_id}/recipients", headers=headers).json()
    assert recipients[0]["skip_reason"] == "frequency_preference"


def test_exclude_rule_removes_matched_subscriber(client: TestClient, db_session: Session) -> None:
    headers, account_id = _register(client)
    sender = _verified_sender(db_session, account_id)
    mailing_list = _list(db_session, account_id)
    keep = _subscriber(db_session, account_id, "keep@example.com")
    drop = _subscriber(db_session, account_id, "drop@example.com")
    for s in (keep, drop):
        db_session.add(
            ListMembership(
                list_id=mailing_list.id, subscriber_id=s.id, status=MembershipStatus.ACTIVE
            )
        )
    db_session.commit()

    create = client.post(
        "/api/v1/campaigns",
        headers=headers,
        json={
            "name": "Exclude test",
            "sender_id": str(sender.id),
            "subject": "Hi",
            "html": "<p>hi</p>",
        },
    )
    campaign_id = create.json()["id"]
    client.post(
        f"/api/v1/campaigns/{campaign_id}/audiences",
        headers=headers,
        json={"mode": "include", "list_id": str(mailing_list.id)},
    )
    client.post(
        f"/api/v1/campaigns/{campaign_id}/audiences",
        headers=headers,
        json={"mode": "exclude", "subscriber_id": str(drop.id)},
    )
    client.post(f"/api/v1/campaigns/{campaign_id}/confirm", headers=headers)
    freeze = client.post(f"/api/v1/campaigns/{campaign_id}/freeze", headers=headers)
    assert freeze.json()["eligible_count"] == 1

    recipients = client.get(f"/api/v1/campaigns/{campaign_id}/recipients", headers=headers).json()
    assert [r["email"] for r in recipients] == ["keep@example.com"]


def test_unschedule_clears_frozen_audience(client: TestClient, db_session: Session) -> None:
    headers, account_id = _register(client)
    sender = _verified_sender(db_session, account_id)
    mailing_list = _list(db_session, account_id)
    sub = _subscriber(db_session, account_id, "a@example.com")
    db_session.add(
        ListMembership(
            list_id=mailing_list.id, subscriber_id=sub.id, status=MembershipStatus.ACTIVE
        )
    )
    db_session.commit()

    create = client.post(
        "/api/v1/campaigns",
        headers=headers,
        json={
            "name": "Scheduled campaign",
            "sender_id": str(sender.id),
            "subject": "Hi",
            "html": "<p>hi</p>",
        },
    )
    campaign_id = create.json()["id"]
    client.post(
        f"/api/v1/campaigns/{campaign_id}/audiences",
        headers=headers,
        json={"mode": "include", "list_id": str(mailing_list.id)},
    )
    client.post(f"/api/v1/campaigns/{campaign_id}/confirm", headers=headers)
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    schedule = client.post(
        f"/api/v1/campaigns/{campaign_id}/schedule", headers=headers, json={"scheduled_at": future}
    )
    assert schedule.status_code == 200, schedule.text
    assert schedule.json()["status"] == "scheduled"

    client.post(f"/api/v1/campaigns/{campaign_id}/freeze", headers=headers)

    unschedule = client.post(f"/api/v1/campaigns/{campaign_id}/unschedule", headers=headers)
    assert unschedule.status_code == 200
    body = unschedule.json()
    assert body["status"] == "draft"
    assert body["confirmed_at"] is None
    assert body["audience_frozen_at"] is None

    recipients = client.get(f"/api/v1/campaigns/{campaign_id}/recipients", headers=headers)
    assert recipients.json() == []


def test_cross_account_campaign_is_not_visible(client: TestClient, db_session: Session) -> None:
    headers_a, _ = _register(client)
    other_register = {
        "account": {
            "name": "Other Co",
            "country_code": "US",
            "address_line1": "2 Main St",
            "city": "Shelbyville",
        },
        "user": {"email": "owner@other.example", "password": "correct-horse-battery"},
    }
    resp = client.post("/api/v1/auth/register", json=other_register)
    headers_b = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    create = client.post(
        "/api/v1/campaigns", headers=headers_a, json={"name": "Private", "html": "<p>hi</p>"}
    )
    campaign_id = create.json()["id"]

    get_as_b = client.get(f"/api/v1/campaigns/{campaign_id}", headers=headers_b)
    assert get_as_b.status_code == 404


def test_test_send_records_attempt(client: TestClient, db_session: Session) -> None:
    headers, account_id = _register(client)
    create = client.post(
        "/api/v1/campaigns", headers=headers, json={"name": "Preview", "html": "<p>hi</p>"}
    )
    campaign_id = create.json()["id"]
    resp = client.post(
        f"/api/v1/campaigns/{campaign_id}/test-send",
        headers=headers,
        json={"to_emails": ["me@example.com"]},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["to_emails"] == ["me@example.com"]
