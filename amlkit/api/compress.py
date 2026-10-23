"""Selective gzip for responses that carry no per-user secret.

Compressing HTML that embeds a CSRF token or other secret next to
attacker-influenced text opens the BREACH side channel, so the app does
not compress every response. Only these are compressed:

* ``/static/*``, ``/robots.txt`` and ``/sitemap.xml`` -- never contain secrets.
* The public marketing pages (``/about``, ``/blog``, ``/blog/<slug>``) when the
  request carries no session cookie. Their only token (the logout form in the
  signed-in nav) is rendered for signed-in users alone.

Everything else (login, forms, case files, downloads) is sent as before.
"""
from __future__ import annotations

from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from ..auth import SESSION_COOKIE

_ALWAYS_PATHS = frozenset({"/robots.txt", "/sitemap.xml"})
_PUBLIC_PAGES = frozenset({"/about", "/blog"})


def _has_session_cookie(scope: Scope) -> bool:
    needle = SESSION_COOKIE.encode() + b"="
    for name, value in scope.get("headers", ()):
        if name == b"cookie" and needle in value:
            return True
    return False


def _compressible(scope: Scope) -> bool:
    path = scope.get("path", "")
    if path.startswith("/static/") or path in _ALWAYS_PATHS:
        return True
    if path in _PUBLIC_PAGES or path.startswith("/blog/"):
        return not _has_session_cookie(scope)
    return False


class SelectiveGZipMiddleware:
    def __init__(self, app: ASGIApp, minimum_size: int = 500) -> None:
        self.app = app
        self.gzip = GZipMiddleware(app, minimum_size=minimum_size)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and _compressible(scope):
            await self.gzip(scope, receive, send)
        else:
            await self.app(scope, receive, send)
