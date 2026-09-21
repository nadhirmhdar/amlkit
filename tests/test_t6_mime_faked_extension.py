"""Test t6: MIME validation rejects files with faked extensions.

Verifies that p13's MIME magic-byte validation correctly rejects a JPEG file
renamed with a .pdf extension.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from amlkit.validation import validate_file_mime  # noqa: E402


class TestT6FakedExtension:
    """Test MIME validation rejects files with mismatched extensions."""

    def test_jpeg_renamed_as_pdf_is_rejected(self) -> None:
        """JPEG file renamed to .pdf should be rejected with 400-equivalent error.

        Attack scenario: User uploads malicious JPEG with .pdf extension
        to bypass client-side validation. Server must detect mismatch.
        """
        # Create JPEG content with proper JPEG magic bytes
        jpeg_content = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # JPEG magic + padding

        # Attempt validation with mismatched .pdf extension
        with pytest.raises(ValueError, match="does not match extension"):
            validate_file_mime(jpeg_content, "malicious.pdf")

    def test_png_renamed_as_pdf_is_rejected(self) -> None:
        """PNG file renamed to .pdf should be rejected."""
        png_magic = b"\x89PNG\r\n\x1a\n"
        png_content = png_magic + b"\x00" * 100

        with pytest.raises(ValueError, match="does not match extension"):
            validate_file_mime(png_content, "image.pdf")

    def test_jpeg_renamed_as_png_is_rejected(self) -> None:
        """JPEG file renamed to .png should be rejected."""
        jpeg_content = b"\xff\xd8\xff\xe1" + b"\x00" * 100

        with pytest.raises(ValueError, match="does not match extension"):
            validate_file_mime(jpeg_content, "photo.png")
