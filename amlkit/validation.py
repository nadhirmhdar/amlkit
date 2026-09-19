"""File upload validation utilities.

MIME type validation by magic bytes prevents attacks where malicious files
are renamed with safe extensions (e.g., virus.exe → report.pdf).
"""

from __future__ import annotations


# Allowed MIME types and their magic byte signatures
ALLOWED_MIME_TYPES = {
    "application/pdf": [b"%PDF-"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/jpeg": [b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1", b"\xff\xd8\xff\xdb"],
}


def validate_file_mime(content: bytes, filename: str) -> str:
    """Validate file content matches expected MIME type by magic bytes.

    Args:
        content: File content bytes (at least first 512 bytes recommended)
        filename: Original filename (used to infer expected type from extension)

    Returns:
        Detected MIME type string

    Raises:
        ValueError: If content doesn't match expected type or type not allowed
    """
    # Read magic bytes (first 16 bytes is enough for most formats)
    magic = content[:16]

    # Detect actual MIME type by magic bytes
    detected_mime = None
    for mime_type, signatures in ALLOWED_MIME_TYPES.items():
        for sig in signatures:
            if magic.startswith(sig):
                detected_mime = mime_type
                break
        if detected_mime:
            break

    if not detected_mime:
        raise ValueError(
            f"File type not allowed or unrecognized. "
            f"Allowed types: PDF, PNG, JPEG. "
            f"Upload failed for: {filename}"
        )

    # Validate extension matches detected type
    ext = filename.lower().split(".")[-1] if "." in filename else ""
    expected_types = {
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
    }

    expected_mime = expected_types.get(ext)
    if expected_mime and expected_mime != detected_mime:
        raise ValueError(
            f"File content does not match extension. "
            f"Extension suggests {expected_mime} but content is {detected_mime}. "
            f"Upload rejected: {filename}"
        )

    return detected_mime
