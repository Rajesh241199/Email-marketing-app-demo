from fastapi.testclient import TestClient

REGISTER_BODY = {
    "account": {
        "name": "Acme Co",
        "country_code": "US",
        "address_line1": "1 Main St",
        "city": "Springfield",
    },
    "user": {"email": "owner@acme.example", "password": "correct-horse-battery"},
}


def test_register_login_me_flow(client: TestClient) -> None:
    resp = client.post("/api/v1/auth/register", json=REGISTER_BODY)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["user"]["email"] == "owner@acme.example"
    assert body["user"]["role"] == "owner"
    access_token = body["access_token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "owner@acme.example"

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@acme.example", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200
    assert "access_token" in login.json()


def test_register_duplicate_email_rejected(client: TestClient) -> None:
    client.post("/api/v1/auth/register", json=REGISTER_BODY)
    resp = client.post("/api/v1/auth/register", json=REGISTER_BODY)
    assert resp.status_code == 409


def test_login_wrong_password_rejected(client: TestClient) -> None:
    client.post("/api/v1/auth/register", json=REGISTER_BODY)
    resp = client.post(
        "/api/v1/auth/login", json={"email": "owner@acme.example", "password": "nope"}
    )
    assert resp.status_code == 401


def test_refresh_and_logout(client: TestClient) -> None:
    reg = client.post("/api/v1/auth/register", json=REGISTER_BODY).json()
    refresh = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": reg["refresh_token"]}
    )
    assert refresh.status_code == 200

    logout = client.post(
        "/api/v1/auth/logout", json={"refresh_token": reg["refresh_token"]}
    )
    assert logout.status_code == 204

    refresh_again = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": reg["refresh_token"]}
    )
    assert refresh_again.status_code == 401


def test_unauthenticated_me_rejected(client: TestClient) -> None:
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_account_profile_get_and_update(client: TestClient) -> None:
    reg = client.post("/api/v1/auth/register", json=REGISTER_BODY).json()
    headers = {"Authorization": f"Bearer {reg['access_token']}"}

    get_resp = client.get("/api/v1/accounts/me", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Acme Co"

    patch_resp = client.patch(
        "/api/v1/accounts/me", headers=headers, json={"name": "Acme Corp"}
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "Acme Corp"

    status_resp = client.get("/api/v1/accounts/me/onboarding-status", headers=headers)
    assert status_resp.status_code == 200
    assert status_resp.json()["has_verified_sender"] is False
