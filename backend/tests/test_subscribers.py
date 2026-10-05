"""Tests for the subscribers domain (subscribers, lists, tags, custom fields).

The subscribers router isn't wired into app/main.py yet (left to a later integration
step), so this module builds its own small FastAPI app -- auth router (for register/login)
+ subscribers router -- and defines its own `client` fixture on top of the shared
`db_session` fixture from conftest.py, following the same pattern tests/test_auth.py uses
against the real app. Automations don't have a CRUD router yet either, so the
automation-enrollment test inserts Automation / AutomationEnrollment rows directly via the
ORM, through db_session, exactly as the task describes.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.router import router as auth_router
from app.automations.models import (
    Automation,
    AutomationEnrollment,
    AutomationStatus,
    AutomationTrigger,
    EnrollmentStatus,
)
from app.core.deps import get_db
from app.senders.models import Sender
from app.subscribers.router import router as subscribers_router


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(subscribers_router)

    def _get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app)


def _register(client: TestClient, email: str) -> dict:
    body = {
        "account": {
            "name": "Acme Co",
            "country_code": "US",
            "address_line1": "1 Main St",
            "city": "Springfield",
        },
        "user": {"email": email, "password": "correct-horse-battery"},
    }
    resp = client.post("/api/v1/auth/register", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _auth_headers(reg: dict) -> dict:
    return {"Authorization": f"Bearer {reg['access_token']}"}


# --- Subscribers CRUD --------------------------------------------------------


def test_subscriber_crud_happy_path(client: TestClient) -> None:
    reg = _register(client, "sub-owner1@acme.example")
    headers = _auth_headers(reg)

    create = client.post(
        "/api/v1/subscribers",
        headers=headers,
        json={"email": "jane@acme.example", "first_name": "Jane"},
    )
    assert create.status_code == 201, create.text
    subscriber = create.json()
    assert subscriber["status"] == "subscribed"
    subscriber_id = subscriber["id"]

    got = client.get(f"/api/v1/subscribers/{subscriber_id}", headers=headers)
    assert got.status_code == 200
    assert got.json()["email"] == "jane@acme.example"

    updated = client.patch(
        f"/api/v1/subscribers/{subscriber_id}",
        headers=headers,
        json={"last_name": "Doe", "email_frequency": "essential_only"},
    )
    assert updated.status_code == 200
    assert updated.json()["last_name"] == "Doe"
    assert updated.json()["email_frequency"] == "essential_only"

    # status is never exposed/updatable via this router.
    attempt_status_change = client.patch(
        f"/api/v1/subscribers/{subscriber_id}", headers=headers, json={"status": "unsubscribed"}
    )
    assert attempt_status_change.status_code == 200
    assert attempt_status_change.json()["status"] == "subscribed"

    deleted = client.delete(f"/api/v1/subscribers/{subscriber_id}", headers=headers)
    assert deleted.status_code == 204

    missing = client.get(f"/api/v1/subscribers/{subscriber_id}", headers=headers)
    assert missing.status_code == 404


def test_subscriber_duplicate_email_conflict(client: TestClient) -> None:
    reg = _register(client, "sub-owner2@acme.example")
    headers = _auth_headers(reg)

    body = {"email": "dup@acme.example"}
    first = client.post("/api/v1/subscribers", headers=headers, json=body)
    assert first.status_code == 201

    second = client.post("/api/v1/subscribers", headers=headers, json=body)
    assert second.status_code == 409


def test_subscriber_account_isolation(client: TestClient) -> None:
    reg_a = _register(client, "sub-ownerA@acme.example")
    reg_b = _register(client, "sub-ownerB@other.example")

    create = client.post(
        "/api/v1/subscribers", headers=_auth_headers(reg_a), json={"email": "person@acme.example"}
    )
    subscriber_id = create.json()["id"]

    get_b = client.get(f"/api/v1/subscribers/{subscriber_id}", headers=_auth_headers(reg_b))
    assert get_b.status_code == 404

    patch_b = client.patch(
        f"/api/v1/subscribers/{subscriber_id}",
        headers=_auth_headers(reg_b),
        json={"first_name": "Hijacked"},
    )
    assert patch_b.status_code == 404

    list_b = client.get("/api/v1/subscribers", headers=_auth_headers(reg_b))
    assert list_b.json() == []


def test_subscriber_list_pagination_and_status_filter(client: TestClient) -> None:
    reg = _register(client, "sub-owner3@acme.example")
    headers = _auth_headers(reg)

    for i in range(3):
        resp = client.post(
            "/api/v1/subscribers", headers=headers, json={"email": f"p{i}@acme.example"}
        )
        assert resp.status_code == 201

    page = client.get("/api/v1/subscribers?limit=2&offset=0", headers=headers)
    assert page.status_code == 200
    assert len(page.json()) == 2

    rest = client.get("/api/v1/subscribers?limit=2&offset=2", headers=headers)
    assert len(rest.json()) == 1

    filtered = client.get("/api/v1/subscribers?status=subscribed", headers=headers)
    assert len(filtered.json()) == 3

    filtered_none = client.get("/api/v1/subscribers?status=suppressed", headers=headers)
    assert filtered_none.json() == []


# --- Lists & membership -------------------------------------------------------


def test_list_crud(client: TestClient) -> None:
    reg = _register(client, "list-owner1@acme.example")
    headers = _auth_headers(reg)

    create = client.post(
        "/api/v1/subscribers/lists", headers=headers, json={"name": "Newsletter"}
    )
    assert create.status_code == 201, create.text
    list_id = create.json()["id"]

    listed = client.get("/api/v1/subscribers/lists", headers=headers)
    assert len(listed.json()) == 1

    updated = client.patch(
        f"/api/v1/subscribers/lists/{list_id}",
        headers=headers,
        json={"description": "Weekly updates"},
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "Weekly updates"

    deleted = client.delete(f"/api/v1/subscribers/lists/{list_id}", headers=headers)
    assert deleted.status_code == 204

    missing = client.get(f"/api/v1/subscribers/lists/{list_id}", headers=headers)
    assert missing.status_code == 404


def test_list_membership_add_remove_and_reopt_in_conflict(client: TestClient) -> None:
    reg = _register(client, "list-owner2@acme.example")
    headers = _auth_headers(reg)

    mailing_list = client.post(
        "/api/v1/subscribers/lists", headers=headers, json={"name": "Promo"}
    )
    list_id = mailing_list.json()["id"]

    subscriber = client.post(
        "/api/v1/subscribers", headers=headers, json={"email": "promo-sub@acme.example"}
    )
    subscriber_id = subscriber.json()["id"]

    add = client.post(f"/api/v1/subscribers/{subscriber_id}/lists/{list_id}", headers=headers)
    assert add.status_code == 201, add.text
    assert add.json()["status"] == "active"

    # Adding again while already active is a harmless no-op.
    add_again = client.post(f"/api/v1/subscribers/{subscriber_id}/lists/{list_id}", headers=headers)
    assert add_again.status_code == 201
    assert add_again.json()["status"] == "active"

    remove = client.delete(f"/api/v1/subscribers/{subscriber_id}/lists/{list_id}", headers=headers)
    assert remove.status_code == 204

    # The opted_out -> active transition is blocked at the DB trigger level; the API must
    # translate that into a clean 409 rather than a raw DB error.
    re_add = client.post(f"/api/v1/subscribers/{subscriber_id}/lists/{list_id}", headers=headers)
    assert re_add.status_code == 409


# --- Tags ----------------------------------------------------------------------


def test_tag_crud_and_apply_remove(client: TestClient) -> None:
    reg = _register(client, "tag-owner1@acme.example")
    headers = _auth_headers(reg)

    tag = client.post("/api/v1/subscribers/tags", headers=headers, json={"name": "VIP"})
    assert tag.status_code == 201
    tag_id = tag.json()["id"]

    listed = client.get("/api/v1/subscribers/tags", headers=headers)
    assert len(listed.json()) == 1

    subscriber = client.post(
        "/api/v1/subscribers", headers=headers, json={"email": "vip@acme.example"}
    )
    subscriber_id = subscriber.json()["id"]

    apply_resp = client.post(f"/api/v1/subscribers/{subscriber_id}/tags/{tag_id}", headers=headers)
    assert apply_resp.status_code == 201

    remove_resp = client.delete(
        f"/api/v1/subscribers/{subscriber_id}/tags/{tag_id}", headers=headers
    )
    assert remove_resp.status_code == 204

    deleted = client.delete(f"/api/v1/subscribers/tags/{tag_id}", headers=headers)
    assert deleted.status_code == 204


# --- Custom fields -------------------------------------------------------------


def test_custom_field_crud_and_value_typing(client: TestClient) -> None:
    reg = _register(client, "field-owner1@acme.example")
    headers = _auth_headers(reg)

    subscriber = client.post(
        "/api/v1/subscribers", headers=headers, json={"email": "field-sub@acme.example"}
    )
    subscriber_id = subscriber.json()["id"]

    text_field = client.post(
        "/api/v1/subscribers/fields",
        headers=headers,
        json={"field_key": "company", "label": "Company", "data_type": "text"},
    )
    assert text_field.status_code == 201
    text_field_id = text_field.json()["id"]

    set_text = client.put(
        f"/api/v1/subscribers/{subscriber_id}/fields/{text_field_id}",
        headers=headers,
        json={"value": "Acme Inc"},
    )
    assert set_text.status_code == 200, set_text.text
    assert set_text.json()["value_text"] == "Acme Inc"
    assert set_text.json()["value_number"] is None

    mismatched = client.put(
        f"/api/v1/subscribers/{subscriber_id}/fields/{text_field_id}",
        headers=headers,
        json={"value": 123},
    )
    assert mismatched.status_code == 422

    number_field = client.post(
        "/api/v1/subscribers/fields",
        headers=headers,
        json={"field_key": "age", "label": "Age", "data_type": "number"},
    )
    number_field_id = number_field.json()["id"]
    set_number = client.put(
        f"/api/v1/subscribers/{subscriber_id}/fields/{number_field_id}",
        headers=headers,
        json={"value": 42},
    )
    assert set_number.status_code == 200
    assert float(set_number.json()["value_number"]) == 42

    bool_field = client.post(
        "/api/v1/subscribers/fields",
        headers=headers,
        json={"field_key": "newsletter_opt", "label": "Opted", "data_type": "boolean"},
    )
    bool_field_id = bool_field.json()["id"]
    set_bool = client.put(
        f"/api/v1/subscribers/{subscriber_id}/fields/{bool_field_id}",
        headers=headers,
        json={"value": True},
    )
    assert set_bool.status_code == 200
    assert set_bool.json()["value_bool"] is True

    date_field = client.post(
        "/api/v1/subscribers/fields",
        headers=headers,
        json={"field_key": "signup_date", "label": "Signup date", "data_type": "date"},
    )
    date_field_id = date_field.json()["id"]
    set_date = client.put(
        f"/api/v1/subscribers/{subscriber_id}/fields/{date_field_id}",
        headers=headers,
        json={"value": "2024-01-15"},
    )
    assert set_date.status_code == 200
    assert set_date.json()["value_date"] == "2024-01-15"

    # Upsert: setting the text field again overwrites the previous value, same row.
    overwrite = client.put(
        f"/api/v1/subscribers/{subscriber_id}/fields/{text_field_id}",
        headers=headers,
        json={"value": "New Co"},
    )
    assert overwrite.status_code == 200
    assert overwrite.json()["value_text"] == "New Co"

    deleted = client.delete(f"/api/v1/subscribers/fields/{text_field_id}", headers=headers)
    assert deleted.status_code == 204


# --- Automation enrollment hook ------------------------------------------------


def test_automation_enrollment_on_list_join(client: TestClient, db_session: Session) -> None:
    reg = _register(client, "auto-owner1@acme.example")
    headers = _auth_headers(reg)
    account_id = uuid.UUID(reg["user"]["account_id"])

    mailing_list = client.post(
        "/api/v1/subscribers/lists", headers=headers, json={"name": "Welcome list"}
    )
    list_id = uuid.UUID(mailing_list.json()["id"])

    subscriber = client.post(
        "/api/v1/subscribers", headers=headers, json={"email": "new-joiner@acme.example"}
    )
    subscriber_id = uuid.UUID(subscriber.json()["id"])

    # The automations CRUD router doesn't exist yet, so set up the active, matching
    # automation directly via the ORM, as instructed.
    sender = Sender(account_id=account_id, from_name="Acme", from_email="hello@acme.example")
    db_session.add(sender)
    db_session.flush()

    automation = Automation(
        account_id=account_id,
        name="Welcome series",
        status=AutomationStatus.ACTIVE,
        trigger_type=AutomationTrigger.LIST_JOINED,
        trigger_list_id=list_id,
        sender_id=sender.id,
    )
    db_session.add(automation)
    db_session.commit()

    add = client.post(
        f"/api/v1/subscribers/{subscriber_id}/lists/{list_id}", headers=headers
    )
    assert add.status_code == 201, add.text

    enrollment = (
        db_session.query(AutomationEnrollment)
        .filter(
            AutomationEnrollment.automation_id == automation.id,
            AutomationEnrollment.subscriber_id == subscriber_id,
        )
        .first()
    )
    assert enrollment is not None
    assert enrollment.status == EnrollmentStatus.ACTIVE
    assert enrollment.next_run_at is not None
    assert enrollment.current_step_id is None


def test_automation_enrollment_on_tag_applied(client: TestClient, db_session: Session) -> None:
    reg = _register(client, "auto-owner2@acme.example")
    headers = _auth_headers(reg)
    account_id = uuid.UUID(reg["user"]["account_id"])

    tag = client.post("/api/v1/subscribers/tags", headers=headers, json={"name": "Hot lead"})
    tag_id = uuid.UUID(tag.json()["id"])

    subscriber = client.post(
        "/api/v1/subscribers", headers=headers, json={"email": "hot-lead@acme.example"}
    )
    subscriber_id = uuid.UUID(subscriber.json()["id"])

    sender = Sender(account_id=account_id, from_name="Acme", from_email="sales@acme.example")
    db_session.add(sender)
    db_session.flush()

    automation = Automation(
        account_id=account_id,
        name="Hot lead follow-up",
        status=AutomationStatus.ACTIVE,
        trigger_type=AutomationTrigger.TAG_APPLIED,
        trigger_tag_id=tag_id,
        sender_id=sender.id,
    )
    db_session.add(automation)
    db_session.commit()

    apply_resp = client.post(
        f"/api/v1/subscribers/{subscriber_id}/tags/{tag_id}", headers=headers
    )
    assert apply_resp.status_code == 201

    enrollment = (
        db_session.query(AutomationEnrollment)
        .filter(
            AutomationEnrollment.automation_id == automation.id,
            AutomationEnrollment.subscriber_id == subscriber_id,
        )
        .first()
    )
    assert enrollment is not None
    assert enrollment.status == EnrollmentStatus.ACTIVE
