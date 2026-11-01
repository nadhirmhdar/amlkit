"""File upload validation utilities.

MIME type validation by magic bytes prevents attacks where malicious files
are renamed with safe extensions (e.g., virus.exe -> report.pdf).

`validate_upload` is the one guard every upload route uses: byte cap, magic-byte
type, and (for images) a header-only pixel-count cap, so a tiny file that
declares a huge canvas is refused before any decoder allocates memory for it.
"""

from __future__ import annotations

import io
import os
import zipfile

PDF = "application/pdf"
PNG = "image/png"
JPEG = "image/jpeg"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

IMAGE_MIMES = frozenset({PNG, JPEG})

DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_MAX_IMAGE_PIXELS = 25_000_000  # 25 megapixels

# Allowed MIME types and their magic byte signatures
ALLOWED_MIME_TYPES = {
    PDF: [b"%PDF-"],
    PNG: [b"\x89PNG\r\n\x1a\n"],
    # Any JPEG SOI + marker prefix (JFIF, Exif, ICC, Adobe, ... all start FF D8 FF).
    JPEG: [b"\xff\xd8\xff"],
}


class UploadRejected(ValueError):
    """An upload was refused. `str(exc)` is safe to show to the user."""

    status_code = 400


class UploadTooLarge(UploadRejected):
    """Too many bytes or too many pixels (HTTP 413)."""

    status_code = 413


class UploadTypeNotAllowed(UploadRejected):
    """Content is not one of the allowed types (HTTP 415)."""

    status_code = 415


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


def max_upload_bytes() -> int:
    """Per-upload byte cap: AMLKIT_MAX_UPLOAD_BYTES (default 10 MB)."""
    return _env_int("AMLKIT_MAX_UPLOAD_BYTES", DEFAULT_MAX_UPLOAD_BYTES)


def max_image_pixels() -> int:
    """Per-image pixel cap: AMLKIT_MAX_IMAGE_PIXELS (default 25 megapixels)."""
    return _env_int("AMLKIT_MAX_IMAGE_PIXELS", DEFAULT_MAX_IMAGE_PIXELS)


def read_capped(fileobj, max_bytes: int | None = None) -> bytes:
    """Read an upload's body, never more than the cap plus one byte.

    The extra byte lets `validate_upload` see that the cap was exceeded
    without the whole oversized body being pulled into memory.
    """
    limit = max_bytes if max_bytes is not None else max_upload_bytes()
    return fileobj.read(limit + 1)


