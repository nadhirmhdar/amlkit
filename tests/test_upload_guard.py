"""Shared upload guard (WP-3): size / type / pixel caps, unique stored names,
DOCX policies, and the feedback / ad-hoc screening input caps.

The OCR stack (tesseract) is not needed: every scan test here either is
rejected by the guard before an extractor runs, or stubs the extractor.
"""

from __future__ import annotations

import base64
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conftest import real_image_bytes  # noqa: E402
from test_api import _csrf, _flash_parse, client  # noqa: F401,E402
from test_mobile_api import api  # noqa: F401,E402

@pytest.fixture()
def _enable_limiter():
    """conftest disables slowapi globally; tests that assert 429 opt back in."""
    from amlkit.api.app import app

    app.state.limiter._storage.reset()
    app.state.limiter.enabled = True
    yield
    app.state.limiter.enabled = False


SCAN_ROUTES_WEB = [
    ("/customers/scan-passport", "passport_file"),
    ("/customers/scan-trade-licence", "licence_file"),
]
SCAN_ROUTES_MOBILE = [
    ("/api/v1/customers/scan-passport", "passport_file"),
    ("/api/v1/customers/scan-emirates-id", "emirates_id_file"),
]


def _big_header_png(side: int = 9000) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("L", (side, side), 255).save(buf, "PNG", optimize=True)
    return buf.getvalue()


@pytest.fixture(scope="module")
def bomb_png() -> bytes:
    data = _big_header_png()
    assert len(data) < 1024 * 1024  # small file, large declared canvas
    return data


def _web_scan(client, route, field, name, data, mime="image/png"):
    return client.post(route, files={field: (name, io.BytesIO(data), mime)},
                       data={"csrf_token": _csrf(client)})


def _mobile_scan(c, headers, route, field, name, data, mime="image/png"):
    return c.post(route, headers=headers, files={field: (name, data, mime)})


# ------------------------------------------------------------ validate_upload
class TestValidateUpload:
    def test_returns_detected_mime(self):
        from amlkit.validation import IMAGE_MIMES, validate_upload

        assert validate_upload(real_image_bytes("PNG"), allowed_mimes=IMAGE_MIMES) == "image/png"
        assert validate_upload(real_image_bytes("JPEG"), allowed_mimes=IMAGE_MIMES) == "image/jpeg"

    def test_env_overrides(self, monkeypatch, bomb_png):
        from amlkit.validation import IMAGE_MIMES, UploadTooLarge, validate_upload

        monkeypatch.setenv("AMLKIT_MAX_IMAGE_PIXELS", "100000000")
        assert validate_upload(bomb_png, allowed_mimes=IMAGE_MIMES) == "image/png"
        monkeypatch.setenv("AMLKIT_MAX_UPLOAD_BYTES", "10")
        with pytest.raises(UploadTooLarge):
            validate_upload(real_image_bytes("PNG"), allowed_mimes=IMAGE_MIMES)

    def test_jpeg_with_other_app_markers_is_accepted(self):
        from amlkit.validation import detect_mime

        assert detect_mime(b"\xff\xd8\xff\xe2" + b"\0" * 20) == "image/jpeg"

    def test_docx_needs_word_part(self):
        from amlkit.validation import DOCX, PDF, UploadTypeNotAllowed, validate_upload

        assert validate_upload(_docx_bytes(), allowed_mimes={PDF, DOCX}) == DOCX
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("hello.txt", "x")
        with pytest.raises(UploadTypeNotAllowed):
            validate_upload(buf.getvalue(), allowed_mimes={PDF, DOCX})

    def test_errors_are_value_errors_with_status(self):
        from amlkit.validation import UploadTooLarge, UploadTypeNotAllowed

        assert issubclass(UploadTooLarge, ValueError) and UploadTooLarge.status_code == 413
        assert issubclass(UploadTypeNotAllowed, ValueError) and UploadTypeNotAllowed.status_code == 415


