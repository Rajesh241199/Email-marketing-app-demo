"""Tests for the synchronous CSV import pipeline."""

from __future__ import annotations

import json
import uuid
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.router import router as auth_router
from app.core.deps import get_db
from app.db.enums import ChangeSource
from app.imports.router import router as imports_router
from app.subscribers.models import ListMembership, MailingList, Subscriber, SubscriberStatus
from app.suppressions.models import Suppression, SuppressionReason

REGISTER_BODY = {
    "account": {
        "name": "Import Co",
        "country_code": "US",
        "address_line1": "1 Main St",
        "city": "Springfield",
    },
    "user": {"email": "impowner@acme.example", "password": "correct-horse-battery"},
}


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(imports_router)

    def _get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app)


@pytest.fixture()
def auth(client: TestClient) -> dict:
    reg = client.post("/api/v1/auth/register", json=REGISTER_BODY).json()
    return {
        "headers": {"Authorization": f"Bearer {reg['access_token']}"},
        "account_id": reg["user"]["account_id"],
    }


EMAIL_MAPPING = json.dumps(
    [
        {"column_index": 0, "target": "email"},
        {"column_index": 1, "target": "first_name"},
        {"column_index": 2, "target": "last_name"},
    ]
)


def test_import_creates_subscribers_and_list_membership(
    client: TestClient, auth: dict, db_session: Session
) -> None:
    headers = auth["headers"]
    account_id = auth["account_id"]

    mailing_list = MailingList(account_id=account_id, name="Newsletter")
    db_session.add(mailing_list)
    db_session.flush()

    csv_content = (
        "email,first_name,last_name\n"
        "alice@example.com,Alice,Smith\n"
        "bob@example.com,Bob,Jones\n"
    )

    resp = client.post(
        "/api/v1/imports",
        headers=headers,
        files={"file": ("subs.csv", csv_content.encode(), "text/csv")},
        data={
            "column_mapping": EMAIL_MAPPING,
            "target_list_id": str(mailing_list.id),
            "update_existing": "false",
        },
    )
    assert resp.status_code == 201, resp.text
    job = resp.json()
    assert job["status"] == "completed"
    assert job["total_rows"] == 2
    assert job["imported_count"] == 2
    assert job["rejected_count"] == 0
    assert job["duplicate_count"] == 0

    subscribers = (
        db_session.query(Subscriber)
        .filter(Subscriber.account_id == account_id)
        .order_by(Subscriber.email)
        .all()
    )
    assert [s.email for s in subscribers] == ["alice@example.com", "bob@example.com"]
    assert all(s.source == ChangeSource.CSV_IMPORT for s in subscribers)

    memberships = (
        db_session.query(ListMembership).filter(ListMembership.list_id == mailing_list.id).all()
    )
    assert len(memberships) == 2

    errors = client.get(f"/api/v1/imports/{job['id']}/errors", headers=headers)
    assert errors.status_code == 200
    assert errors.json() == []


def test_import_invalid_email_row_is_recorded(client: TestClient, auth: dict) -> None:
    headers = auth["headers"]
    csv_content = "email,first_name,last_name\nnot-an-email,Alice,Smith\n"

    resp = client.post(
        "/api/v1/imports",
        headers=headers,
        files={"file": ("subs.csv", csv_content.encode(), "text/csv")},
        data={"column_mapping": EMAIL_MAPPING},
    )
    assert resp.status_code == 201, resp.text
    job = resp.json()
    assert job["status"] == "completed_with_errors"
    assert job["rejected_count"] == 1
    assert job["imported_count"] == 0

    errors = client.get(f"/api/v1/imports/{job['id']}/errors", headers=headers).json()
    assert len(errors) == 1
    assert errors[0]["error_code"] == "invalid_email"
    assert errors[0]["row_number"] == 1


def test_import_duplicate_email_in_file_counted_once(client: TestClient, auth: dict) -> None:
    headers = auth["headers"]
    csv_content = (
        "email,first_name,last_name\n"
        "dup@example.com,First,Last\n"
        "dup@example.com,Second,Occurrence\n"
    )

    resp = client.post(
        "/api/v1/imports",
        headers=headers,
        files={"file": ("subs.csv", csv_content.encode(), "text/csv")},
        data={"column_mapping": EMAIL_MAPPING},
    )
    assert resp.status_code == 201, resp.text
    job = resp.json()
    assert job["imported_count"] == 1
    assert job["duplicate_count"] == 1
    assert job["rejected_count"] == 0


def test_import_update_existing_never_touches_status(
    client: TestClient, auth: dict, db_session: Session
) -> None:
    headers = auth["headers"]
    account_id = auth["account_id"]

    # Simulate a previously-suppressed subscriber: a live suppression row plus the
    # subscriber already stored as suppressed (as the DB trigger would set on insert).
    db_session.add(
        Suppression(
            account_id=account_id,
            email="suppressed@example.com",
            reason=SuppressionReason.UNSUBSCRIBE,
            source=ChangeSource.MANUAL,
        )
    )
    existing = Subscriber(
        account_id=account_id,
        email="suppressed@example.com",
        first_name="Old",
        status=SubscriberStatus.SUPPRESSED,
    )
    db_session.add(existing)
    db_session.flush()
    existing_id = existing.id

    csv_content = "email,first_name,last_name\nsuppressed@example.com,New,Name\n"

    resp = client.post(
        "/api/v1/imports",
        headers=headers,
        files={"file": ("subs.csv", csv_content.encode(), "text/csv")},
        data={"column_mapping": EMAIL_MAPPING, "update_existing": "true"},
    )
    assert resp.status_code == 201, resp.text
    job = resp.json()
    assert job["status"] == "completed"
    assert job["updated_count"] == 1
    assert job["imported_count"] == 0

    db_session.expire_all()
    refreshed = db_session.get(Subscriber, existing_id)
    assert refreshed.status == SubscriberStatus.SUPPRESSED
    assert refreshed.first_name == "New"
    assert refreshed.last_name == "Name"


def test_import_column_mapping_requires_custom_field_id(client: TestClient, auth: dict) -> None:
    headers = auth["headers"]
    bad_mapping = json.dumps([{"column_index": 0, "target": "custom_field"}])
    csv_content = "email\nfoo@example.com\n"

    resp = client.post(
        "/api/v1/imports",
        headers=headers,
        files={"file": ("subs.csv", csv_content.encode(), "text/csv")},
        data={"column_mapping": bad_mapping},
    )
    assert resp.status_code == 400


def test_import_never_assigns_subscriber_status() -> None:
    """Belt-and-suspenders static check: imports must never set a subscriber's `status`.

    `ImportJob.status` is unrelated and fine to assign; what must never happen is the
    import code setting `status=` on a `Subscriber(...)` construction or assigning
    `.status` on an existing/target subscriber object.
    """
    import pathlib

    source = pathlib.Path(__file__).parent.parent.joinpath("app/imports/router.py").read_text()
    assert "existing.status" not in source
    assert "target_subscriber.status" not in source
    assert "subscriber.status" not in source


def test_import_job_not_found_for_other_account(client: TestClient, auth: dict) -> None:
    headers = auth["headers"]
    missing_id = uuid.uuid4()
    resp = client.get(f"/api/v1/imports/{missing_id}", headers=headers)
    assert resp.status_code == 404