def _is_docx(content: bytes) -> bool:
    """A zip holding [Content_Types].xml and a word/ part (OOXML wordprocessing)."""
    if not content.startswith(b"PK\x03\x04"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            names = z.namelist()
    except (zipfile.BadZipFile, OSError):
        return False
    return "[Content_Types].xml" in names and any(n.startswith("word/") for n in names)


def detect_mime(content: bytes) -> str | None:
    """Detected MIME type by magic bytes, or None when unrecognised."""
    magic = content[:16]
    for mime_type, signatures in ALLOWED_MIME_TYPES.items():
        if any(magic.startswith(sig) for sig in signatures):
            return mime_type
    if _is_docx(content):
        return DOCX
    return None


_TYPE_LABELS = {PDF: "PDF", PNG: "PNG", JPEG: "JPEG", DOCX: "DOCX"}


def validate_upload(
    data: bytes,
    *,
    allowed_mimes,
    max_bytes: int | None = None,
    max_pixels: int | None = None,
    check_pdf_pages: bool = False,
) -> str:
    """Check size, magic-byte type and (for images) pixel count; return the MIME.

    With `check_pdf_pages` (scan routes, whose PDFs are rasterised for OCR) a
    PDF is also refused when any of its first PDF_MAX_PAGES pages would render
    to more than the pixel cap at OCR_RENDER_DPI.

    Raises UploadTooLarge (413) for bytes/pixels and UploadTypeNotAllowed (415)
    for type, both ValueError subclasses with user-safe messages. Image
    dimensions come from the file header only (no full decode).
    """
    from PIL import Image

    cap = max_bytes if max_bytes is not None else max_upload_bytes()
    if len(data) > cap:
        raise UploadTooLarge(f"File is too large (maximum {cap / (1024 * 1024):g} MB).")

    detected = detect_mime(data)
    if detected is None or detected not in allowed_mimes:
        allowed = ", ".join(_TYPE_LABELS.get(m, m) for m in sorted(allowed_mimes))
        raise UploadTypeNotAllowed(f"File type not allowed or unrecognised. Allowed types: {allowed}.")

    if detected in IMAGE_MIMES:
        pixel_cap = max_pixels if max_pixels is not None else max_image_pixels()
        # Pillow raises DecompressionBombError at 2x MAX_IMAGE_PIXELS and warns at 1x;
        # we compare the header's own size to our cap, so no global is mutated.
        try:
            with Image.open(io.BytesIO(data)) as im:
                width, height = im.size
        except Image.DecompressionBombError as exc:
            raise UploadTooLarge("Image dimensions are too large.") from exc
        except Exception as exc:
            raise UploadTypeNotAllowed("The image could not be read.") from exc
        if width * height > pixel_cap:
            raise UploadTooLarge(
                f"Image dimensions are too large (maximum {pixel_cap / 1_000_000:g} megapixels)."
            )

    if check_pdf_pages and detected == PDF:
        pixel_cap = max_pixels if max_pixels is not None else max_image_pixels()
        check_pdf_render_size(data, max_pixels=pixel_cap)

    return detected


# PDF scans are rasterised at this DPI for OCR (cases.ocr); only the first
# PDF_MAX_PAGES pages are ever looked at.
OCR_RENDER_DPI = 300
PDF_MAX_PAGES = 5


def pdf_render_pixels(width_pt: float, height_pt: float, dpi: int = OCR_RENDER_DPI) -> int:
    """Pixel count of a page of the given size (points) rendered at `dpi`."""
    return round(width_pt * dpi / 72) * round(height_pt * dpi / 72)


def check_pdf_render_size(data: bytes, *, max_pixels: int | None = None) -> None:
    """Refuse (413) a PDF whose first pages would render to too many pixels.

    Reads only the page sizes (no rendering), so a few-hundred-byte PDF that
    declares a huge MediaBox is rejected before OCR ever allocates a bitmap.
    An unparseable PDF is left alone here: the OCR path already treats it as
    unreadable.
    """
    import pypdfium2 as pdfium

    cap = max_pixels if max_pixels is not None else max_image_pixels()
    try:
        pdf = pdfium.PdfDocument(data)
    except Exception:
        return
    try:
        for index in range(min(len(pdf), PDF_MAX_PAGES)):
            page = pdf[index]
            try:
                width_pt, height_pt = page.get_size()
            finally:
                page.close()
            if not (width_pt > 0 and height_pt > 0) or pdf_render_pixels(width_pt, height_pt) > cap:
                raise UploadTooLarge(
                    f"PDF page {index + 1} is too large to scan "
                    f"(maximum {cap / 1_000_000:g} megapixels at {OCR_RENDER_DPI} dpi)."
                )
    finally:
        pdf.close()


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
    detected_mime = detect_mime(content)
    if detected_mime is None or detected_mime == DOCX:
        # DOCX is only accepted through validate_upload (policy uploads); the
        # customer-document path keeps its PDF/PNG/JPEG allow-list.
        raise ValueError(
            f"File type not allowed or unrecognized. "
            f"Allowed types: PDF, PNG, JPEG. "
            f"Upload failed for: {filename}"
        )

    # Validate extension matches detected type
    ext = filename.lower().split(".")[-1] if "." in filename else ""
    expected_types = {
        "pdf": PDF,
        "png": PNG,
        "jpg": JPEG,
        "jpeg": JPEG,
    }

    expected_mime = expected_types.get(ext)
    if expected_mime and expected_mime != detected_mime:
        raise ValueError(
            f"File content does not match extension. "
            f"Extension suggests {expected_mime} but content is {detected_mime}. "
            f"Upload rejected: {filename}"
        )

    return detected_mime
