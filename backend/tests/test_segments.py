"""Tests for the segments domain: CRUD + the evaluator's four rule types.

The segments router is not wired into ``app.main`` yet (that happens in a later
integration pass), so this module builds its own minimal FastAPI app - the auth router
(for registration/login) plus the segments router - sharing the same transactional
``db_session`` fixture from ``tests/conftest.py``.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.router import router as auth_router
from app.core.deps import get_db
from app.segments.router import router as segments_router
from app.subscribers.models import (
    CustomField,
    FieldType,
    ListMembership,
    MailingList,
    Subscriber,
    SubscriberFieldValue,
    SubscriberStatus,
    SubscriberTag,
    Tag,
)

REGISTER_BODY = {
    "account": {
        "name": "Segment Co",
        "country_code": "US",
        "address_line1": "1 Main St",
        "city": "Springfield",
    },
    "user": {"email": "segowner@acme.example", "password": "correct-horse-battery"},
}


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(segments_router)

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


def test_segment_crud(client: TestClient, auth: dict) -> None:
    headers = auth["headers"]

    create = client.post(
        "/api/v1/segments",
        headers=headers,
        json={
            "name": "Subscribed",
            "match_type": "all",
            "conditions": [{"field": "status", "op": "eq", "value": "subscribed"}],
        },
    )
    assert create.status_code == 201, create.text
    segment = create.json()
    segment_id = segment["id"]
    assert segment["match_type"] == "all"
    assert segment["conditions"] == [{"field": "status", "op": "eq", "value": "subscribed"}]

    listing = client.get("/api/v1/segments", headers=headers)
    assert listing.status_code == 200
    assert len(listing.json()) == 1

    get_resp = client.get(f"/api/v1/segments/{segment_id}", headers=headers)
    assert get_resp.status_code == 200

    update = client.patch(
        f"/api/v1/segments/{segment_id}", headers=headers, json={"name": "Active subscribers"}
    )
    assert update.status_code == 200
    assert update.json()["name"] == "Active subscribers"

    delete = client.delete(f"/api/v1/segments/{segment_id}", headers=headers)
    assert delete.status_code == 204

    missing = client.get(f"/api/v1/segments/{segment_id}", headers=headers)
    assert missing.status_code == 404


def test_segment_not_found_for_other_account(client: TestClient, auth: dict) -> None:
    headers = auth["headers"]
    create = client.post(
        "/api/v1/segments",
        headers=headers,
        json={"name": "Mine", "match_type": "all", "conditions": []},
    )
    segment_id = create.json()["id"]

    other_reg = client.post(
        "/api/v1/auth/register",
        json={
            "account": {
                "name": "Other Co",
                "country_code": "US",
                "address_line1": "2 Main St",
                "city": "Shelbyville",
            },
            "user": {"email": "other@acme.example", "password": "correct-horse-battery"},
        },
    ).json()
    other_headers = {"Authorization": f"Bearer {other_reg['access_token']}"}

    resp = client.get(f"/api/v1/segments/{segment_id}", headers=other_headers)
    assert resp.status_code == 404


def _make_subscriber(
    db_session: Session, account_id: str, email: str, status: SubscriberStatus | None = None
) -> Subscriber:
    kwargs = {"account_id": account_id, "email": email}
    if status is not None:
        kwargs["status"] = status
    sub = Subscriber(**kwargs)
    db_session.add(sub)
    db_session.flush()
    return sub


def test_segment_preview_rule_types_and_all_vs_any(
    client: TestClient, auth: dict, db_session: Session
) -> None:
    headers = auth["headers"]
    account_id = auth["account_id"]

    # A: subscribed, tagged "vip", in list L1, custom field plan="pro"
    # B: subscribed, no tag, not in L1, custom field plan="basic"
    # C: unsubscribed, no tag, not in L1
    sub_a = _make_subscriber(db_session, account_id, "a@example.com")
    sub_b = _make_subscriber(db_session, account_id, "b@example.com")
    sub_c = _make_subscriber(
        db_session, account_id, "c@example.com", status=SubscriberStatus.UNSUBSCRIBED
    )

    tag = Tag(account_id=account_id, name="vip")
    db_session.add(tag)
    db_session.flush()
    db_session.add(SubscriberTag(subscriber_id=sub_a.id, tag_id=tag.id))

    mailing_list = MailingList(account_id=account_id, name="L1")
    db_session.add(mailing_list)
    db_session.flush()
    db_session.add(ListMembership(list_id=mailing_list.id, subscriber_id=sub_a.id))

    plan_field = CustomField(
        account_id=account_id, field_key="plan", label="Plan", data_type=FieldType.TEXT
    )
    db_session.add(plan_field)
    db_session.flush()
    db_session.add(
        SubscriberFieldValue(
            subscriber_id=sub_a.id, custom_field_id=plan_field.id, value_text="pro"
        )
    )
    db_session.add(
        SubscriberFieldValue(
            subscriber_id=sub_b.id, custom_field_id=plan_field.id, value_text="basic"
        )
    )
    db_session.flush()

    # ALL: subscribed AND tagged vip -> only A
    all_segment = client.post(
        "/api/v1/segments",
        headers=headers,
        json={
            "name": "Subscribed VIP",
            "match_type": "all",
            "conditions": [
                {"field": "status", "op": "eq", "value": "subscribed"},
                {"field": "tag", "op": "has", "value": str(tag.id)},
            ],
        },
    ).json()
    preview = client.get(f"/api/v1/segments/{all_segment['id']}/preview", headers=headers).json()
    assert preview["count"] == 1
    assert preview["sample_subscriber_ids"] == [str(sub_a.id)]

    # ANY: subscribed OR tagged vip -> A and B (C is unsubscribed and untagged)
    any_segment = client.post(
        "/api/v1/segments",
        headers=headers,
        json={
            "name": "Subscribed or VIP",
            "match_type": "any",
            "conditions": [
                {"field": "status", "op": "eq", "value": "subscribed"},
                {"field": "tag", "op": "has", "value": str(tag.id)},
            ],
        },
    ).json()
    preview = client.get(f"/api/v1/segments/{any_segment['id']}/preview", headers=headers).json()
    assert preview["count"] == 2
    assert set(preview["sample_subscriber_ids"]) == {str(sub_a.id), str(sub_b.id)}

    # list rule -> only A is an active member of L1
    list_segment = client.post(
        "/api/v1/segments",
        headers=headers,
        json={
            "name": "In L1",
            "match_type": "all",
            "conditions": [{"field": "list", "op": "has", "value": str(mailing_list.id)}],
        },
    ).json()
    preview = client.get(f"/api/v1/segments/{list_segment['id']}/preview", headers=headers).json()
    assert preview["count"] == 1
    assert preview["sample_subscriber_ids"] == [str(sub_a.id)]

    # custom_field rule -> plan eq "pro" matches only A
    cf_segment = client.post(
        "/api/v1/segments",
        headers=headers,
        json={
            "name": "Pro plan",
            "match_type": "all",
            "conditions": [
                {
                    "field": "custom_field",
                    "op": "eq",
                    "value": "pro",
                    "custom_field_id": str(plan_field.id),
                }
            ],
        },
    ).json()
    preview = client.get(f"/api/v1/segments/{cf_segment['id']}/preview", headers=headers).json()
    assert preview["count"] == 1
    assert preview["sample_subscriber_ids"] == [str(sub_a.id)]

    assert sub_c.id is not None  # sanity: C exists and matched nothing above
