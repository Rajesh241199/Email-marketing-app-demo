"""Tests for the senders domain (sending domains + sender identities).

The senders router isn't wired into app/main.py yet (that's left to a later integration
step, per the task that built this domain), so this module builds its own small FastAPI
app -- auth router (for register/login) + senders router -- and defines its own `client`
fixture on top of the shared `db_session` fixture from conftest.py, following the exact
same pattern tests/test_auth.py uses against the real app.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.router import router as auth_router
from app.core.deps import get_db
from app.senders.router import router as senders_router


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(senders_router)

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


def test_sending_domain_crud(client: TestClient) -> None:
    reg = _register(client, "owner1@acme.example")
    headers = _auth_headers(reg)

    create = client.post("/api/v1/senders/domains", headers=headers, json={"domain": "acme.com"})
    assert create.status_code == 201, create.text
    domain_id = create.json()["id"]
    assert create.json()["dkim_status"] == "not_started"

    listed = client.get("/api/v1/senders/domains", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    got = client.get(f"/api/v1/senders/domains/{domain_id}", headers=headers)
    assert got.status_code == 200
    assert got.json()["domain"] == "acme.com"

    deleted = client.delete(f"/api/v1/senders/domains/{domain_id}", headers=headers)
    assert deleted.status_code == 204

    missing = client.get(f"/api/v1/senders/domains/{domain_id}", headers=headers)
    assert missing.status_code == 404


def test_sender_crud_happy_path(client: TestClient) -> None:
    reg = _register(client, "owner2@acme.example")
    headers = _auth_headers(reg)

    create = client.post(
        "/api/v1/senders",
        headers=headers,
        json={"from_name": "Acme Alerts", "from_email": "alerts@acme.com"},
    )
    assert create.status_code == 201, create.text
    sender = create.json()
    assert sender["status"] == "unverified"
    assert sender["is_default"] is False
    sender_id = sender["id"]

    listed = client.get("/api/v1/senders", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    got = client.get(f"/api/v1/senders/{sender_id}", headers=headers)
    assert got.status_code == 200
    assert got.json()["from_email"] == "alerts@acme.com"

    updated = client.patch(
        f"/api/v1/senders/{sender_id}",
        headers=headers,
        json={"from_name": "Acme Updates", "reply_to_email": "reply@acme.com"},
    )
    assert updated.status_code == 200
    assert updated.json()["from_name"] == "Acme Updates"
    assert updated.json()["reply_to_email"] == "reply@acme.com"

    verified = client.patch(f"/api/v1/senders/{sender_id}/verify", headers=headers)
    assert verified.status_code == 200
    assert verified.json()["status"] == "verified"
    assert verified.json()["verified_at"] is not None

    deleted = client.delete(f"/api/v1/senders/{sender_id}", headers=headers)
    assert deleted.status_code == 204

    missing = client.get(f"/api/v1/senders/{sender_id}", headers=headers)
    assert missing.status_code == 404


def test_sender_duplicate_from_email_conflict(client: TestClient) -> None:
    reg = _register(client, "owner3@acme.example")
    headers = _auth_headers(reg)

    body = {"from_name": "Acme Alerts", "from_email": "dup@acme.com"}
    first = client.post("/api/v1/senders", headers=headers, json=body)
    assert first.status_code == 201, first.text

    second = client.post("/api/v1/senders", headers=headers, json=body)
    assert second.status_code == 409


def test_sender_is_default_exclusivity(client: TestClient) -> None:
    reg = _register(client, "owner4@acme.example")
    headers = _auth_headers(reg)

    first = client.post(
        "/api/v1/senders",
        headers=headers,
        json={"from_name": "First", "from_email": "first@acme.com", "is_default": True},
    )
    assert first.status_code == 201
    first_id = first.json()["id"]
    assert first.json()["is_default"] is True

    second = client.post(
        "/api/v1/senders",
        headers=headers,
        json={"from_name": "Second", "from_email": "second@acme.com", "is_default": True},
    )
    assert second.status_code == 201
    assert second.json()["is_default"] is True

    first_after = client.get(f"/api/v1/senders/{first_id}", headers=headers)
    assert first_after.json()["is_default"] is False

    # Setting is_default on the first sender again via PATCH should flip it back.
    patched = client.patch(
        f"/api/v1/senders/{first_id}", headers=headers, json={"is_default": True}
    )
    assert patched.status_code == 200
    assert patched.json()["is_default"] is True

    second_after = client.get(f"/api/v1/senders/{second.json()['id']}", headers=headers)
    assert second_after.json()["is_default"] is False


def test_sender_account_isolation(client: TestClient) -> None:
    reg_a = _register(client, "ownerA@acme.example")
    reg_b = _register(client, "ownerB@other.example")

    create = client.post(
        "/api/v1/senders",
        headers=_auth_headers(reg_a),
        json={"from_name": "Acme Alerts", "from_email": "alerts@acme-isolated.com"},
    )
    assert create.status_code == 201
    sender_id = create.json()["id"]

    # Account B must not be able to see or edit account A's sender.
    get_as_b = client.get(f"/api/v1/senders/{sender_id}", headers=_auth_headers(reg_b))
    assert get_as_b.status_code == 404

    patch_as_b = client.patch(
        f"/api/v1/senders/{sender_id}",
        headers=_auth_headers(reg_b),
        json={"from_name": "Hijacked"},
    )
    assert patch_as_b.status_code == 404

    delete_as_b = client.delete(f"/api/v1/senders/{sender_id}", headers=_auth_headers(reg_b))
    assert delete_as_b.status_code == 404

    list_as_b = client.get("/api/v1/senders", headers=_auth_headers(reg_b))
    assert list_as_b.json() == []