# ------------------------------------------------------------------ web scans
class TestWebScanGuard:
    @pytest.mark.parametrize("route,field", SCAN_ROUTES_WEB)
    def test_huge_canvas_png_is_413(self, client, bomb_png, route, field):  # noqa: F811
        r = _web_scan(client, route, field, "p.png", bomb_png)
        assert r.status_code == 413, r.text
        assert "dimensions" in r.json()["detail"]

    @pytest.mark.parametrize("route,field", SCAN_ROUTES_WEB)
    def test_11mb_blob_is_413(self, client, route, field):  # noqa: F811
        blob = b"\x89PNG\r\n\x1a\n" + b"\0" * (11 * 1024 * 1024)
        r = _web_scan(client, route, field, "p.png", blob)
        assert r.status_code == 413, r.text

    @pytest.mark.parametrize("route,field", SCAN_ROUTES_WEB)
    def test_exe_with_png_magic_is_415(self, client, route, field):  # noqa: F811
        r = _web_scan(client, route, field, "evil.png", b"\x89PNG\r\n\x1a\nMZ\x90\x00 not an image")
        assert r.status_code == 415, r.text

    def test_mz_blob_on_trade_licence_is_415(self, client):  # noqa: F811
        r = _web_scan(client, "/customers/scan-trade-licence", "licence_file", "l.jpg",
                      b"MZ\x90\x00\x03\x00\x00\x00" + b"\0" * 64, "image/jpeg")
        assert r.status_code == 415, r.text

    def test_valid_image_reaches_the_extractor(self, client, monkeypatch):  # noqa: F811
        from amlkit.cases import ocr

        monkeypatch.setattr(ocr, "extract_trade_licence_data", lambda f: {"id_type": "trade_licence"})
        r = _web_scan(client, "/customers/scan-trade-licence", "licence_file", "l.jpg",
                      real_image_bytes("JPEG"), "image/jpeg")
        assert r.status_code == 200

    def test_rate_limit_429_after_ten(self, client, monkeypatch, _enable_limiter):  # noqa: F811
        from amlkit.cases import ocr

        monkeypatch.setattr(ocr, "extract_trade_licence_data", lambda f: {"id_type": "trade_licence"})
        img = real_image_bytes("JPEG")
        codes = [
            _web_scan(client, "/customers/scan-trade-licence", "licence_file", "l.jpg", img, "image/jpeg").status_code
            for _ in range(11)
        ]
        assert codes[:10] == [200] * 10
        assert codes[10] == 429


# ---------------------------------------------------------------- mobile scans
class TestMobileScanGuard:
    @pytest.mark.parametrize("route,field", SCAN_ROUTES_MOBILE)
    def test_huge_canvas_png_is_413(self, api, bomb_png, route, field):  # noqa: F811
        c, headers = api
        r = _mobile_scan(c, headers, route, field, "p.png", bomb_png)
        assert r.status_code == 413, r.text

    @pytest.mark.parametrize("route,field", SCAN_ROUTES_MOBILE)
    def test_11mb_blob_is_413(self, api, route, field):  # noqa: F811
        c, headers = api
        blob = b"\x89PNG\r\n\x1a\n" + b"\0" * (11 * 1024 * 1024)
        assert _mobile_scan(c, headers, route, field, "p.png", blob).status_code == 413

    @pytest.mark.parametrize("route,field", SCAN_ROUTES_MOBILE)
    def test_exe_with_png_magic_is_415(self, api, route, field):  # noqa: F811
        c, headers = api
        r = _mobile_scan(c, headers, route, field, "evil.png", b"\x89PNG\r\n\x1a\nMZ\x90\x00 not an image")
        assert r.status_code == 415, r.text

    def test_rate_limit_429_after_ten(self, api, monkeypatch, _enable_limiter):  # noqa: F811
        import amlkit.cases.ocr as ocr

        monkeypatch.setattr(ocr, "extract_emirates_id_data", lambda f: {"id_type": "emirates_id"})
        monkeypatch.setattr(ocr, "assess_image_quality", lambda f: {"flags": []})
        c, headers = api
        img = real_image_bytes("JPEG")
        codes = [
            _mobile_scan(c, headers, "/api/v1/customers/scan-emirates-id", "emirates_id_file",
                         "e.jpg", img, "image/jpeg").status_code
            for _ in range(11)
        ]
        assert codes[:10] == [200] * 10
        assert codes[10] == 429

    def test_rate_limit_is_per_operator_not_per_ip(self, api, monkeypatch, _enable_limiter):  # noqa: F811
        """Exhausting one token's budget does not throttle a different credential from the same IP."""
        import amlkit.cases.ocr as ocr

        monkeypatch.setattr(ocr, "extract_emirates_id_data", lambda f: {"id_type": "emirates_id"})
        monkeypatch.setattr(ocr, "assess_image_quality", lambda f: {"flags": []})
        c, headers = api
        img = real_image_bytes("JPEG")
        for _ in range(11):
            _mobile_scan(c, headers, "/api/v1/customers/scan-emirates-id", "emirates_id_file", "e.jpg", img, "image/jpeg")
        other = {"Authorization": "Bearer some-other-token"}
        r = _mobile_scan(c, other, "/api/v1/customers/scan-emirates-id", "emirates_id_file", "e.jpg", img, "image/jpeg")
        assert r.status_code == 401  # not 429: separate bucket, then rejected as unauthenticated


