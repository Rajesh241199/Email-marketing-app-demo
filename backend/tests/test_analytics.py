"""Tests for the authenticated campaign-stats endpoints (recompute + read).

Wires the analytics router onto the shared app at import time (see the note in
test_preferences.py). Registers via the real /api/v1/auth/register endpoint and inserts
Campaign / EmailMessage / EmailEvent rows directly, since the campaigns domain's own
routers (owned by another agent) aren't what's under test here.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.analytics.models import (
    EmailEvent,
    EmailEventType,
    EmailMessage,
    EmailProvider,
    MessageStatus,
)
from app.analytics.router import router as analytics_router
from app.campaigns.models import Campaign, CampaignRecipient
from app.main import app as main_app

if not getattr(main_app.state, "_analytics_wired", False):
    main_app.include_router(analytics_router)
    main_app.state._analytics_wired = True

REGISTER_BODY = {
    "account": {
        "name": "Acme Co",
        "country_code": "US",
        "address_line1": "1 Main St",
        "city": "Springfield",
    },
    "user": {"email": "owner@acme.example", "password": "correct-horse-battery"},
}


def _auth_headers(client: TestClient) -> tuple[dict[str, str], str]:
    reg = client.post("/api/v1/auth/register", json=REGISTER_BODY).json()
    return {"Authorization": f"Bearer {reg['access_token']}"}, reg["user"]["account_id"]


def _make_campaign(db: Session, account_id: uuid.UUID) -> Campaign:
    campaign = Campaign(account_id=account_id, name="Spring Sale")
    db.add(campaign)
    db.commit()
    return campaign


def _make_message(
    db: Session, campaign: Campaign, *, status: MessageStatus, **extra: object
) -> EmailMessage:
    # one_origin requires a real campaign_recipient_id alongside campaign_id.
    email = f"{uuid.uuid4()}@example.com"
    recipient = CampaignRecipient(campaign_id=campaign.id, email=email)
    db.add(recipient)
    db.flush()

    message = EmailMessage(
        account_id=campaign.account_id,
        campaign_id=campaign.id,
        campaign_recipient_id=recipient.id,
        email=email,
        provider=EmailProvider.SES,
        provider_message_id=str(uuid.uuid4()),
        status=status,
        accepted_at=datetime.now(UTC),
        **extra,
    )
    db.add(message)
    db.flush()
    return message


def test_stats_not_found_before_recompute(client: TestClient, db_session: Session) -> None:
    headers, account_id = _auth_headers(client)
    campaign = _make_campaign(db_session, uuid.UUID(account_id))

    resp = client.get(f"/api/v1/campaigns/{campaign.id}/stats", headers=headers)
    assert resp.status_code == 404


def test_recompute_then_get_stats(client: TestClient, db_session: Session) -> None:
    headers, account_id = _auth_headers(client)
    campaign = _make_campaign(db_session, uuid.UUID(account_id))

    now = datetime.now(UTC)
    delivered = _make_message(
        db_session, campaign, status=MessageStatus.DELIVERED, delivered_at=now,
        first_opened_at=now, first_clicked_at=now,
    )
    _make_message(db_session, campaign, status=MessageStatus.BOUNCED, bounced_at=now)
    _make_message(db_session, campaign, status=MessageStatus.SOFT_BOUNCED)
    _make_message(db_session, campaign, status=MessageStatus.COMPLAINED, complained_at=now)
    # rejected still requires accepted_at (accepted_has_provider_id): the provider
    # accepted the send request, then refused it afterwards.
    _make_message(db_session, campaign, status=MessageStatus.REJECTED)
    db_session.commit()

    event = EmailEvent(
        account_id=campaign.account_id,
        message_id=delivered.id,
        campaign_id=campaign.id,
        provider=EmailProvider.SES,
        provider_event_id="evt-delivery-1",
        event_type=EmailEventType.DELIVERY,
        occurred_at=now,
    )
    db_session.add(event)
    db_session.commit()

    recompute = client.post(f"/api/v1/campaigns/{campaign.id}/stats/recompute", headers=headers)
    assert recompute.status_code == 200, recompute.text
    body = recompute.json()
    assert body["recipients"] == 5
    assert body["sent"] == 5  # accepted_at is set on all 5 messages
    assert body["delivered"] == 1
    assert body["hard_bounces"] == 1
    assert body["soft_bounces"] == 1
    assert body["complaints"] == 1
    assert body["failures"] == 1  # rejected
    assert body["unique_opens"] == 1
    assert body["unique_clicks"] == 1
    assert body["last_event_id"] == event.id

    get_resp = client.get(f"/api/v1/campaigns/{campaign.id}/stats", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["sent"] == 5


def test_recompute_is_idempotent_upsert(client: TestClient, db_session: Session) -> None:
    headers, account_id = _auth_headers(client)
    campaign = _make_campaign(db_session, uuid.UUID(account_id))
    _make_message(
        db_session, campaign, status=MessageStatus.DELIVERED, delivered_at=datetime.now(UTC)
    )
    db_session.commit()

    first = client.post(f"/api/v1/campaigns/{campaign.id}/stats/recompute", headers=headers)
    second = client.post(f"/api/v1/campaigns/{campaign.id}/stats/recompute", headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["delivered"] == 1
    assert second.json()["computed_at"] >= first.json()["computed_at"]


def test_stats_scoped_to_account(client: TestClient, db_session: Session) -> None:
    headers, account_id = _auth_headers(client)
    campaign = _make_campaign(db_session, uuid.UUID(account_id))

    other_body = dict(REGISTER_BODY)
    other_body["user"] = {"email": "other@acme.example", "password": "correct-horse-battery"}
    other_token = client.post("/api/v1/auth/register", json=other_body).json()["access_token"]
    other_headers = {"Authorization": f"Bearer {other_token}"}

    resp = client.get(f"/api/v1/campaigns/{campaign.id}/stats", headers=other_headers)
    assert resp.status_code == 404

    resp = client.post(f"/api/v1/campaigns/{campaign.id}/stats/recompute", headers=other_headers)
    assert resp.status_code == 404
