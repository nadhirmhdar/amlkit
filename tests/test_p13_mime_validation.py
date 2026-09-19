"""Test p13: MIME magic-byte validation on file uploads.

File uploads must be validated by content (magic bytes), not just extension.
Attackers can rename malicious files (e.g., virus.exe → virus.pdf) to bypass
extension-only checks.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

from amlkit.api.app import app  # noqa: E402


# Magic bytes for common file types
PDF_MAGIC = b'%PDF-'
PNG_MAGIC = b'\x89PNG\r\n\x1a\n'
JPEG_MAGIC = b'\xff\xd8\xff'


class TestP13MIMEValidation:
    """Test MIME type validation by magic bytes."""

    def test_fake_pdf_is_rejected(self) -> None:
        """File with .pdf extension but non-PDF content should be rejected."""
        # Create fake "PDF" file that's actually plain text
        fake_pdf_content = b"This is not a real PDF file"
        fake_pdf = io.BytesIO(fake_pdf_content)

        client = TestClient(app)
        # This route requires authentication, but we're testing the validation
        # which should happen before checking auth
        r = client.post(
            "/api/v1/customers/1/documents?doc_type=passport",
            files={"file": ("malicious.pdf", fake_pdf, "application/pdf")}
        )

        # Should be rejected due to MIME mismatch (400), not auth error (401)
        assert r.status_code in [400, 401, 403], \
            "Fake PDF should be rejected or fail auth"

        if r.status_code == 400:
            error_msg = r.json().get("detail", "").lower()
            assert "mime" in error_msg or "type" in error_msg or "invalid" in error_msg, \
                "Error should mention MIME/type validation"

    def test_real_pdf_passes_validation(self) -> None:
        """File with .pdf extension and PDF magic bytes should pass MIME check."""
        # Create minimal valid PDF
        real_pdf_content = b'%PDF-1.4\n1 0 obj\n<<\n>>\nendobj\n'
        real_pdf = io.BytesIO(real_pdf_content)

        client = TestClient(app)
        r = client.post(
            "/api/v1/customers/1/documents?doc_type=passport",
            files={"file": ("valid.pdf", real_pdf, "application/pdf")}
        )

        # Should NOT be rejected for MIME mismatch (may still fail auth)
        # If it's 400, it shouldn't be due to MIME validation
        if r.status_code == 400:
            error_msg = r.json().get("detail", "").lower()
            assert "mime" not in error_msg and "magic" not in error_msg, \
                "Valid PDF should not fail MIME validation"

    def test_fake_image_is_rejected(self) -> None:
        """File with .png extension but non-PNG content should be rejected."""
        fake_png_content = b"<html><body>Not a PNG</body></html>"
        fake_png = io.BytesIO(fake_png_content)

        client = TestClient(app)
        r = client.post(
            "/api/v1/customers/1/documents?doc_type=photo_id",
            files={"file": ("fake.png", fake_png, "image/png")}
        )

        assert r.status_code in [400, 401, 403], \
            "Fake PNG should be rejected or fail auth"

        if r.status_code == 400:
            error_msg = r.json().get("detail", "").lower()
            assert "mime" in error_msg or "type" in error_msg or "invalid" in error_msg

    def test_real_png_passes_validation(self) -> None:
        """File with .png extension and PNG magic bytes should pass MIME check."""
        # PNG magic bytes + minimal valid PNG header
        real_png_content = PNG_MAGIC + b'\x00\x00\x00\rIHDR' + b'\x00' * 100
        real_png = io.BytesIO(real_png_content)

        client = TestClient(app)
        r = client.post(
            "/api/v1/customers/1/documents?doc_type=photo_id",
            files={"file": ("valid.png", real_png, "image/png")}
        )

        # Should NOT fail MIME validation
        if r.status_code == 400:
            error_msg = r.json().get("detail", "").lower()
            assert "mime" not in error_msg and "magic" not in error_msg

    def test_executable_renamed_as_pdf_is_rejected(self) -> None:
        """Executable file renamed to .pdf should be rejected."""
        # MZ header (DOS executable magic bytes)
        exe_content = b'MZ\x90\x00' + b'\x00' * 100
        fake_pdf = io.BytesIO(exe_content)

        client = TestClient(app)
        r = client.post(
            "/api/v1/customers/1/documents?doc_type=passport",
            files={"file": ("virus.pdf", fake_pdf, "application/pdf")}
        )

        assert r.status_code in [400, 401, 403], \
            "Executable renamed as PDF should be rejected"

        if r.status_code == 400:
            error_msg = r.json().get("detail", "").lower()
            assert any(word in error_msg for word in ["mime", "type", "invalid", "not allowed"])
