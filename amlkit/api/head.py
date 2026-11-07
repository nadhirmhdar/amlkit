"""Answer HEAD on the public, read-only pages.

The routes are declared GET-only, so a HEAD request (link checkers, uptime
monitors, some crawlers and share-preview bots) got ``405 Method Not Allowed``
and looked like a broken page. For the allow-listed paths below a HEAD is run
as a GET and the body dropped, so status, headers and Content-Length match
what the GET would return.

Deliberately an allow-list: a HEAD must never trigger a GET handler that has a
side effect (email-verification and setup-token links consume a one-time token
on GET), so nothing outside the public marketing pages and static assets is
mapped.
"""
from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_HEAD_PATHS = frozenset({
    "/", "/about", "/aml-law", "/pricing", "/privacy", "/apply", "/login",
    "/register-organization", "/blog", "/robots.txt", "/sitemap.xml",
})
_HEAD_PREFIXES = ("/blog/", "/static/")


def _head_allowed(path: str) -> bool:
    return path in _HEAD_PATHS or path.startswith(_HEAD_PREFIXES)


class HeadAsGetMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "HEAD" or not _head_allowed(scope["path"]):
            await self.app(scope, receive, send)
            return

        async def send_headers_only(message: Message) -> None:
            if message["type"] == "http.response.body":
                message = {"type": "http.response.body", "body": b"", "more_body": message.get("more_body", False)}
            await send(message)

        await self.app({**scope, "method": "GET"}, receive, send_headers_only)
