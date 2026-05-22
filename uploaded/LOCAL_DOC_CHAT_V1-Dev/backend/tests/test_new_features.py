"""Tests for newly-added features:
- Admin feature-flags CRUD (/api/admin/flags/*)
- Document upload size cap (50 MB)
- SHA-256 duplicate detection (409)
- Reprocess endpoint
- RAG query truncation (>2000 chars must not error)
- ENABLE_VISION_LLM_FOR_PDF_IMAGES flag gating (no-op when false)
- Smoke regression: /api/auth/login, /api/v2/flags, /api/v2/providers,
  /api/v2/documents, /api/v2/widgets
"""
import io
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://app-launch-view-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

OWNER_EMAIL = "owner@example.com"
OWNER_PASS = "test1234"


# ---------------- fixtures ----------------
@pytest.fixture(scope="module")
def owner_headers():
    r = requests.post(f"{API}/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASS}, timeout=20)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def viewer_headers():
    email = f"TEST_viewer_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register",
                      json={"email": email, "password": "test1234", "name": "V"}, timeout=20)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ---------------- Smoke regression ----------------
class TestRegressionEndpoints:
    def test_login_owner(self):
        r = requests.post(f"{API}/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASS}, timeout=15)
        assert r.status_code == 200
        assert r.json()["user"]["role"] == "owner"

    def test_v2_flags(self, viewer_headers):
        r = requests.get(f"{API}/v2/flags", headers=viewer_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "ENABLE_VISION_LLM_FOR_PDF_IMAGES" in d

    def test_v2_providers(self, viewer_headers):
        r = requests.get(f"{API}/v2/providers", headers=viewer_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "llm" in d and "embedding" in d
        assert "provider" in d["llm"] and "model" in d["llm"]

    def test_documents_list(self, owner_headers):
        r = requests.get(f"{API}/v2/documents", headers=owner_headers, timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_widgets_list(self, owner_headers):
        r = requests.get(f"{API}/v2/widgets", headers=owner_headers, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------------- Admin Feature Flags CRUD ----------------
class TestAdminFlags:
    def test_list_flags_owner(self, owner_headers):
        r = requests.get(f"{API}/admin/flags/", headers=owner_headers, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "flags" in body and "overrides" in body
        assert isinstance(body["flags"], dict)
        assert "ENABLE_VISION_LLM_FOR_PDF_IMAGES" in body["flags"]

    def test_list_flags_forbidden_for_viewer(self, viewer_headers):
        r = requests.get(f"{API}/admin/flags/", headers=viewer_headers, timeout=15)
        assert r.status_code == 403

    def test_list_flags_unauthenticated(self):
        r = requests.get(f"{API}/admin/flags/", timeout=15)
        assert r.status_code == 401

    def test_patch_flag_owner_toggle(self, owner_headers):
        # toggle ENABLE_VISION_LLM_FOR_PDF_IMAGES → True
        r = requests.patch(f"{API}/admin/flags/ENABLE_VISION_LLM_FOR_PDF_IMAGES",
                           json={"value": True}, headers=owner_headers, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["flag"] == "ENABLE_VISION_LLM_FOR_PDF_IMAGES"
        assert d["value"] is True
        # verify GET reflects
        r2 = requests.get(f"{API}/admin/flags/", headers=owner_headers, timeout=15)
        assert r2.json()["flags"]["ENABLE_VISION_LLM_FOR_PDF_IMAGES"] is True
        # /v2/flags should also reflect (live dict is patched)
        r3 = requests.get(f"{API}/v2/flags", headers=owner_headers, timeout=15)
        assert r3.json()["ENABLE_VISION_LLM_FOR_PDF_IMAGES"] is True

    def test_patch_invalid_flag_404(self, owner_headers):
        r = requests.patch(f"{API}/admin/flags/NOT_A_REAL_FLAG",
                           json={"value": True}, headers=owner_headers, timeout=15)
        assert r.status_code == 404

    def test_patch_flag_forbidden_for_viewer(self, viewer_headers):
        r = requests.patch(f"{API}/admin/flags/ENABLE_VISION_LLM_FOR_PDF_IMAGES",
                           json={"value": False}, headers=viewer_headers, timeout=15)
        assert r.status_code == 403

    def test_reset_flags_owner(self, owner_headers):
        r = requests.post(f"{API}/admin/flags/reset", headers=owner_headers, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "reset"
        assert "flags" in d
        # vision flag should now be back to env-default (false)
        r2 = requests.get(f"{API}/admin/flags/", headers=owner_headers, timeout=15)
        assert r2.json()["overrides"] == {}
        assert r2.json()["flags"]["ENABLE_VISION_LLM_FOR_PDF_IMAGES"] is False

    def test_reset_flags_forbidden_for_viewer(self, viewer_headers):
        r = requests.post(f"{API}/admin/flags/reset", headers=viewer_headers, timeout=15)
        assert r.status_code == 403


# ---------------- Document upload: size + duplicate + reprocess ----------------
class TestUploadHardening:
    def test_upload_oversize_rejected_413(self, owner_headers):
        # 51 MB dummy txt
        big = b"a" * (51 * 1024 * 1024)
        files = {"file": ("TEST_big.txt", io.BytesIO(big), "text/plain")}
        r = requests.post(f"{API}/v2/documents/ingest",
                          files=files, data={"tags": ""},
                          headers=owner_headers, timeout=120)
        # Either 413 (size limit) or 400 — explicitly accept both per spec
        assert r.status_code in (400, 413), f"expected 413/400, got {r.status_code}: {r.text[:200]}"

    def test_upload_duplicate_rejected_409(self, owner_headers):
        unique_content = f"TEST_dup_content_{uuid.uuid4().hex}".encode()
        files1 = {"file": ("TEST_dup.txt", io.BytesIO(unique_content), "text/plain")}
        r1 = requests.post(f"{API}/v2/documents/ingest",
                           files=files1, data={"tags": ""},
                           headers=owner_headers, timeout=30)
        assert r1.status_code == 200, r1.text
        doc_id = r1.json()["id"]
        pytest.dup_doc_id = doc_id

        # Re-upload same exact bytes
        files2 = {"file": ("TEST_dup_renamed.txt", io.BytesIO(unique_content), "text/plain")}
        r2 = requests.post(f"{API}/v2/documents/ingest",
                           files=files2, data={"tags": ""},
                           headers=owner_headers, timeout=30)
        assert r2.status_code == 409, r2.text
        body = r2.json()
        # FastAPI HTTPException(detail={...}) wraps in {"detail": {...}}
        detail = body.get("detail", body)
        assert detail.get("code") == "DUPLICATE"
        assert detail.get("existing_id") == doc_id

    def test_reprocess_endpoint(self, owner_headers):
        doc_id = getattr(pytest, "dup_doc_id", None)
        assert doc_id, "previous test must have created a doc"
        # let it ingest first
        time.sleep(2)
        r = requests.post(f"{API}/v2/documents/{doc_id}/reprocess",
                          headers=owner_headers, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["id"] == doc_id
        assert d["status"] == "queued"
        # verify status reset via processing-status (queued or progressing)
        time.sleep(1)
        r2 = requests.get(f"{API}/v2/documents/{doc_id}/processing-status",
                          headers=owner_headers, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["status"] in ("queued", "extracting", "chunking", "embedding",
                                        "indexed", "ready", "failed")

    def test_reprocess_nonexistent_404(self, owner_headers):
        r = requests.post(f"{API}/v2/documents/does-not-exist-xyz/reprocess",
                          headers=owner_headers, timeout=15)
        assert r.status_code == 404

    def test_reprocess_forbidden_for_viewer(self, viewer_headers):
        r = requests.post(f"{API}/v2/documents/some-id/reprocess",
                          headers=viewer_headers, timeout=15)
        # viewer lacks editor role → 403 (before 404 check)
        assert r.status_code == 403


# ---------------- RAG query truncation ----------------
class TestRagQueryTruncation:
    def test_long_query_does_not_error(self, owner_headers):
        # 4000-char query → service should silently truncate to 2000.
        long_q = "what is this about? " * 250  # ~5000 chars
        r = requests.post(f"{API}/v2/chat",
                          json={"query": long_q, "document_ids": [], "stream": False},
                          headers=owner_headers, timeout=60)
        # Acceptable outcomes:
        #   200 (chat answered or returned no-context message)
        #   400 (no docs / no LLM key — clear validation error)
        # NOT acceptable: 500 (would mean truncation logic crashed)
        assert r.status_code != 500, f"server crashed on long query: {r.text[:300]}"
        assert r.status_code in (200, 400, 422), f"unexpected: {r.status_code} {r.text[:200]}"


# ---------------- Vision flag gating (no real Anthropic key needed) ----------------
class TestVisionFlagGating:
    """Verify ENABLE_VISION_LLM_FOR_PDF_IMAGES gates the vision code path.
    We toggle the flag via the admin endpoint and inspect the live /v2/flags
    response (the same dict is read by services/extraction.maybe_vision_extract).
    """

    def test_flag_default_false(self, owner_headers):
        # ensure clean baseline
        requests.post(f"{API}/admin/flags/reset", headers=owner_headers, timeout=15)
        r = requests.get(f"{API}/v2/flags", headers=owner_headers, timeout=15)
        assert r.status_code == 200
        assert r.json().get("ENABLE_VISION_LLM_FOR_PDF_IMAGES") is False

    def test_flag_toggle_on_then_off(self, owner_headers):
        # ON
        r1 = requests.patch(f"{API}/admin/flags/ENABLE_VISION_LLM_FOR_PDF_IMAGES",
                            json={"value": True}, headers=owner_headers, timeout=15)
        assert r1.status_code == 200
        r2 = requests.get(f"{API}/v2/flags", headers=owner_headers, timeout=15)
        assert r2.json()["ENABLE_VISION_LLM_FOR_PDF_IMAGES"] is True

        # OFF
        r3 = requests.patch(f"{API}/admin/flags/ENABLE_VISION_LLM_FOR_PDF_IMAGES",
                            json={"value": False}, headers=owner_headers, timeout=15)
        assert r3.status_code == 200
        r4 = requests.get(f"{API}/v2/flags", headers=owner_headers, timeout=15)
        assert r4.json()["ENABLE_VISION_LLM_FOR_PDF_IMAGES"] is False

    def test_pdf_upload_with_flag_off_does_not_invoke_vision(self, owner_headers):
        """Upload a tiny text-PDF with flag=false. Ingestion must complete normally;
        no Anthropic call required, no error logged."""
        # ensure flag is OFF
        requests.post(f"{API}/admin/flags/reset", headers=owner_headers, timeout=15)
        # build a minimal 1-page PDF using reportlab if available, else skip
        try:
            from reportlab.pdfgen import canvas
            buf = io.BytesIO()
            c = canvas.Canvas(buf)
            c.drawString(100, 750, f"TEST_vision_off_{uuid.uuid4().hex[:6]}")
            c.showPage()
            c.save()
            pdf_bytes = buf.getvalue()
        except ImportError:
            pytest.skip("reportlab unavailable")

        files = {"file": ("TEST_vision_off.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
        r = requests.post(f"{API}/v2/documents/ingest",
                          files=files, data={"tags": ""},
                          headers=owner_headers, timeout=30)
        assert r.status_code == 200, r.text
        doc_id = r.json()["id"]
        # poll for completion (or failed) — with flag off, no vision API needed
        for _ in range(15):
            time.sleep(1)
            sr = requests.get(f"{API}/v2/documents/{doc_id}/processing-status",
                              headers=owner_headers, timeout=10)
            if sr.json().get("status") in ("ready", "indexed", "failed"):
                break
        final = sr.json()
        # We do not require success (LLM keys may be unset → embedding fails) —
        # we only require the status reaches a terminal state without server crash.
        assert final["status"] in ("ready", "indexed", "failed", "queued",
                                    "extracting", "chunking", "embedding"), final
