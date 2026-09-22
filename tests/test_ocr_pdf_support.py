"""PDF support for the OCR pipeline (amlkit/cases/ocr.py).

Passport/Emirates ID scans are commonly uploaded as PDF (a phone scanner
app, an all-in-one printer) rather than a direct photo -- validate_file_mime
already allow-lists application/pdf for exactly this reason -- but neither
passporteye's MRZ reader nor PIL-based OCR can decode PDF bytes directly.
These tests cover the new `_prepare_image_bytes` PDF-rasterization step and
the routes that exercise it end-to-end.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _make_blank_pdf_bytes(width: float = 595.0, height: float = 842.0) -> bytes:
    """Build a real, minimal single-page PDF in-process (A4-ish points)."""
    import fitz

    doc = fitz.open()
    try:
        doc.new_page(width=width, height=height)
        return doc.tobytes()
    finally:
        doc.close()


class TestPrepareImageBytesPdfRasterization:
    def test_pdf_bytes_are_rasterized_to_a_decodable_image(self) -> None:
        from amlkit.cases.ocr import _prepare_image_bytes

        pdf_bytes = _make_blank_pdf_bytes(width=595.0, height=842.0)
        result = _prepare_image_bytes(pdf_bytes, dpi=300)

        # Rasterization actually happened -- not just the raw PDF handed back.
        assert result != pdf_bytes
        assert not result.startswith(b"%PDF-")

        from PIL import Image
        img = Image.open(io.BytesIO(result))
        img.load()  # force decode

        expected_width = round(595.0 / 72 * 300)
        expected_height = round(842.0 / 72 * 300)
        assert abs(img.width - expected_width) <= 5
        assert abs(img.height - expected_height) <= 5

    def test_non_pdf_bytes_pass_through_unchanged(self) -> None:
        from amlkit.cases.ocr import _prepare_image_bytes

        raw = b"not a real image"
        assert _prepare_image_bytes(raw) == raw

    def test_corrupt_pdf_magic_header_falls_back_to_raw_bytes(self) -> None:
        """Bytes that look like a PDF (magic header) but aren't valid PDF
        content must not raise -- they fall back to the raw bytes per the
        documented behavior, and downstream MRZ/OCR handles them the same
        way any other unreadable input already is (swallowed, all-null)."""
        from amlkit.cases.ocr import _prepare_image_bytes

        garbage = b"%PDF-1.4\ngarbage garbage garbage"
        result = _prepare_image_bytes(garbage)
        assert result == garbage

    def test_extract_passport_data_on_corrupt_pdf_is_all_null_not_a_crash(self) -> None:
        from amlkit.cases.ocr import extract_passport_data

        garbage = b"%PDF-1.4\ngarbage garbage garbage"
        result = extract_passport_data(io.BytesIO(garbage))
        assert result["full_name"] is None
        assert result["id_number"] is None
        assert result["authenticity"] is None


def _csrf(client) -> str:
    return client.cookies.get("amlkit_csrf")


def _register(client, org_name: str, name: str, email: str, password: str = "a-strong-password-1"):
    import re

    client.get("/register-organization")
    r = client.post("/register-organization", data={
        "org_name": org_name, "name": name, "email": email, "password": password,
        "csrf_token": _csrf(client), "invite_code": "test-invite",
    }, follow_redirects=True)
    assert "Check your email" in r.text, f"registration failed: {r.text[:300]}"
    m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r.text)
    assert m, f"no dev verification link in registration response: {r.text[:500]}"
    r2 = client.get(f"/verify-email?token={m.group(1)}", follow_redirects=True)
    from conftest import settle_mfa
    settle_mfa(client)
    assert any(s in r2.text for s in ("Dashboard", "24-hour", "Two-Factor")), f"verification failed: {r2.text[:300]}"
    return client


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_api import _seed_sanctions_data
    _seed_sanctions_data(db_file)

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    _register(c, "PDF OCR Test Firm", "nadhir", "nadhir@pdf-ocr-test.invalid")
    return c


class TestWebScanPassportPdfRoute:
    def test_pdf_upload_reaches_200_via_the_pdf_path(self, client) -> None:
        """Mirrors test_new_features_e2e.py's
        test_scan_passport_response_includes_authenticity_field, but with a
        real (blank) PDF instead of garbage image bytes. A blank page has no
        MRZ, so `authenticity` is expected to be None -- the point here is
        that the PDF path is reached and completes cleanly (200), not that
        fields get magically extracted from a blank page."""
        pdf_bytes = _make_blank_pdf_bytes()
        r = client.post(
            "/customers/scan-passport",
            files={"passport_file": ("scan.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            data={"csrf_token": _csrf(client)},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "authenticity" in data
        assert data["authenticity"] is None
        assert data["full_name"] is None

    def test_non_pdf_garbage_bytes_still_work_unchanged(self, client) -> None:
        """Regression check: non-PDF garbage bytes must still take the
        pass-through path unaffected by the new PDF branch (same assertions
        as the existing test_new_features_e2e.py test, kept independent here
        so this file doesn't depend on that one)."""
        r = client.post(
            "/customers/scan-passport",
            files={"passport_file": ("test.jpg", io.BytesIO(b"not a real image"), "image/jpeg")},
            data={"csrf_token": _csrf(client)},
        )
        assert r.status_code == 200
        data = r.json()
        assert "authenticity" in data
        assert data["authenticity"] is None
        assert data["full_name"] is None


class TestMobileScanEmiratesIdPdfRoute:
    """Mirrors tests/test_mobile_api.py's TestOcrRoutes auth/header pattern:
    a bearer token from /auth/verify-email, exercised over the JSON API."""

    _JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"

    @pytest.fixture()
    def api(self, tmp_path, monkeypatch):
        """Mirrors tests/test_mobile_api.py's `api` fixture exactly: the
        bearer-token JSON API is served by the same `amlkit.api.app.app`
        FastAPI app (mounted under /api/v1), not a separate app object."""
        db_file = tmp_path / "test.db"
        monkeypatch.setenv("AMLKIT_DB", str(db_file))
        monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)

        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from test_api import _seed_sanctions_data
        _seed_sanctions_data(db_file)

        from fastapi.testclient import TestClient
        from amlkit.api.app import app

        client = TestClient(app)
        r = client.post("/api/v1/auth/register-organization", json={
            "org_name": "PDF Mobile OCR Test Firm",
            "name": "nadhir", "email": "nadhir@pdf-mobile-ocr-test.invalid",
            "password": "a-strong-password-1", "invite_code": "test-invite",
        })
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "verification_required"
        verify_token = r.json()["dev_verification_token"]

        r2 = client.post("/api/v1/auth/verify-email", json={"token": verify_token})
        assert r2.status_code == 200, r2.text
        token = r2.json()["token"]
        assert r2.json()["mfa_required"] is True
        from conftest import unlock_mobile_mfa
        unlock_mobile_mfa(client, token)
        headers = {"Authorization": f"Bearer {token}"}
        return client, headers

    def test_pdf_upload_to_scan_emirates_id_reaches_200(self, api, monkeypatch) -> None:
        """The tesseract binary itself isn't installed in this test
        environment (every existing Emirates ID test in test_mobile_api.py
        works around the same gap), so only pytesseract's own call is
        stubbed -- `_prepare_image_bytes`'s PDF rasterization inside
        `extract_emirates_id_data` still runs for real, which is the thing
        this test exists to cover."""
        import pytesseract

        def fake_image_to_data(img, output_type=None):
            img.load()  # confirm a real, decodable raster image was handed in
            return {"text": [], "conf": []}

        monkeypatch.setattr(pytesseract, "image_to_data", fake_image_to_data)

        client, headers = api
        pdf_bytes = _make_blank_pdf_bytes()
        r = client.post(
            "/api/v1/customers/scan-emirates-id", headers=headers,
            files={"emirates_id_file": ("id.pdf", pdf_bytes, "application/pdf")},
        )
        assert r.status_code == 200, r.text
        assert "id_number" in r.json()
