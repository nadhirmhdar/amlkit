"""Test MIME magic-byte validation on file uploads (t6)."""
import pytest
import sys
import io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.names.arabic import canonical_key as _ck


# Magic bytes
PDF_MAGIC = b'%PDF-'
PNG_MAGIC = b'\x89PNG\r\n\x1a\n'
JPEG_MAGIC = b'\xff\xd8\xff'


def _setup_db(tmp_path, monkeypatch):
    """Create a fresh DB with one org, operator and customer; return bearer token."""
    from amlkit.db import connect, utcnow
    from amlkit.auth import hash_password, create_session

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(db_file)
    now = utcnow()
    conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
        ("Test Org", "test-org", "active", now)
    )
    conn.execute(
        """INSERT INTO operators (org_id, name, email, password_hash, role, is_active,
           created_at, email_verified_at, disclaimer_acknowledged_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (1, "Test User", "test@example.ae", hash_password("Pass123!"), "analyst", 1, now, now, now)
    )
    conn.execute(
        "INSERT INTO customers (org_id, reference, full_name, canonical_key, customer_type, status, onboarded_at, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (1, "CUST-001", "Test Customer", _ck("Test Customer"), "natural", "active", now, now, now)
    )
    conn.commit()

    token = create_session(conn, operator_id=1, org_id=1)
    conn.close()
    return token


def test_pdf_with_fake_png_extension_rejected(tmp_path, monkeypatch):
    """PDF upload with faked .png extension → 400/415 rejected."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    token = _setup_db(tmp_path, monkeypatch)

    # Real PDF content but .png extension
    pdf_content = b'%PDF-1.4\n1 0 obj\n<<\n>>\nendobj\n'
    fake_png = io.BytesIO(pdf_content)

    client = TestClient(app)
    r = client.post(
        "/api/v1/customers/1/documents?doc_type=passport",
        files={"file": ("document.png", fake_png, "image/png")},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Should reject: claimed MIME (PNG) doesn't match actual content (PDF)
    assert r.status_code in [400, 415]
    if r.status_code in [400, 415]:
        detail = r.json().get("detail", "").lower()
        assert any(kw in detail for kw in ("mime", "type", "magic", "content", "extension", "mismatch", "match"))


def test_valid_pdf_accepted(tmp_path, monkeypatch):
    """Valid PDF → accepted."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    token = _setup_db(tmp_path, monkeypatch)

    # Valid PDF content with .pdf extension
    pdf_content = b'%PDF-1.4\n1 0 obj\n<<\n>>\nendobj\n'
    valid_pdf = io.BytesIO(pdf_content)

    client = TestClient(app)
    r = client.post(
        "/api/v1/customers/1/documents?doc_type=passport",
        files={"file": ("document.pdf", valid_pdf, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Should NOT reject for MIME mismatch (may be 201 or 200)
    assert r.status_code not in [400, 415]


def test_valid_png_accepted(tmp_path, monkeypatch):
    """Valid PNG → accepted."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    token = _setup_db(tmp_path, monkeypatch)

    # Valid PNG content
    png_content = PNG_MAGIC + b'\x00\x00\x00\rIHDR' + b'\x00' * 100
    valid_png = io.BytesIO(png_content)

    client = TestClient(app)
    r = client.post(
        "/api/v1/customers/1/documents?doc_type=photo_id",
        files={"file": ("photo.png", valid_png, "image/png")},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Should NOT reject for MIME mismatch
    assert r.status_code not in [400, 415]


def test_faked_jpeg_rejected(tmp_path, monkeypatch):
    """Faked JPEG (mismatched magic bytes) → rejected."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    token = _setup_db(tmp_path, monkeypatch)

    # Text content claiming to be JPEG
    fake_jpeg_content = b"This is not a real JPEG file"
    fake_jpeg = io.BytesIO(fake_jpeg_content)

    client = TestClient(app)
    r = client.post(
        "/api/v1/customers/1/documents?doc_type=photo_id",
        files={"file": ("photo.jpg", fake_jpeg, "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Should reject due to MIME mismatch
    assert r.status_code in [400, 415]
    if r.status_code in [400, 415]:
        detail = r.json().get("detail", "").lower()
        assert any(kw in detail for kw in ("mime", "type", "magic", "content", "extension", "mismatch", "match"))
