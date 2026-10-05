"""Tests for the templates domain: templates, content blocks, media assets."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.router import router as auth_router
from app.core.deps import get_db
from app.templates.router import content_blocks_router, media_router
from app.templates.router import router as templates_router

REGISTER_BODY = {
    "account": {
        "name": "Template Co",
        "country_code": "US",
        "address_line1": "1 Main St",
        "city": "Springfield",
    },
    "user": {"email": "tplowner@acme.example", "password": "correct-horse-battery"},
}


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(templates_router)
    app.include_router(content_blocks_router)
    app.include_router(media_router)

    def _get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app)


@pytest.fixture()
def headers(client: TestClient) -> dict:
    reg = client.post("/api/v1/auth/register", json=REGISTER_BODY).json()
    return {"Authorization": f"Bearer {reg['access_token']}"}


def test_template_crud_and_soft_delete(client: TestClient, headers: dict) -> None:
    create = client.post(
        "/api/v1/templates",
        headers=headers,
        json={"name": "Welcome", "subject": "Hi!", "content_json": {"blocks": []}},
    )
    assert create.status_code == 201, create.text
    template = create.json()
    template_id = template["id"]

    listing = client.get("/api/v1/templates", headers=headers)
    assert listing.status_code == 200
    assert len(listing.json()) == 1

    get_resp = client.get(f"/api/v1/templates/{template_id}", headers=headers)
    assert get_resp.status_code == 200

    update = client.patch(
        f"/api/v1/templates/{template_id}", headers=headers, json={"subject": "Hello!"}
    )
    assert update.status_code == 200
    assert update.json()["subject"] == "Hello!"

    delete = client.delete(f"/api/v1/templates/{template_id}", headers=headers)
    assert delete.status_code == 204

    missing = client.get(f"/api/v1/templates/{template_id}", headers=headers)
    assert missing.status_code == 404

    listing_after = client.get("/api/v1/templates", headers=headers)
    assert listing_after.json() == []


def test_template_duplicate(client: TestClient, headers: dict) -> None:
    create = client.post(
        "/api/v1/templates",
        headers=headers,
        json={"name": "Newsletter", "content_json": {"blocks": []}},
    ).json()

    dup = client.post(f"/api/v1/templates/{create['id']}/duplicate", headers=headers)
    assert dup.status_code == 201, dup.text
    copy = dup.json()
    assert copy["name"] == "Newsletter (copy)"
    assert copy["duplicated_from_id"] == create["id"]
    assert copy["id"] != create["id"]


def test_content_block_default_swap(client: TestClient, headers: dict) -> None:
    first = client.post(
        "/api/v1/content-blocks",
        headers=headers,
        json={"kind": "header", "name": "Header A", "content_json": {}, "is_default": True},
    ).json()
    assert first["is_default"] is True

    second = client.post(
        "/api/v1/content-blocks",
        headers=headers,
        json={"kind": "header", "name": "Header B", "content_json": {}, "is_default": True},
    ).json()
    assert second["is_default"] is True

    first_after = client.get(f"/api/v1/content-blocks/{first['id']}", headers=headers).json()
    assert first_after["is_default"] is False

    # A footer default is independent of header defaults.
    footer = client.post(
        "/api/v1/content-blocks",
        headers=headers,
        json={"kind": "footer", "name": "Footer A", "content_json": {}, "is_default": True},
    ).json()
    assert footer["is_default"] is True
    second_after = client.get(f"/api/v1/content-blocks/{second['id']}", headers=headers).json()
    assert second_after["is_default"] is True

    # Updating a non-default block to is_default=True swaps the existing default.
    third = client.post(
        "/api/v1/content-blocks",
        headers=headers,
        json={"kind": "header", "name": "Header C", "content_json": {}, "is_default": False},
    ).json()
    swap = client.patch(
        f"/api/v1/content-blocks/{third['id']}", headers=headers, json={"is_default": True}
    )
    assert swap.status_code == 200
    assert swap.json()["is_default"] is True
    second_after_2 = client.get(f"/api/v1/content-blocks/{second['id']}", headers=headers).json()
    assert second_after_2["is_default"] is False

    delete = client.delete(f"/api/v1/content-blocks/{third['id']}", headers=headers)
    assert delete.status_code == 204
    missing = client.get(f"/api/v1/content-blocks/{third['id']}", headers=headers)
    assert missing.status_code == 404


def test_media_upload_list_get_delete(client: TestClient, headers: dict) -> None:
    upload = client.post(
        "/api/v1/media",
        headers=headers,
        files={"file": ("logo.png", b"\x89PNG-fake-bytes", "image/png")},
        data={"alt_text": "Company logo"},
    )
    assert upload.status_code == 201, upload.text
    asset = upload.json()
    assert asset["filename"] == "logo.png"
    assert asset["content_type"] == "image/png"
    assert asset["size_bytes"] == len(b"\x89PNG-fake-bytes")
    assert asset["alt_text"] == "Company logo"
    assert asset["url"]

    listing = client.get("/api/v1/media", headers=headers)
    assert listing.status_code == 200
    assert len(listing.json()) == 1

    get_resp = client.get(f"/api/v1/media/{asset['id']}", headers=headers)
    assert get_resp.status_code == 200

    delete = client.delete(f"/api/v1/media/{asset['id']}", headers=headers)
    assert delete.status_code == 204

    missing = client.get(f"/api/v1/media/{asset['id']}", headers=headers)
    assert missing.status_code == 404
