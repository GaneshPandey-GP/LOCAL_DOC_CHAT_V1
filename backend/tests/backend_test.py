"""DocChat backend API tests (pytest).

Scope: auth, RBAC, documents metadata, share links + guest token isolation,
sessions, flags, admin. Does NOT exercise chat/embedding (keys intentionally unset).
"""
import os
import time
import uuid
import jwt
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://app-launch-view-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

OWNER_EMAIL = "owner@example.com"
OWNER_PASS = "test1234"


# ---------------- fixtures ----------------
@pytest.fixture(scope="session")
def owner_tokens():
    r = requests.post(f"{API}/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASS}, timeout=20)
    assert r.status_code == 200, f"owner login failed: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="session")
def owner_headers(owner_tokens):
    return {"Authorization": f"Bearer {owner_tokens['access_token']}"}


@pytest.fixture(scope="session")
def viewer():
    email = f"TEST_viewer_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register",
                      json={"email": email, "password": "test1234", "name": "Test Viewer"}, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    data["email"] = email
    return data


@pytest.fixture(scope="session")
def viewer_headers(viewer):
    return {"Authorization": f"Bearer {viewer['access_token']}"}


@pytest.fixture(scope="session")
def editor(owner_headers):
    """Create a user and have owner promote to editor."""
    email = f"TEST_editor_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register",
                      json={"email": email, "password": "test1234", "name": "Test Editor"}, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    user_id = data["user"]["id"]
    # promote
    r2 = requests.patch(f"{API}/admin/users/{user_id}", json={"role": "editor"},
                        headers=owner_headers, timeout=20)
    assert r2.status_code == 200, r2.text
    # re-login to get editor-role token
    r3 = requests.post(f"{API}/auth/login", json={"email": email, "password": "test1234"}, timeout=20)
    assert r3.status_code == 200
    data = r3.json()
    data["email"] = email
    return data


@pytest.fixture(scope="session")
def editor_headers(editor):
    return {"Authorization": f"Bearer {editor['access_token']}"}


# ---------------- health ----------------
class TestHealth:
    def test_health(self):
        r = requests.get(f"{API}/health", timeout=10)
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


# ---------------- auth ----------------
class TestAuth:
    def test_register_duplicate(self):
        r = requests.post(f"{API}/auth/register",
                          json={"email": OWNER_EMAIL, "password": OWNER_PASS, "name": "x"}, timeout=15)
        assert r.status_code == 400

    def test_register_new_is_viewer(self):
        email = f"TEST_reg_{uuid.uuid4().hex[:8]}@example.com"
        r = requests.post(f"{API}/auth/register",
                          json={"email": email, "password": "test1234", "name": "R"}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["user"]["role"] == "viewer"
        assert data["user"]["email"] == email.lower()
        assert "password_hash" not in data["user"]
        assert data["access_token"] and data["refresh_token"]

    def test_login_ok(self, owner_tokens):
        assert owner_tokens["user"]["role"] == "owner"
        assert owner_tokens["user"]["email"] == OWNER_EMAIL

    def test_login_bad_creds(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": OWNER_EMAIL, "password": "WRONG"}, timeout=15)
        assert r.status_code == 401

    def test_refresh_ok(self, owner_tokens):
        r = requests.post(f"{API}/auth/refresh",
                          json={"refresh_token": owner_tokens["refresh_token"]}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["access_token"] and d["refresh_token"]
        assert d["user"]["email"] == OWNER_EMAIL

    def test_refresh_invalid(self):
        r = requests.post(f"{API}/auth/refresh", json={"refresh_token": "not-a-jwt"}, timeout=15)
        assert r.status_code == 401

    def test_me_ok(self, owner_headers):
        r = requests.get(f"{API}/auth/me", headers=owner_headers, timeout=15)
        assert r.status_code == 200
        assert r.json()["user"]["email"] == OWNER_EMAIL

    def test_me_missing_token(self):
        r = requests.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 401

    def test_me_invalid_token(self):
        r = requests.get(f"{API}/auth/me", headers={"Authorization": "Bearer junk"}, timeout=15)
        assert r.status_code == 401


# ---------------- RBAC ----------------
class TestRBAC:
    def test_viewer_cannot_upload(self, viewer_headers, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("hello world")
        with f.open("rb") as fh:
            r = requests.post(f"{API}/v2/documents/ingest",
                              files={"file": ("a.txt", fh, "text/plain")},
                              data={"tags": ""}, headers=viewer_headers, timeout=30)
        assert r.status_code == 403

    def test_viewer_cannot_create_share_link(self, viewer_headers):
        r = requests.post(f"{API}/v2/share-links",
                          json={"document_ids": ["fake"], "mode": "public"},
                          headers=viewer_headers, timeout=15)
        assert r.status_code == 403

    def test_viewer_cannot_access_admin(self, viewer_headers):
        for path in ("/admin/analytics", "/admin/audit-log", "/admin/users"):
            r = requests.get(f"{API}{path}", headers=viewer_headers, timeout=15)
            assert r.status_code == 403, f"{path} -> {r.status_code}"


# ---------------- documents ----------------
class TestDocuments:
    def test_upload_txt_owner(self, owner_headers, tmp_path):
        f = tmp_path / "doc_owner.txt"
        f.write_text("This is the OWNER document content for testing.")
        with f.open("rb") as fh:
            r = requests.post(f"{API}/v2/documents/ingest",
                              files={"file": ("doc_owner.txt", fh, "text/plain")},
                              data={"tags": "test,owner"},
                              headers=owner_headers, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "id" in d and d["status"] == "queued"
        pytest.owner_doc_id = d["id"]

        # verify it appears in list
        r2 = requests.get(f"{API}/v2/documents", headers=owner_headers, timeout=15)
        assert r2.status_code == 200
        ids = [x["id"] for x in r2.json()]
        assert d["id"] in ids

    def test_upload_txt_editor(self, editor_headers, tmp_path):
        f = tmp_path / "doc_editor.txt"
        f.write_text("Editor's own document.")
        with f.open("rb") as fh:
            r = requests.post(f"{API}/v2/documents/ingest",
                              files={"file": ("doc_editor.txt", fh, "text/plain")},
                              data={"tags": ""},
                              headers=editor_headers, timeout=30)
        assert r.status_code == 200, r.text
        pytest.editor_doc_id = r.json()["id"]

    def test_processing_status_owner_sees(self, owner_headers):
        doc_id = getattr(pytest, "owner_doc_id", None)
        assert doc_id
        # allow a moment for background task to progress / fail
        time.sleep(3)
        r = requests.get(f"{API}/v2/documents/{doc_id}/processing-status",
                         headers=owner_headers, timeout=15)
        assert r.status_code == 200
        body = r.json()
        # LLM keys may or may not be active; accept any legitimate status.
        assert body["status"] in ("queued", "extracting", "chunking", "embedding",
                                  "indexed", "ready", "failed")

    def test_unsupported_file_type(self, owner_headers, tmp_path):
        f = tmp_path / "x.exe"
        f.write_bytes(b"MZ\x00")
        with f.open("rb") as fh:
            r = requests.post(f"{API}/v2/documents/ingest",
                              files={"file": ("x.exe", fh, "application/octet-stream")},
                              data={"tags": ""}, headers=owner_headers, timeout=15)
        assert r.status_code == 400

    def test_list_scope_non_owner(self, editor_headers, viewer_headers):
        # editor only sees own docs
        r = requests.get(f"{API}/v2/documents", headers=editor_headers, timeout=15)
        assert r.status_code == 200
        ids = [x["id"] for x in r.json()]
        assert getattr(pytest, "editor_doc_id", None) in ids
        assert getattr(pytest, "owner_doc_id", None) not in ids
        # viewer has none
        r2 = requests.get(f"{API}/v2/documents", headers=viewer_headers, timeout=15)
        assert r2.status_code == 200
        assert all(d["owner_id"] != "nobody" for d in r2.json())  # just structural

    def test_get_doc_403_for_non_owner(self, editor_headers):
        doc_id = getattr(pytest, "owner_doc_id", None)
        r = requests.get(f"{API}/v2/documents/{doc_id}", headers=editor_headers, timeout=15)
        assert r.status_code == 403

    def test_get_doc_404(self, owner_headers):
        r = requests.get(f"{API}/v2/documents/does-not-exist", headers=owner_headers, timeout=15)
        assert r.status_code == 404


# ---------------- share links + isolation ----------------
class TestShareLinks:
    @pytest.fixture(scope="class")
    def two_owner_docs(self, owner_headers, tmp_path_factory):
        ids = []
        for name in ("share_a.txt", "share_b.txt"):
            p = tmp_path_factory.mktemp("s") / name
            p.write_text(f"content for {name}")
            with p.open("rb") as fh:
                r = requests.post(f"{API}/v2/documents/ingest",
                                  files={"file": (name, fh, "text/plain")},
                                  data={"tags": ""}, headers=owner_headers, timeout=30)
            assert r.status_code == 200
            ids.append(r.json()["id"])
        return ids

    def test_create_public_link(self, owner_headers, two_owner_docs):
        doc_a, _ = two_owner_docs
        r = requests.post(f"{API}/v2/share-links",
                          json={"document_ids": [doc_a], "mode": "public", "title": "Pub"},
                          headers=owner_headers, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["mode"] == "public" and data["document_ids"] == [doc_a]
        pytest.pub_token = data["token"]

    def test_create_password_link(self, owner_headers, two_owner_docs):
        doc_a, _ = two_owner_docs
        r = requests.post(f"{API}/v2/share-links",
                          json={"document_ids": [doc_a], "mode": "password", "password": "secret1"},
                          headers=owner_headers, timeout=15)
        assert r.status_code == 200
        pytest.pw_token = r.json()["token"]

    def test_create_password_link_requires_password(self, owner_headers, two_owner_docs):
        doc_a, _ = two_owner_docs
        r = requests.post(f"{API}/v2/share-links",
                          json={"document_ids": [doc_a], "mode": "password"},
                          headers=owner_headers, timeout=15)
        assert r.status_code == 400

    def test_create_expiring_link(self, owner_headers, two_owner_docs):
        doc_a, _ = two_owner_docs
        r = requests.post(f"{API}/v2/share-links",
                          json={"document_ids": [doc_a], "mode": "expiring", "expires_in_hours": 1,
                                "single_use": True},
                          headers=owner_headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["expires_at"] and data["single_use"] is True
        pytest.exp_token = data["token"]

    def test_create_fails_for_unowned_doc(self, editor_headers):
        # editor tries to share owner's doc
        owner_doc = getattr(pytest, "owner_doc_id", None)
        r = requests.post(f"{API}/v2/share-links",
                          json={"document_ids": [owner_doc], "mode": "public"},
                          headers=editor_headers, timeout=15)
        assert r.status_code == 403

    def test_list_share_links_owner(self, owner_headers):
        r = requests.get(f"{API}/v2/share-links", headers=owner_headers, timeout=15)
        assert r.status_code == 200
        tokens = [l["token"] for l in r.json()]
        assert pytest.pub_token in tokens

    def test_info_public_no_auth(self):
        r = requests.get(f"{API}/v2/share-links/{pytest.pub_token}/info", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["mode"] == "public" and d["requires_password"] is False

    def test_info_password_no_auth(self):
        r = requests.get(f"{API}/v2/share-links/{pytest.pw_token}/info", timeout=15)
        assert r.status_code == 200
        assert r.json()["requires_password"] is True

    def test_verify_public_returns_scoped_guest_token(self, two_owner_docs):
        doc_a, doc_b = two_owner_docs
        r = requests.post(f"{API}/v2/share-links/{pytest.pub_token}/verify", json={}, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["document_ids"] == [doc_a]
        gt = data["guest_token"]
        # decode without verification to inspect claims (we don't know SHARE_TOKEN_SECRET)
        payload = jwt.decode(gt, options={"verify_signature": False})
        assert payload["type"] == "guest"
        assert payload["document_ids"] == [doc_a]  # scope contains ONLY doc_a not doc_b
        assert doc_b not in payload["document_ids"]

    def test_verify_password_wrong(self):
        r = requests.post(f"{API}/v2/share-links/{pytest.pw_token}/verify",
                          json={"password": "WRONG"}, timeout=15)
        assert r.status_code == 401

    def test_verify_password_ok(self):
        r = requests.post(f"{API}/v2/share-links/{pytest.pw_token}/verify",
                          json={"password": "secret1"}, timeout=15)
        assert r.status_code == 200

    def test_single_use_link_second_open_410(self):
        token = pytest.exp_token
        r1 = requests.post(f"{API}/v2/share-links/{token}/verify", json={}, timeout=15)
        assert r1.status_code == 200
        # /info should now return 410 since opens>0 and single_use
        r2 = requests.get(f"{API}/v2/share-links/{token}/info", timeout=15)
        assert r2.status_code == 410

    def test_chat_with_forged_guest_token_fails(self, two_owner_docs):
        """Forge a guest_token claiming access to BOTH docs. Signed with wrong key → 401."""
        doc_a, doc_b = two_owner_docs
        forged = jwt.encode(
            {"type": "guest", "share_token": pytest.pub_token,
             "document_ids": [doc_a, doc_b],
             "iat": int(time.time()), "exp": int(time.time()) + 3600},
            "wrong-secret", algorithm="HS256",
        )
        r = requests.post(f"{API}/v2/chat",
                          json={"query": "test", "guest_token": forged, "stream": False},
                          timeout=15)
        assert r.status_code == 401, f"forged token should be rejected, got {r.status_code}"

    def test_revoke_then_info_404(self, owner_headers):
        token = pytest.pub_token
        r = requests.delete(f"{API}/v2/share-links/{token}", headers=owner_headers, timeout=15)
        assert r.status_code == 200
        r2 = requests.get(f"{API}/v2/share-links/{token}/info", timeout=15)
        assert r2.status_code == 404


# ---------------- delete doc + share-link cleanup ----------------
class TestDeleteDocument:
    def test_delete_doc_403_for_non_owner(self, editor_headers):
        r = requests.delete(f"{API}/v2/documents/{getattr(pytest, 'owner_doc_id', 'x')}",
                            headers=editor_headers, timeout=15)
        assert r.status_code == 403

    def test_delete_doc_404_missing(self, owner_headers):
        r = requests.delete(f"{API}/v2/documents/missing-xyz", headers=owner_headers, timeout=15)
        assert r.status_code == 404

    def test_delete_doc_ok(self, owner_headers):
        r = requests.delete(f"{API}/v2/documents/{pytest.owner_doc_id}",
                            headers=owner_headers, timeout=15)
        assert r.status_code == 200
        # verify 404 on subsequent get
        r2 = requests.get(f"{API}/v2/documents/{pytest.owner_doc_id}",
                          headers=owner_headers, timeout=15)
        assert r2.status_code == 404


# ---------------- sessions ----------------
class TestSessions:
    def test_list_empty(self, viewer_headers):
        r = requests.get(f"{API}/v2/sessions", headers=viewer_headers, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_messages_404(self, owner_headers):
        r = requests.get(f"{API}/v2/sessions/nonexistent/messages",
                         headers=owner_headers, timeout=15)
        assert r.status_code == 404

    def test_rename_404(self, owner_headers):
        r = requests.patch(f"{API}/v2/sessions/nonexistent",
                           json={"title": "x"}, headers=owner_headers, timeout=15)
        assert r.status_code == 404

    def test_delete_404(self, owner_headers):
        r = requests.delete(f"{API}/v2/sessions/nonexistent",
                            headers=owner_headers, timeout=15)
        assert r.status_code == 404


# ---------------- flags ----------------
class TestFlags:
    def test_flags_requires_auth(self):
        r = requests.get(f"{API}/v2/flags", timeout=15)
        assert r.status_code == 401

    def test_flags_returns_dict(self, viewer_headers):
        r = requests.get(f"{API}/v2/flags", headers=viewer_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d, dict)
        assert "ENABLE_RBAC" in d and "ENABLE_SHARE_LINKS" in d


# ---------------- admin ----------------
class TestAdmin:
    def test_analytics(self, owner_headers):
        r = requests.get(f"{API}/admin/analytics", headers=owner_headers, timeout=20)
        assert r.status_code == 200
        d = r.json()
        for key in ("totals", "latency_ms", "feedback", "queries_daily", "confidence_distribution"):
            assert key in d
        assert "documents" in d["totals"] and "users" in d["totals"]

    def test_audit_log(self, owner_headers):
        r = requests.get(f"{API}/admin/audit-log", headers=owner_headers, timeout=20)
        assert r.status_code == 200
        events = r.json()
        assert isinstance(events, list)
        actions = {e.get("action") for e in events}
        # Should include at least these from our registration/upload activity
        assert "user.register" in actions or "user.login" in actions

    def test_users_list_no_password_hash(self, owner_headers):
        r = requests.get(f"{API}/admin/users", headers=owner_headers, timeout=15)
        assert r.status_code == 200
        users_list = r.json()
        assert isinstance(users_list, list) and len(users_list) >= 1
        for u in users_list:
            assert "password_hash" not in u
            assert "_id" not in u

    def test_update_user_invalid_role(self, owner_headers, viewer):
        r = requests.patch(f"{API}/admin/users/{viewer['user']['id']}",
                           json={"role": "SUPERADMIN"},
                           headers=owner_headers, timeout=15)
        assert r.status_code == 400

    def test_update_user_valid_role(self, owner_headers, viewer):
        r = requests.patch(f"{API}/admin/users/{viewer['user']['id']}",
                           json={"role": "editor"},
                           headers=owner_headers, timeout=15)
        assert r.status_code == 200
        # restore to viewer
        requests.patch(f"{API}/admin/users/{viewer['user']['id']}",
                       json={"role": "viewer"}, headers=owner_headers, timeout=15)