# ------------------------------------------------------------ document storage
class TestUniqueStoredNames:
    def _customer(self, c, headers):
        r = c.post("/api/v1/customers", headers=headers, json={"reference": "C-1", "full_name": "Ordinary Person"})
        assert r.status_code == 200, r.text
        return r.json()["customer_id"]

    def test_same_name_uploads_keep_both_blobs(self, api, tmp_path, monkeypatch):  # noqa: F811
        from amlkit import storage

        monkeypatch.setattr(storage, "DOCS_DIR", tmp_path / "docs")
        monkeypatch.setattr(storage, "_GCS_BUCKET", None)
        c, headers = api
        cid = self._customer(c, headers)
        first, second = real_image_bytes("JPEG", (16, 16)), real_image_bytes("JPEG", (32, 32))
        assert first != second
        ids = []
        for blob in (first, second):
            r = c.post(f"/api/v1/customers/{cid}/documents?doc_type=passport", headers=headers,
                       files={"file": ("passport.jpg", blob, "image/jpeg")})
            assert r.status_code == 200, r.text
            assert r.json()["filename"] == "passport.jpg"
            ids.append(r.json()["document_id"])

        from test_api import _db  # same AMLKIT_DB the app uses
        rows = _db().execute("SELECT id, filename, stored_path FROM documents ORDER BY id").fetchall()
        assert [r["filename"] for r in rows] == ["passport.jpg", "passport.jpg"]
        assert rows[0]["stored_path"] != rows[1]["stored_path"]
        assert Path(rows[0]["stored_path"]).read_bytes() == first
        assert Path(rows[1]["stored_path"]).read_bytes() == second
        dl = c.get(f"/api/v1/customers/{cid}/documents/{ids[0]}", headers=headers)
        assert dl.content == first
        assert "passport.jpg" in dl.headers["content-disposition"]

    @pytest.mark.parametrize("bad", ["../x.jpg", "a/b.jpg", "a\\b.jpg", "..jpg"])
    def test_path_in_filename_is_rejected(self, api, bad):  # noqa: F811
        c, headers = api
        cid = self._customer(c, headers)
        r = c.post(f"/api/v1/customers/{cid}/documents?doc_type=passport", headers=headers,
                   files={"file": (bad, real_image_bytes("JPEG"), "image/jpeg")})
        assert r.status_code == 400, r.text

    def test_storage_upload_never_uses_client_name(self, tmp_path, monkeypatch):
        from amlkit import storage

        monkeypatch.setattr(storage, "DOCS_DIR", tmp_path)
        monkeypatch.setattr(storage, "_GCS_BUCKET", None)
        a = storage.upload(b"1", 1, 2, "scan.PDF")
        b = storage.upload(b"2", 1, 2, "scan.PDF")
        assert a != b and a.endswith(".pdf") and "scan" not in Path(a).name
        with pytest.raises(ValueError):
            storage.upload(b"x", 1, 2, "../../etc/passwd")

    def test_oversized_document_is_413(self, api):  # noqa: F811
        c, headers = api
        cid = self._customer(c, headers)
        blob = b"%PDF-1.4\n" + b"\0" * (11 * 1024 * 1024)
        r = c.post(f"/api/v1/customers/{cid}/documents?doc_type=passport", headers=headers,
                   files={"file": ("big.pdf", blob, "application/pdf")})
        assert r.status_code == 413, r.text


