"""Tests for the authenticated automations + steps + (read-only) enrollments CRUD.

Wires the automations router onto the shared app at import time (see the note in
test_preferences.py) and registers via the real /api/v1/auth/register endpoint, matching
the house test style.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.automations.models import AutomationEnrollment, EnrollmentStatus
from app.automations.router import router as automations_router
from app.main import app as main_app
from app.senders.models import Sender
from app.subscribers.models import MailingList, Subscriber, Tag

if not getattr(main_app.state, "_automations_wired", False):
    main_app.include_router(automations_router)
    main_app.state._automations_wired = True

REGISTER_BODY = {
    "account": {
        "name": "Acme Co",
        "country_code": "US",
        "address_line1": "1 Main St",
        "city": "Springfield",
    },
    "user": {"email": "owner@acme.example", "password": "correct-horse-battery"},
}


def _auth_headers(client: TestClient) -> dict[str, str]:
    reg = client.post("/api/v1/auth/register", json=REGISTER_BODY).json()
    return {"Authorization": f"Bearer {reg['access_token']}"}, reg["user"]["account_id"]


def _make_list(db: Session, account_id: uuid.UUID) -> MailingList:
    mailing_list = MailingList(account_id=account_id, name="Onboarding")
    db.add(mailing_list)
    db.commit()
    return mailing_list


def _make_sender(db: Session, account_id: uuid.UUID) -> Sender:
    sender = Sender(account_id=account_id, from_name="Acme", from_email="hello@acme.example")
    db.add(sender)
    db.commit()
    return sender


def _list_joined_body(name: str, mailing_list: MailingList) -> dict[str, str]:
    return {
        "name": name,
        "trigger_type": "list_joined",
        "trigger_list_id": str(mailing_list.id),
    }


def test_create_list_get_automation(client: TestClient, db_session: Session) -> None:
    headers, account_id = _auth_headers(client)
    mailing_list = _make_list(db_session, uuid.UUID(account_id))

    resp = client.post(
        "/api/v1/automations",
        headers=headers,
        json=_list_joined_body("Welcome series", mailing_list),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "draft"
    automation_id = body["id"]

    list_resp = client.get("/api/v1/automations", headers=headers)
    assert list_resp.status_code == 200
    assert any(a["id"] == automation_id for a in list_resp.json())

    get_resp = client.get(f"/api/v1/automations/{automation_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Welcome series"


def test_automation_not_found_for_other_account(client: TestClient, db_session: Session) -> None:
    headers, account_id = _auth_headers(client)
    mailing_list = _make_list(db_session, uuid.UUID(account_id))
    resp = client.post(
        "/api/v1/automations",
        headers=headers,
        json=_list_joined_body("A", mailing_list),
    )
    automation_id = resp.json()["id"]

    # Register a second, distinct account.
    other_body = dict(REGISTER_BODY)
    other_body["user"] = {"email": "other@acme.example", "password": "correct-horse-battery"}
    other_reg = client.post("/api/v1/auth/register", json=other_body).json()
    other_headers = {"Authorization": f"Bearer {other_reg['access_token']}"}

    resp = client.get(f"/api/v1/automations/{automation_id}", headers=other_headers)
    assert resp.status_code == 404


def test_trigger_target_must_match_type(client: TestClient, db_session: Session) -> None:
    headers, account_id = _auth_headers(client)
    mailing_list = _make_list(db_session, uuid.UUID(account_id))

    # list_joined trigger with no trigger_list_id is invalid.
    resp = client.post(
        "/api/v1/automations",
        headers=headers,
        json={"name": "Bad", "trigger_type": "list_joined"},
    )
    assert resp.status_code == 400

    # tag_applied trigger with a trigger_list_id set instead of trigger_tag_id is invalid.
    resp = client.post(
        "/api/v1/automations",
        headers=headers,
        json={
            "name": "Bad2",
            "trigger_type": "tag_applied",
            "trigger_list_id": str(mailing_list.id),
        },
    )
    assert resp.status_code == 400


def test_activate_without_sender_rejected(client: TestClient, db_session: Session) -> None:
    headers, account_id = _auth_headers(client)
    mailing_list = _make_list(db_session, uuid.UUID(account_id))
    resp = client.post(
        "/api/v1/automations",
        headers=headers,
        json=_list_joined_body("Needs sender", mailing_list),
    )
    automation_id = resp.json()["id"]

    activate = client.patch(
        f"/api/v1/automations/{automation_id}", headers=headers, json={"status": "active"}
    )
    assert activate.status_code == 400

    sender = _make_sender(db_session, uuid.UUID(account_id))
    activate_ok = client.patch(
        f"/api/v1/automations/{automation_id}",
        headers=headers,
        json={"status": "active", "sender_id": str(sender.id)},
    )
    assert activate_ok.status_code == 200, activate_ok.text
    assert activate_ok.json()["status"] == "active"
    assert activate_ok.json()["activated_at"] is not None


def test_update_and_delete_automation(client: TestClient, db_session: Session) -> None:
    headers, account_id = _auth_headers(client)
    mailing_list = _make_list(db_session, uuid.UUID(account_id))
    resp = client.post(
        "/api/v1/automations",
        headers=headers,
        json=_list_joined_body("Rename me", mailing_list),
    )
    automation_id = resp.json()["id"]

    patch_resp = client.patch(
        f"/api/v1/automations/{automation_id}", headers=headers, json={"name": "Renamed"}
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "Renamed"

    delete_resp = client.delete(f"/api/v1/automations/{automation_id}", headers=headers)
    assert delete_resp.status_code == 204

    get_resp = client.get(f"/api/v1/automations/{automation_id}", headers=headers)
    assert get_resp.status_code == 404


def test_step_crud_and_field_validation(client: TestClient, db_session: Session) -> None:
    headers, account_id = _auth_headers(client)
    tag = Tag(account_id=uuid.UUID(account_id), name="vip")
    db_session.add(tag)
    db_session.commit()

    resp = client.post(
        "/api/v1/automations",
        headers=headers,
        json={"name": "Tag flow", "trigger_type": "tag_applied", "trigger_tag_id": str(tag.id)},
    )
    automation_id = resp.json()["id"]

    # Wait step missing wait_unit is invalid.
    bad_wait = client.post(
        f"/api/v1/automations/{automation_id}/steps",
        headers=headers,
        json={"step_type": "wait", "wait_amount": 2},
    )
    assert bad_wait.status_code == 400

    # Email step with neither template_id nor content_json is invalid.
    bad_email = client.post(
        f"/api/v1/automations/{automation_id}/steps",
        headers=headers,
        json={"step_type": "email"},
    )
    assert bad_email.status_code == 400

    # Valid wait step, auto-positioned.
    wait_step = client.post(
        f"/api/v1/automations/{automation_id}/steps",
        headers=headers,
        json={"step_type": "wait", "wait_amount": 1, "wait_unit": "days"},
    )
    assert wait_step.status_code == 201, wait_step.text
    assert wait_step.json()["position"] == 0

    # Valid email step, auto-positioned after the wait step.
    email_step = client.post(
        f"/api/v1/automations/{automation_id}/steps",
        headers=headers,
        json={"step_type": "email", "content_json": {"blocks": []}},
    )
    assert email_step.status_code == 201, email_step.text
    assert email_step.json()["position"] == 1

    steps = client.get(f"/api/v1/automations/{automation_id}/steps", headers=headers)
    assert steps.status_code == 200
    assert [s["position"] for s in steps.json()] == [0, 1]

    step_id = wait_step.json()["id"]
    update = client.patch(
        f"/api/v1/automations/{automation_id}/steps/{step_id}",
        headers=headers,
        json={"wait_amount": 3},
    )
    assert update.status_code == 200
    assert update.json()["wait_amount"] == 3

    # Flipping a wait step to look like an email step without clearing wait fields is invalid.
    bad_update = client.patch(
        f"/api/v1/automations/{automation_id}/steps/{step_id}",
        headers=headers,
        json={"step_type": "email"},
    )
    assert bad_update.status_code == 400

    delete_resp = client.delete(
        f"/api/v1/automations/{automation_id}/steps/{step_id}", headers=headers
    )
    assert delete_resp.status_code == 204

    remaining = client.get(f"/api/v1/automations/{automation_id}/steps", headers=headers)
    assert len(remaining.json()) == 1


def test_enrollments_are_read_only_list(client: TestClient, db_session: Session) -> None:
    headers, account_id = _auth_headers(client)
    mailing_list = _make_list(db_session, uuid.UUID(account_id))
    resp = client.post(
        "/api/v1/automations",
        headers=headers,
        json=_list_joined_body("Has enrollments", mailing_list),
    )
    automation_id = resp.json()["id"]

    subscriber = Subscriber(account_id=uuid.UUID(account_id), email="sub@example.com")
    db_session.add(subscriber)
    db_session.flush()
    # active requires next_run_at per the active_has_next_run check constraint.
    enrollment = AutomationEnrollment(
        automation_id=uuid.UUID(automation_id),
        subscriber_id=subscriber.id,
        status=EnrollmentStatus.ACTIVE,
        next_run_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(enrollment)
    db_session.commit()

    list_resp = client.get(f"/api/v1/automations/{automation_id}/enrollments", headers=headers)
    assert list_resp.status_code == 200, list_resp.text
    assert len(list_resp.json()) == 1
    assert list_resp.json()[0]["subscriber_id"] == str(subscriber.id)
