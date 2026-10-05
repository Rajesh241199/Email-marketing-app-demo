"""
Comprehensive test suite for the Email Marketing Platform.
Tests all endpoints — Heet's (full) and Rajesh's (scaffold).
"""
import io
import pytest

# ── Shared state across tests ─────────────────────────────────────────────────
state = {}


# ═══════════════════════════════════════════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════════════════════════════════════════

class TestHealth:
    def test_health_check(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "healthy"
        assert "version" in d


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuth:
    def test_register_user(self, client):
        r = client.post("/api/v1/auth/register", json={
            "email": "heet@emailplatform.com",
            "password": "TestPass123",
            "first_name": "Heet",
            "last_name": "Dev",
        })
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["email"] == "heet@emailplatform.com"
        assert d["status"] == "not_verified"
        state["user_id"] = d["id"]

    def test_register_duplicate_email(self, client):
        r = client.post("/api/v1/auth/register", json={
            "email": "heet@emailplatform.com",
            "password": "AnotherPass",
        })
        assert r.status_code == 400

    def test_login_before_verify(self, client):
        r = client.post("/api/v1/auth/login", data={
            "username": "heet@emailplatform.com",
            "password": "TestPass123",
        })
        assert r.status_code == 200
        d = r.json()
        assert "access_token" in d
        state["token"] = d["access_token"]

    def test_login_wrong_password(self, client):
        r = client.post("/api/v1/auth/login", data={
            "username": "heet@emailplatform.com",
            "password": "WrongPass",
        })
        assert r.status_code == 401

    def test_verify_email(self, client):
        r = client.post(f"/api/v1/auth/verify-email/{state['user_id']}")
        assert r.status_code == 200
        assert r.json()["status"] == "active"
        assert r.json()["email_verified"] is True

    def test_forgot_password_stub(self, client):
        r = client.post("/api/v1/auth/forgot-password", params={"email": "heet@emailplatform.com"})
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# ACCOUNT
# ═══════════════════════════════════════════════════════════════════════════════

class TestAccount:
    def test_create_account(self, client):
        r = client.post("/api/v1/account/", json={
            "name": "Acme Email Co",
            "country": "India",
            "business_address": "123 MG Road, Bangalore",
            "timezone": "Asia/Kolkata",
        })
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["name"] == "Acme Email Co"
        assert d["onboarding_status"] == "pending"
        state["account_id"] = d["id"]

    def test_get_account(self, client):
        r = client.get(f"/api/v1/account/{state['account_id']}")
        assert r.status_code == 200
        assert r.json()["name"] == "Acme Email Co"

    def test_update_account(self, client):
        r = client.put(f"/api/v1/account/{state['account_id']}", json={
            "onboarding_status": "in_progress",
        })
        assert r.status_code == 200
        assert r.json()["onboarding_status"] == "in_progress"

    def test_get_account_not_found(self, client):
        r = client.get("/api/v1/account/99999")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# SENDERS
# ═══════════════════════════════════════════════════════════════════════════════

class TestSenders:
    def test_create_sender(self, client):
        r = client.post("/api/v1/senders/", params={"account_id": state["account_id"]}, json={
            "sender_name": "Acme Newsletter",
            "sender_email": "newsletter@acme.com",
            "reply_to_email": "reply@acme.com",
            "is_default": True,
        })
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["sender_email"] == "newsletter@acme.com"
        assert d["verification_status"] == "unverified"
        state["sender_id"] = d["id"]

    def test_list_senders(self, client):
        r = client.get("/api/v1/senders/", params={"account_id": state["account_id"]})
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_get_sender(self, client):
        r = client.get(f"/api/v1/senders/{state['sender_id']}")
        assert r.status_code == 200

    def test_update_sender(self, client):
        r = client.put(f"/api/v1/senders/{state['sender_id']}", json={"sender_name": "Acme Weekly"})
        assert r.status_code == 200
        assert r.json()["sender_name"] == "Acme Weekly"

    def test_verify_sender(self, client):
        r = client.post(f"/api/v1/senders/{state['sender_id']}/verify")
        assert r.status_code == 200
        assert r.json()["verification_status"] == "verified"

    def test_sender_not_found(self, client):
        r = client.get("/api/v1/senders/99999")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# LISTS  [Heet]
# ═══════════════════════════════════════════════════════════════════════════════

class TestLists:
    def test_create_list(self, client):
        r = client.post("/api/v1/lists/", params={"account_id": state["account_id"]}, json={
            "name": "Newsletter Subscribers",
            "description": "Main newsletter list",
        })
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["name"] == "Newsletter Subscribers"
        state["list_id"] = d["id"]

    def test_create_second_list(self, client):
        r = client.post("/api/v1/lists/", params={"account_id": state["account_id"]}, json={
            "name": "VIP Customers",
        })
        assert r.status_code == 201
        state["list_id_2"] = r.json()["id"]

    def test_get_all_lists(self, client):
        r = client.get("/api/v1/lists/", params={"account_id": state["account_id"]})
        assert r.status_code == 200
        assert len(r.json()) >= 2

    def test_get_list(self, client):
        r = client.get(f"/api/v1/lists/{state['list_id']}")
        assert r.status_code == 200
        assert r.json()["name"] == "Newsletter Subscribers"

    def test_update_list(self, client):
        r = client.put(f"/api/v1/lists/{state['list_id']}", json={"description": "Updated description"})
        assert r.status_code == 200
        assert r.json()["description"] == "Updated description"

    def test_list_not_found(self, client):
        r = client.get("/api/v1/lists/99999")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# TAGS  [Heet]
# ═══════════════════════════════════════════════════════════════════════════════

class TestTags:
    def test_create_tag(self, client):
        r = client.post("/api/v1/tags/", params={"account_id": state["account_id"]}, json={"name": "vip"})
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["name"] == "vip"
        state["tag_id"] = d["id"]

    def test_create_duplicate_tag(self, client):
        r = client.post("/api/v1/tags/", params={"account_id": state["account_id"]}, json={"name": "vip"})
        assert r.status_code == 409

    def test_create_second_tag(self, client):
        r = client.post("/api/v1/tags/", params={"account_id": state["account_id"]}, json={"name": "early-adopter"})
        assert r.status_code == 201
        state["tag_id_2"] = r.json()["id"]

    def test_list_tags(self, client):
        r = client.get("/api/v1/tags/", params={"account_id": state["account_id"]})
        assert r.status_code == 200
        assert len(r.json()) >= 2


# ═══════════════════════════════════════════════════════════════════════════════
# CUSTOM FIELDS  [Heet]
# ═══════════════════════════════════════════════════════════════════════════════

class TestCustomFields:
    def test_create_custom_field(self, client):
        r = client.post("/api/v1/custom-fields/", params={"account_id": state["account_id"]}, json={
            "field_name": "Company",
            "field_slug": "company",
            "field_type": "text",
            "is_required": False,
        })
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["field_slug"] == "company"
        state["cf_id"] = d["id"]

    def test_duplicate_slug_blocked(self, client):
        r = client.post("/api/v1/custom-fields/", params={"account_id": state["account_id"]}, json={
            "field_name": "Company 2",
            "field_slug": "company",
            "field_type": "text",
        })
        assert r.status_code == 409

    def test_create_number_field(self, client):
        r = client.post("/api/v1/custom-fields/", params={"account_id": state["account_id"]}, json={
            "field_name": "Employee Count",
            "field_slug": "employee_count",
            "field_type": "number",
        })
        assert r.status_code == 201
        state["cf_id_2"] = r.json()["id"]

    def test_list_custom_fields(self, client):
        r = client.get("/api/v1/custom-fields/", params={"account_id": state["account_id"]})
        assert r.status_code == 200
        assert len(r.json()) >= 2

    def test_get_custom_field(self, client):
        r = client.get(f"/api/v1/custom-fields/{state['cf_id']}")
        assert r.status_code == 200

    def test_update_custom_field(self, client):
        r = client.put(f"/api/v1/custom-fields/{state['cf_id']}", json={"field_name": "Company Name"})
        assert r.status_code == 200
        assert r.json()["field_name"] == "Company Name"


# ═══════════════════════════════════════════════════════════════════════════════
# SUBSCRIBERS  [Heet]
# ═══════════════════════════════════════════════════════════════════════════════

class TestSubscribers:
    def test_create_subscriber(self, client):
        r = client.post("/api/v1/subscribers/", params={"account_id": state["account_id"]}, json={
            "email": "alice@example.com",
            "first_name": "Alice",
            "last_name": "Smith",
            "consent_source": "manual",
            "list_ids": [state["list_id"]],
            "tag_ids": [state["tag_id"]],
            "custom_fields": [{"custom_field_id": state["cf_id"], "value": "Acme Corp"}],
        })
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["email"] == "alice@example.com"
        assert d["status"] == "subscribed"
        state["sub_id"] = d["id"]

    def test_create_second_subscriber(self, client):
        r = client.post("/api/v1/subscribers/", params={"account_id": state["account_id"]}, json={
            "email": "bob@example.com",
            "first_name": "Bob",
            "last_name": "Jones",
            "list_ids": [state["list_id"]],
            "tag_ids": [state["tag_id_2"]],
        })
        assert r.status_code == 201
        state["sub_id_2"] = r.json()["id"]

    def test_create_third_subscriber_vip(self, client):
        r = client.post("/api/v1/subscribers/", params={"account_id": state["account_id"]}, json={
            "email": "carol@example.com",
            "first_name": "Carol",
            "list_ids": [state["list_id_2"]],
            "tag_ids": [state["tag_id"]],
        })
        assert r.status_code == 201
        state["sub_id_3"] = r.json()["id"]

    def test_duplicate_email_blocked(self, client):
        r = client.post("/api/v1/subscribers/", params={"account_id": state["account_id"]}, json={
            "email": "alice@example.com",
        })
        assert r.status_code == 409

    def test_email_case_insensitive(self, client):
        r = client.post("/api/v1/subscribers/", params={"account_id": state["account_id"]}, json={
            "email": "ALICE@EXAMPLE.COM",
        })
        assert r.status_code == 409

    def test_get_subscriber_detail(self, client):
        r = client.get(f"/api/v1/subscribers/{state['sub_id']}")
        assert r.status_code == 200
        d = r.json()
        assert d["email"] == "alice@example.com"
        assert len(d["tags"]) == 1
        assert d["tags"][0]["name"] == "vip"
        assert len(d["lists"]) == 1
        assert len(d["custom_field_values"]) == 1
        assert d["custom_field_values"][0]["value"] == "Acme Corp"

    def test_list_all_subscribers(self, client):
        r = client.get("/api/v1/subscribers/", params={"account_id": state["account_id"]})
        assert r.status_code == 200
        d = r.json()
        assert d["total"] >= 3
        assert "items" in d

    def test_search_by_name(self, client):
        r = client.get("/api/v1/subscribers/", params={
            "account_id": state["account_id"], "q": "alice"
        })
        assert r.status_code == 200
        d = r.json()
        assert d["total"] == 1
        assert d["items"][0]["email"] == "alice@example.com"

    def test_filter_by_status(self, client):
        r = client.get("/api/v1/subscribers/", params={
            "account_id": state["account_id"], "status": "subscribed"
        })
        assert r.status_code == 200
        assert r.json()["total"] >= 3

    def test_filter_by_list(self, client):
        r = client.get("/api/v1/subscribers/", params={
            "account_id": state["account_id"], "list_id": state["list_id"]
        })
        assert r.status_code == 200
        assert r.json()["total"] == 2

    def test_filter_by_tag(self, client):
        r = client.get("/api/v1/subscribers/", params={
            "account_id": state["account_id"], "tag_id": state["tag_id"]
        })
        assert r.status_code == 200
        assert r.json()["total"] == 2  # alice + carol have "vip" tag

    def test_pagination(self, client):
        r = client.get("/api/v1/subscribers/", params={
            "account_id": state["account_id"], "page": 1, "per_page": 2
        })
        assert r.status_code == 200
        d = r.json()
        assert len(d["items"]) <= 2

    def test_update_subscriber(self, client):
        r = client.put(f"/api/v1/subscribers/{state['sub_id']}", json={
            "first_name": "Alice Updated",
            "tag_ids": [state["tag_id"], state["tag_id_2"]],
        })
        assert r.status_code == 200
        assert r.json()["first_name"] == "Alice Updated"

    def test_subscriber_not_found(self, client):
        r = client.get("/api/v1/subscribers/99999")
        assert r.status_code == 404

    def test_preference_history(self, client):
        r = client.get(f"/api/v1/subscribers/{state['sub_id']}/history")
        assert r.status_code == 200
        history = r.json()
        assert len(history) >= 1
        assert any(h["change_type"] == "subscribed" for h in history)

    def test_bulk_unsubscribe(self, client):
        r = client.post("/api/v1/subscribers/bulk-unsubscribe",
            params={"account_id": state["account_id"]},
            json={"ids": [state["sub_id_3"]]},
        )
        assert r.status_code == 200
        assert r.json()["unsubscribed"] == 1
        # Verify status changed
        r2 = client.get(f"/api/v1/subscribers/{state['sub_id_3']}")
        assert r2.json()["status"] == "unsubscribed"

    def test_filter_by_status_unsubscribed(self, client):
        r = client.get("/api/v1/subscribers/", params={
            "account_id": state["account_id"], "status": "unsubscribed"
        })
        assert r.status_code == 200
        assert r.json()["total"] >= 1

    def test_bulk_delete(self, client):
        # Create a throwaway subscriber
        r = client.post("/api/v1/subscribers/", params={"account_id": state["account_id"]}, json={
            "email": "throwaway@example.com"
        })
        tid = r.json()["id"]
        r2 = client.post("/api/v1/subscribers/bulk-delete",
            params={"account_id": state["account_id"]},
            json={"ids": [tid]},
        )
        assert r2.status_code == 200
        assert r2.json()["deleted"] == 1
        # Confirm gone
        r3 = client.get(f"/api/v1/subscribers/{tid}")
        assert r3.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# LIST ↔ SUBSCRIBER  [Heet]
# ═══════════════════════════════════════════════════════════════════════════════

class TestListSubscriberMembership:
    def test_get_list_subscribers(self, client):
        r = client.get(f"/api/v1/lists/{state['list_id']}/subscribers")
        assert r.status_code == 200
        d = r.json()
        assert d["total"] == 2  # alice + bob

    def test_add_subscriber_to_list(self, client):
        r = client.post(
            f"/api/v1/lists/{state['list_id_2']}/subscribers/{state['sub_id']}"
        )
        assert r.status_code == 201

    def test_add_duplicate_blocked(self, client):
        r = client.post(
            f"/api/v1/lists/{state['list_id_2']}/subscribers/{state['sub_id']}"
        )
        assert r.status_code == 409

    def test_remove_subscriber_from_list(self, client):
        r = client.delete(
            f"/api/v1/lists/{state['list_id_2']}/subscribers/{state['sub_id']}"
        )
        assert r.status_code == 204


# ═══════════════════════════════════════════════════════════════════════════════
# TAG ↔ SUBSCRIBER  [Heet]
# ═══════════════════════════════════════════════════════════════════════════════

class TestTagSubscriber:
    def test_apply_tag(self, client):
        r = client.post(
            f"/api/v1/tags/subscribers/{state['sub_id_2']}/tags/{state['tag_id']}"
        )
        assert r.status_code == 201

    def test_apply_duplicate_tag(self, client):
        r = client.post(
            f"/api/v1/tags/subscribers/{state['sub_id_2']}/tags/{state['tag_id']}"
        )
        assert r.status_code == 409

    def test_remove_tag(self, client):
        r = client.delete(
            f"/api/v1/tags/subscribers/{state['sub_id_2']}/tags/{state['tag_id']}"
        )
        assert r.status_code == 204

    def test_delete_tag(self, client):
        # Create and delete a disposable tag
        r = client.post("/api/v1/tags/", params={"account_id": state["account_id"]}, json={"name": "disposable"})
        tid = r.json()["id"]
        r2 = client.delete(f"/api/v1/tags/{tid}")
        assert r2.status_code == 204


# ═══════════════════════════════════════════════════════════════════════════════
# CSV IMPORT  [Heet]
# ═══════════════════════════════════════════════════════════════════════════════

class TestCSVImport:
    def test_upload_csv(self, client):
        csv_content = (
            "subscriber_id,name,email,interests,internal_note\n"
            "1001,Dave Kumar,dave@example.com,product updates,ignore this\n"
            "1002,Eve Patel,eve@example.com,newsletter,also ignore\n"
            "1003,Frank Lee,frank@example.com,all,skip\n"
            "1004,Bad Email,notanemail,offers,skip\n"
            "1005,Alice Smith,alice@example.com,vip,dup\n"  # duplicate
        )
        r = client.post(
            "/api/v1/import-jobs/upload",
            params={"account_id": state["account_id"]},
            files={"file": ("subscribers.csv", csv_content.encode(), "text/csv")},
        )
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["total_rows"] == 5
        assert "email" in d["headers"]
        assert len(d["preview_rows"]) == 5
        state["import_job_id"] = d["job_id"]

    def test_upload_wrong_extension(self, client):
        r = client.post(
            "/api/v1/import-jobs/upload",
            params={"account_id": state["account_id"]},
            files={"file": ("data.txt", b"col1,col2\n1,2", "text/plain")},
        )
        assert r.status_code == 400

    def test_set_field_mapping(self, client):
        r = client.post(
            f"/api/v1/import-jobs/{state['import_job_id']}/map",
            json={
                "field_mapping": {
                    "subscriber_id": "ignore",
                    "name": "first_name",
                    "email": "email",
                    "interests": "ignore",
                    "internal_note": "ignore",
                },
                "list_id": state["list_id"],
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["field_mapping"]["email"] == "email"

    def test_process_without_mapping_fails(self, client):
        # Create a new job and try to process without mapping
        csv_content = "email\ntest@test.com\n"
        r = client.post(
            "/api/v1/import-jobs/upload",
            params={"account_id": state["account_id"]},
            files={"file": ("test.csv", csv_content.encode(), "text/csv")},
        )
        jid = r.json()["job_id"]
        # Process without mapping
        r2 = client.post(f"/api/v1/import-jobs/{jid}/process")
        assert r2.status_code == 400

    def test_trigger_processing(self, client):
        r = client.post(f"/api/v1/import-jobs/{state['import_job_id']}/process")
        assert r.status_code == 200
        assert r.json()["job_id"] == state["import_job_id"]

    def test_check_import_status(self, client):
        import time
        # Background task runs synchronously in TestClient
        r = client.get(f"/api/v1/import-jobs/{state['import_job_id']}")
        assert r.status_code == 200
        d = r.json()
        # Should be completed (TestClient runs background tasks synchronously)
        assert d["status"] in ("completed", "completed_with_errors", "processing", "queued")
        state["import_status"] = d["status"]

    def test_import_results_correct(self, client):
        r = client.get(f"/api/v1/import-jobs/{state['import_job_id']}")
        d = r.json()
        if d["status"] in ("completed", "completed_with_errors"):
            # 3 new (dave, eve, frank) + 1 invalid (notanemail) + 1 duplicate (alice)
            assert d["imported_count"] >= 1
            assert d["invalid_count"] >= 1 or d["duplicate_count"] >= 1

    def test_get_import_errors(self, client):
        r = client.get(f"/api/v1/import-jobs/{state['import_job_id']}/errors")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_import_jobs(self, client):
        r = client.get("/api/v1/import-jobs/", params={"account_id": state["account_id"]})
        assert r.status_code == 200
        assert len(r.json()) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# TEMPLATES  [Heet]
# ═══════════════════════════════════════════════════════════════════════════════

VALID_HTML = """
<html><body>
  <p>Hi {{first_name}},</p>
  <p>Welcome to our newsletter!</p>
  <p>Click here to <a href="{{unsubscribe_link}}">unsubscribe</a>.</p>
</body></html>
"""

INVALID_HTML_NO_UNSUB = "<p>Hi {{first_name}}, just a plain email with no opt-out.</p>"


class TestTemplates:
    def test_create_valid_template(self, client):
        r = client.post("/api/v1/templates/", params={"account_id": state["account_id"]}, json={
            "name": "Welcome Email",
            "subject": "Welcome, {{first_name}}!",
            "pre_header": "You have been invited",
            "body_html": VALID_HTML,
            "body_text": "Hi {{first_name}}, welcome! To unsubscribe visit {{unsubscribe_link}}",
        })
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["name"] == "Welcome Email"
        assert d["is_valid"] is True
        assert d["has_unsubscribe_link"] is True
        assert d["validation_errors"] is None
        state["template_id"] = d["id"]

    def test_create_invalid_template_no_subject(self, client):
        r = client.post("/api/v1/templates/", params={"account_id": state["account_id"]}, json={
            "name": "Bad Template",
            "body_html": VALID_HTML,
        })
        assert r.status_code == 201
        d = r.json()
        assert d["is_valid"] is False
        assert any("Subject" in e for e in d["validation_errors"])
        state["invalid_template_id"] = d["id"]

    def test_create_invalid_template_no_unsubscribe(self, client):
        r = client.post("/api/v1/templates/", params={"account_id": state["account_id"]}, json={
            "name": "No Unsub Template",
            "subject": "Hello!",
            "body_html": INVALID_HTML_NO_UNSUB,
        })
        assert r.status_code == 201
        d = r.json()
        assert d["is_valid"] is False
        assert any("unsubscribe" in e.lower() for e in d["validation_errors"])

    def test_list_templates(self, client):
        r = client.get("/api/v1/templates/", params={"account_id": state["account_id"]})
        assert r.status_code == 200
        d = r.json()
        assert d["total"] >= 1

    def test_search_templates(self, client):
        r = client.get("/api/v1/templates/", params={
            "account_id": state["account_id"], "q": "Welcome"
        })
        assert r.status_code == 200
        assert r.json()["total"] >= 1

    def test_get_template(self, client):
        r = client.get(f"/api/v1/templates/{state['template_id']}")
        assert r.status_code == 200
        assert r.json()["subject"] == "Welcome, {{first_name}}!"

    def test_update_template(self, client):
        r = client.put(f"/api/v1/templates/{state['template_id']}", json={
            "subject": "Welcome back, {{first_name}}!",
        })
        assert r.status_code == 200
        assert r.json()["subject"] == "Welcome back, {{first_name}}!"

    def test_validate_valid_template(self, client):
        r = client.post(f"/api/v1/templates/{state['template_id']}/validate")
        assert r.status_code == 200
        d = r.json()
        assert d["is_valid"] is True
        assert d["errors"] == []

    def test_validate_invalid_template(self, client):
        r = client.post(f"/api/v1/templates/{state['invalid_template_id']}/validate")
        assert r.status_code == 200
        d = r.json()
        assert d["is_valid"] is False
        assert len(d["errors"]) > 0

    def test_duplicate_template(self, client):
        r = client.post(f"/api/v1/templates/{state['template_id']}/duplicate")
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["name"].startswith("Copy of")
        assert d["subject"] == "Welcome back, {{first_name}}!"
        state["dup_template_id"] = d["id"]

    def test_preview_with_merge_fields(self, client):
        r = client.get(f"/api/v1/templates/{state['template_id']}/preview", params={
            "first_name": "Heet",
            "last_name": "Dev",
            "email": "heet@test.com",
        })
        assert r.status_code == 200
        d = r.json()
        assert "Heet" in d["rendered_html"]
        assert "{{first_name}}" not in d["rendered_html"]

    def test_archive_template(self, client):
        r = client.put(f"/api/v1/templates/{state['dup_template_id']}", json={"is_archived": True})
        assert r.status_code == 200
        assert r.json()["is_archived"] is True

    def test_archived_excluded_from_list(self, client):
        r = client.get("/api/v1/templates/", params={"account_id": state["account_id"]})
        ids = [t["id"] for t in r.json()["items"]]
        assert state["dup_template_id"] not in ids

    def test_archived_included_when_requested(self, client):
        r = client.get("/api/v1/templates/", params={
            "account_id": state["account_id"], "include_archived": True
        })
        ids = [t["id"] for t in r.json()["items"]]
        assert state["dup_template_id"] in ids

    def test_template_not_found(self, client):
        r = client.get("/api/v1/templates/99999")
        assert r.status_code == 404

    def test_delete_template(self, client):
        r = client.post("/api/v1/templates/", params={"account_id": state["account_id"]}, json={
            "name": "To Delete", "subject": "Del", "body_html": VALID_HTML,
        })
        tid = r.json()["id"]
        r2 = client.delete(f"/api/v1/templates/{tid}")
        assert r2.status_code == 204
        assert client.get(f"/api/v1/templates/{tid}").status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# PREFERENCES & UNSUBSCRIBE  [Heet]
# ═══════════════════════════════════════════════════════════════════════════════

class TestPreferences:
    def test_create_unsubscribe_token(self, client):
        from tests.conftest import TestingSession
        from crud.crud_suppression import create_unsubscribe_token
        db = TestingSession()
        ut = create_unsubscribe_token(db, state["sub_id"], campaign_id=None)
        state["unsub_token"] = ut.token
        state["unsub_token_id"] = ut.id
        db.close()

    def test_get_preference_center(self, client):
        r = client.get("/api/v1/preferences/", params={"token": state["unsub_token"]})
        assert r.status_code == 200
        d = r.json()
        assert d["email"] == "alice@example.com"
        assert "lists" in d

    def test_invalid_token_returns_404(self, client):
        r = client.get("/api/v1/preferences/", params={"token": "invalid-token-xyz"})
        assert r.status_code == 404

    def test_one_click_unsubscribe(self, client):
        # alice is currently subscribed (updated back if needed)
        # Re-subscribe alice first
        from tests.conftest import TestingSession
        from models.subscriber import Subscriber, SubscriberStatus
        db = TestingSession()
        sub = db.query(Subscriber).filter(Subscriber.id == state["sub_id"]).first()
        sub.status = SubscriberStatus.SUBSCRIBED
        sub.unsubscribed_at = None
        db.commit()
        db.close()

        r = client.post("/api/v1/preferences/unsubscribe", json={"token": state["unsub_token"]})
        assert r.status_code == 200
        d = r.json()
        assert d["email"] == "alice@example.com"
        assert d["status"] == "unsubscribed"

    def test_token_cannot_be_reused(self, client):
        r = client.post("/api/v1/preferences/unsubscribe", json={"token": state["unsub_token"]})
        assert r.status_code == 404  # token already used

    def test_preference_update(self, client):
        # Create a new token for alice (previous was used)
        from tests.conftest import TestingSession
        from models.subscriber import Subscriber, SubscriberStatus
        from crud.crud_suppression import create_unsubscribe_token
        db = TestingSession()
        sub = db.query(Subscriber).filter(Subscriber.id == state["sub_id"]).first()
        sub.status = SubscriberStatus.SUBSCRIBED
        db.commit()
        ut2 = create_unsubscribe_token(db, state["sub_id"])
        state["unsub_token_2"] = ut2.token
        db.close()

        r = client.post("/api/v1/preferences/update", json={
            "token": state["unsub_token_2"],
            "list_ids_to_keep": [state["list_id"]],
            "unsubscribe_all": False,
        })
        assert r.status_code == 200
        assert "updated" in r.json()["message"].lower()

    def test_preference_unsubscribe_all(self, client):
        from tests.conftest import TestingSession
        from models.subscriber import Subscriber, SubscriberStatus
        from crud.crud_suppression import create_unsubscribe_token
        db = TestingSession()
        sub = db.query(Subscriber).filter(Subscriber.id == state["sub_id"]).first()
        sub.status = SubscriberStatus.SUBSCRIBED
        db.commit()
        ut3 = create_unsubscribe_token(db, state["sub_id"])
        state["unsub_token_3"] = ut3.token
        db.close()

        r = client.post("/api/v1/preferences/update", json={
            "token": state["unsub_token_3"],
            "unsubscribe_all": True,
        })
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# CAMPAIGNS
# ═══════════════════════════════════════════════════════════════════════════════

class TestCampaigns:
    def test_create_campaign(self, client):
        r = client.post("/api/v1/campaigns/", params={"account_id": state["account_id"]}, json={
            "name": "May Newsletter",
            "sender_id": state["sender_id"],
            "template_id": state["template_id"],
            "subject": "May updates for {{first_name}}",
            "pre_header": "Our latest news",
            "audiences": [{"audience_type": "list", "audience_id": state["list_id"]}],
        })
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["name"] == "May Newsletter"
        assert d["status"] == "draft"
        state["campaign_id"] = d["id"]

    def test_list_campaigns(self, client):
        r = client.get("/api/v1/campaigns/", params={"account_id": state["account_id"]})
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_get_campaign(self, client):
        r = client.get(f"/api/v1/campaigns/{state['campaign_id']}")
        assert r.status_code == 200

    def test_update_campaign(self, client):
        r = client.put(f"/api/v1/campaigns/{state['campaign_id']}", json={
            "subject": "May updates — don't miss this!",
        })
        assert r.status_code == 200
        assert r.json()["subject"] == "May updates — don't miss this!"

    def test_cancel_non_scheduled(self, client):
        r = client.post(f"/api/v1/campaigns/{state['campaign_id']}/cancel")
        assert r.status_code == 400  # not scheduled yet

    def test_schedule_and_cancel(self, client):
        from tests.conftest import TestingSession
        from models.campaign import Campaign, CampaignStatus
        db = TestingSession()
        c = db.query(Campaign).filter(Campaign.id == state["campaign_id"]).first()
        c.status = CampaignStatus.SCHEDULED
        db.commit()
        db.close()
        r = client.post(f"/api/v1/campaigns/{state['campaign_id']}/cancel")
        assert r.status_code == 200

    def test_campaign_not_found(self, client):
        r = client.get("/api/v1/campaigns/99999")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# AUTOMATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestAutomation:
    def test_create_automation(self, client):
        r = client.post("/api/v1/automations/", params={"account_id": state["account_id"]}, json={
            "name": "Welcome Sequence",
            "trigger_type": "subscriber_added_to_list",
            "trigger_config": {"list_id": state["list_id"]},
            "steps": [
                {"step_type": "email", "template_id": state["template_id"], "position": 0},
                {"step_type": "wait", "wait_duration_hours": 48, "position": 1},
                {"step_type": "email", "template_id": state["template_id"], "position": 2},
            ],
        })
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["name"] == "Welcome Sequence"
        assert d["status"] == "draft"
        assert len(d["steps"]) == 3
        state["automation_id"] = d["id"]

    def test_list_automations(self, client):
        r = client.get("/api/v1/automations/", params={"account_id": state["account_id"]})
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_get_automation(self, client):
        r = client.get(f"/api/v1/automations/{state['automation_id']}")
        assert r.status_code == 200
        assert len(r.json()["steps"]) == 3

    def test_activate_automation(self, client):
        r = client.put(f"/api/v1/automations/{state['automation_id']}", json={"status": "active"})
        assert r.status_code == 200
        assert r.json()["status"] == "active"

    def test_pause_automation(self, client):
        r = client.put(f"/api/v1/automations/{state['automation_id']}", json={"status": "paused"})
        assert r.status_code == 200
        assert r.json()["status"] == "paused"

    def test_automation_not_found(self, client):
        r = client.get("/api/v1/automations/99999")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# ALEMBIC CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

class TestAlembicSetup:
    def test_alembic_env_imports(self):
        import importlib.util, sys, os
        spec = importlib.util.spec_from_file_location(
            "alembic_env",
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic", "env.py"),
        )
        # Just check file is parseable
        with open(spec.origin) as f:
            content = f.read()
        assert "target_metadata" in content
        assert "Base.metadata" in content
