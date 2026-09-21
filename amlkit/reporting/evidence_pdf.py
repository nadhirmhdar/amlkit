"""Server-side evidence pack PDF rendering (WeasyPrint).

The evidence pack HTML is rendered to PDF with WeasyPrint. WeasyPrint fetches
every stylesheet, font and image the HTML references, so the fetcher is locked
down: the document is given a synthetic base URL (``PDF_BASE_URL``), and only
URLs under ``PDF_BASE_URL + "static/"`` are served, straight from the local
``web/static`` directory. Every other URL (http/https to any other host,
``file:``, ``ftp:``, ``data:``...) is refused, so customer-controlled content in
the pack cannot make the server issue network requests (SSRF) or read
arbitrary local files into the PDF.

Targets WeasyPrint 70 (pinned in requirements.txt), where a custom fetcher
must be a ``weasyprint.urls.URLFetcher`` subclass overriding ``fetch()`` and
returning a ``URLFetcherResponse``. Plain functions and the removed
``weasyprint.default_url_fetcher`` no longer work.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlsplit

STATIC_ROOT = (Path(__file__).resolve().parent.parent / "web" / "static").resolve()

# Synthetic origin: never resolved over the network, only matched by
# resolve_static_asset(). Root-relative hrefs such as "/static/app.css" in the
# templates resolve against it to PDF_BASE_URL + "static/app.css".
PDF_BASE_URL = "https://amlkit.invalid/"

_MIME_TYPES = {
    ".css": "text/css",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".ttf": "font/ttf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
}


def resolve_static_asset(url: str) -> Path | None:
    """Map an allowed asset URL to a file inside STATIC_ROOT, or return None.

    Only ``PDF_BASE_URL/static/...`` URLs that resolve to an existing file
    inside STATIC_ROOT (no traversal, no symlink escape) are allowed.
    """
    parts = urlsplit(url)
    base = urlsplit(PDF_BASE_URL)
    if (parts.scheme.lower(), parts.netloc.lower()) != (base.scheme, base.netloc):
        return None
    path = unquote(parts.path)
    if not path.startswith("/static/"):
        return None
    candidate = (STATIC_ROOT / path[len("/static/"):]).resolve()
    if not candidate.is_relative_to(STATIC_ROOT) or not candidate.is_file():
        return None
    return candidate


def mime_type_for(path: Path) -> str:
    return (_MIME_TYPES.get(path.suffix.lower())
            or mimetypes.guess_type(path.name)[0]
            or "application/octet-stream")


def make_url_fetcher():
    """Return a WeasyPrint URL fetcher that only serves local static assets.

    Imports WeasyPrint lazily; raises ImportError/OSError when WeasyPrint or
    its native libraries (Pango) are unavailable.
    """
    from weasyprint.urls import URLFetcher, URLFetcherResponse

    class StaticOnlyURLFetcher(URLFetcher):
        def __init__(self):
            # No protocols allowed for the network-capable parent fetch path;
            # fetch() below never delegates to it anyway.
            super().__init__(allowed_protocols=(), allow_redirects=False,
                             fail_on_errors=False)

        def fetch(self, url, headers=None):
            local = resolve_static_asset(url)
            if local is None:
                # Non-fatal: WeasyPrint logs a warning and skips the resource.
                raise ValueError(f"External resource blocked in evidence PDF: {url}")
            return URLFetcherResponse(
                url, body=local.read_bytes(),
                headers={"Content-Type": mime_type_for(local)},
            )

    return StaticOnlyURLFetcher()


def render_pdf(html: str) -> bytes:
    """Render evidence pack HTML to PDF bytes with the locked-down fetcher."""
    import weasyprint

    return weasyprint.HTML(
        string=html,
        base_url=PDF_BASE_URL,
        url_fetcher=make_url_fetcher(),
    ).write_pdf()
