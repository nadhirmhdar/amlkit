"""Unit tests for p13 MIME validation functions."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from amlkit.validation import validate_file_mime  # noqa: E402


class TestMIMEValidation:
    """Unit tests for MIME type validation by magic bytes."""

    def test_valid_pdf_passes(self) -> None:
        """PDF with correct magic bytes should pass validation."""
        pdf_content = b"%PDF-1.4\nSome PDF content here"
        result = validate_file_mime(pdf_content, "document.pdf")
        assert result == "application/pdf"

    def test_fake_pdf_fails(self) -> None:
        """File with .pdf extension but non-PDF content should fail."""
        fake_content = b"This is not a PDF"
        with pytest.raises(ValueError, match="not allowed|unrecognized"):
            validate_file_mime(fake_content, "fake.pdf")

    def test_valid_png_passes(self) -> None:
        """PNG with correct magic bytes should pass validation."""
        png_magic = b"\x89PNG\r\n\x1a\n"
        png_content = png_magic + b"\x00" * 100
        result = validate_file_mime(png_content, "image.png")
        assert result == "image/png"

    def test_fake_png_fails(self) -> None:
        """File with .png extension but non-PNG content should fail."""
        fake_content = b"<html>Not a PNG</html>"
        with pytest.raises(ValueError, match="not allowed|unrecognized"):
            validate_file_mime(fake_content, "fake.png")

    def test_valid_jpeg_passes(self) -> None:
        """JPEG with correct magic bytes should pass validation."""
        jpeg_content = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        result = validate_file_mime(jpeg_content, "photo.jpg")
        assert result == "image/jpeg"

    def test_executable_as_pdf_fails(self) -> None:
        """Executable file renamed to .pdf should fail."""
        exe_content = b"MZ\x90\x00" + b"\x00" * 100  # DOS executable magic
        with pytest.raises(ValueError, match="not allowed|unrecognized"):
            validate_file_mime(exe_content, "virus.pdf")

    def test_pdf_renamed_as_png_fails(self) -> None:
        """PDF file renamed to .png should fail (extension mismatch)."""
        pdf_content = b"%PDF-1.4\nContent"
        with pytest.raises(ValueError, match="does not match extension"):
            validate_file_mime(pdf_content, "document.png")

    def test_empty_file_fails(self) -> None:
        """Empty file should fail validation."""
        with pytest.raises(ValueError, match="not allowed|unrecognized"):
            validate_file_mime(b"", "empty.pdf")

    def test_jpeg_with_jpg_extension_passes(self) -> None:
        """JPEG content with .jpg extension should pass."""
        jpeg_content = b"\xff\xd8\xff\xe1" + b"\x00" * 100
        result = validate_file_mime(jpeg_content, "photo.jpg")
        assert result == "image/jpeg"

    def test_jpeg_with_jpeg_extension_passes(self) -> None:
        """JPEG content with .jpeg extension should pass."""
        jpeg_content = b"\xff\xd8\xff\xdb" + b"\x00" * 100
        result = validate_file_mime(jpeg_content, "photo.jpeg")
        assert result == "image/jpeg"