# --------------------------------------------------------------------- policies
def _docx_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("_rels/.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
        z.writestr("word/document.xml", '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body/></w:document>')
    return buf.getvalue()


def _flash(r):
    cookie = r.cookies.get("amlkit_flash") or r.headers.get("set-cookie", "")
    return cookie


class TestPolicyDocx:
    def _upload(self, client, name, data, mime):  # noqa: F811
        return client.post("/policies/upload",
                           data={"title": "AML Policy", "category": "AML_Policy", "csrf_token": _csrf(client)},
                           files={"file": (name, io.BytesIO(data), mime)}, follow_redirects=True)

    def test_real_docx_is_accepted(self, client):  # noqa: F811
        r = self._upload(client, "policy.docx", _docx_bytes(),
                         "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        assert r.status_code == 200
        assert "uploaded successfully" in r.text
        assert "AML Policy" in r.text

    def test_zip_without_word_part_is_refused(self, client):  # noqa: F811
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("evil.txt", "x")
        r = self._upload(client, "policy.docx", buf.getvalue(), "application/octet-stream")
        assert "File validation failed" in r.text
        assert "uploaded successfully" not in r.text

    def test_docx_named_pdf_is_refused(self, client):  # noqa: F811
        r = self._upload(client, "policy.pdf", _docx_bytes(), "application/pdf")
        assert "File validation failed" in r.text

    def test_pdf_still_accepted(self, client):  # noqa: F811
        r = self._upload(client, "policy.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")
        assert "uploaded successfully" in r.text


# ---------------------------------------------------------- feedback / screening
class TestInputCaps:
    def test_feedback_over_5000_chars_is_400(self, client):  # noqa: F811
        r = client.post("/feedback", data={"page": "/", "message": "x" * 6000, "csrf_token": _csrf(client)})
        assert r.status_code == 400
        assert "too long" in r.json()["error"]

    def test_feedback_at_cap_is_accepted(self, client):  # noqa: F811
        r = client.post("/feedback", data={"page": "/", "message": "x" * 5000, "csrf_token": _csrf(client)})
        assert r.status_code == 200

    def test_feedback_rate_limited_to_10_per_minute(self, client, _enable_limiter):  # noqa: F811
        codes = [client.post("/feedback", data={"page": "/", "message": "hi", "csrf_token": _csrf(client)}).status_code
                 for _ in range(11)]
        assert codes[:10] == [200] * 10 and codes[10] == 429

    def test_web_screen_201_char_name_is_400_and_unrecorded(self, client):  # noqa: F811
        from test_api import _db

        before = _db().execute("SELECT COUNT(*) FROM screenings").fetchone()[0]
        r = client.post("/screen", data={"name": "A" * 201, "csrf_token": _csrf(client)})
        assert r.status_code == 400
        assert "200 characters" in r.text
        assert _db().execute("SELECT COUNT(*) FROM screenings").fetchone()[0] == before

    def test_web_screen_200_char_name_is_ok(self, client):  # noqa: F811
        r = client.post("/screen", data={"name": "A" * 200, "csrf_token": _csrf(client)})
        assert r.status_code == 200

    def test_mobile_screen_201_char_name_is_400(self, api):  # noqa: F811
        c, headers = api
        r = c.post("/api/v1/screen", headers=headers, json={"name": "A" * 201})
        assert r.status_code == 400
        assert "200 characters" in r.json()["detail"]

    def test_mobile_screen_rate_limited_to_10_per_minute(self, api, _enable_limiter):  # noqa: F811
        c, headers = api
        codes = [c.post("/api/v1/screen", headers=headers, json={"name": "Ordinary Person"}).status_code
                 for _ in range(11)]
        assert codes[:10] == [200] * 10 and codes[10] == 429
