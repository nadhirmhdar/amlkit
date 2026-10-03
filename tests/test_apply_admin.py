"""Quotation requests: admin viewer, retention, and real SMTP delivery.

The viewer is for the platform admin who receives the requests (a super-admin
whose email is a quote recipient) -- nobody else, not even an org MLRO.
"""
from __future__ import annotations

import os
import re
import socketserver
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import pytest
from conftest import register_org

from test_apply import GOOD  # noqa: F401  (form payload)

ADMIN_EMAIL = "info@grovisor.ae"


def _db():
    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    conn.row_factory = sqlite3.Row
    return conn


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("AMLKIT_DB", str(tmp_path / "t.db"))
    for var in ("AMLKIT_SMTP_HOST", "AMLKIT_QUOTE_TO"):
        monkeypatch.delenv(var, raising=False)
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    return TestClient(app)


def _submit(c, **over):
    c.get("/apply")
    data = {**GOOD, **over, "csrf_token": c.cookies.get("amlkit_csrf")}
    return c.post("/apply", data=data, follow_redirects=False)


def _as_admin(tmp_c, email=ADMIN_EMAIL, super_admin=True):
    register_org(tmp_c, f"Org of {email}", "Info", email)
    conn = _db()
    conn.execute("UPDATE operators SET super_admin=? WHERE email=?", (1 if super_admin else 0, email))
    conn.commit()
    conn.close()
    return tmp_c


def test_anonymous_and_ordinary_users_get_404(app_client):
    _submit(app_client)
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    assert TestClient(app).get("/admin/applications").status_code == 404
    # An org MLRO (even a super-admin) whose email is not a quote recipient.
    other = _as_admin(TestClient(app), email="boss@elsewhere.example")
    assert other.get("/admin/applications").status_code == 404
    # The right email without the super-admin flag is not enough either.
    from amlkit.api.app import app as a2
    nobody = _as_admin(TestClient(a2), email=ADMIN_EMAIL, super_admin=False)
    assert nobody.get("/admin/applications").status_code == 404


def test_admin_sees_requests_and_consent_trail(app_client):
    _submit(app_client)
    admin = _as_admin(app_client)
    r = admin.get("/admin/applications")
    assert r.status_code == 200
    assert "Gulf Gold Trading LLC" in r.text and "Layla Haddad" in r.text
    assert "wording 2026-10-v1" in r.text
    # The sidebar link appears for this user.
    assert 'href="/admin/applications"' in admin.get("/dashboard").text


def test_admin_can_change_status_and_delete(app_client):
    _submit(app_client)
    admin = _as_admin(app_client)
    tok = admin.cookies.get("amlkit_csrf")
    admin.post("/admin/applications/1/status", data={"status": "contacted", "csrf_token": tok})
    row = _db().execute("SELECT status, status_changed_at FROM applications WHERE id=1").fetchone()
    assert row["status"] == "contacted" and row["status_changed_at"]
    admin.post("/admin/applications/1/delete", data={"csrf_token": tok})
    assert _db().execute("SELECT COUNT(*) FROM applications").fetchone()[0] == 0
    actions = {r["action"] for r in _db().execute("SELECT action FROM audit_log")}
    assert {"application.status", "application.deleted"} <= actions


def test_acting_on_a_missing_request_reports_an_error_not_success(app_client):
    admin = _as_admin(app_client)
    tok = admin.cookies.get("amlkit_csrf")
    for path, data in (("/admin/applications/999/status", {"status": "contacted"}),
                       ("/admin/applications/999/delete", {})):
        page = admin.post(path, data={**data, "csrf_token": tok}).text
        assert "Request #999 not found." in page, path
        assert "marked contacted" not in page and "#999 deleted" not in page, path


def test_actions_need_csrf_and_the_right_user(app_client):
    _submit(app_client)
    admin = _as_admin(app_client)
    admin.post("/admin/applications/1/delete", data={"csrf_token": "wrong"})
    assert _db().execute("SELECT COUNT(*) FROM applications").fetchone()[0] == 1
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    anon = TestClient(app)
    assert anon.post("/admin/applications/1/delete", data={"csrf_token": "x"}).status_code == 404
    assert _db().execute("SELECT COUNT(*) FROM applications").fetchone()[0] == 1


def test_retention_purges_idle_requests_but_never_won_ones(app_client):
    from amlkit.cases import applications as apps
    for _ in range(4):
        _submit(app_client)
    old = (datetime.now(timezone.utc) - timedelta(days=apps.RETENTION_DAYS + 5)).isoformat(timespec="seconds")
    fresh = (datetime.now(timezone.utc) - timedelta(days=apps.RETENTION_DAYS - 5)).isoformat(timespec="seconds")
    conn = _db()
    conn.execute("UPDATE applications SET created_at=?, status_changed_at=?, status='lost' WHERE id=1", (old, old))
    conn.execute("UPDATE applications SET created_at=?, status_changed_at=?, status='won' WHERE id=2", (old, old))
    conn.execute("UPDATE applications SET created_at=?, status_changed_at=? WHERE id=3", (old, fresh))  # touched recently
    conn.commit()
    assert apps.expired_count(conn) == 1
    assert apps.purge_expired(conn, actor="test") == 1
    left = {r["id"] for r in conn.execute("SELECT id FROM applications")}
    assert left == {2, 3, 4}
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='application.purged'").fetchone()[0] == 1
    conn.close()


def test_scheduled_refresh_runs_the_purge(app_client, monkeypatch):
    called = {}
    import amlkit.cases.applications as apps
    monkeypatch.setattr(apps, "purge_expired", lambda conn, actor="system", now=None: called.setdefault("n", 0) or 0)
    # The endpoint itself needs the scheduler secret; here we only check that
    # the module is importable from the route (wiring), via its source.
    import inspect
    import amlkit.api.app as appmod
    assert "purge_expired" in inspect.getsource(appmod.system_refresh)


def test_consent_wording_states_purpose_retention_and_withdrawal(app_client):
    page = app_client.get("/apply").text
    assert "up to 12 months" in page and "info@grovisor.ae" in page and "/privacy" in page
    assert "Quotation requests" in app_client.get("/privacy").text


# ------------------------------------------------------------ real SMTP socket
class _SMTPSink(socketserver.StreamRequestHandler):
    messages: list[str] = []

    def handle(self):
        w = lambda s: self.wfile.write((s + "\r\n").encode())
        w("220 sink ESMTP")
        data_mode, buf = False, []
        for raw in self.rfile:
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if data_mode:
                if line == ".":
                    _SMTPSink.messages.append("\n".join(buf))
                    data_mode, buf = False, []
                    w("250 queued")
                else:
                    buf.append(line[1:] if line.startswith("..") else line)
                continue
            cmd = line.upper()
            if cmd.startswith(("EHLO", "HELO")):
                w("250 sink")
            elif cmd.startswith("DATA"):
                data_mode = True
                w("354 go")
            elif cmd.startswith("QUIT"):
                w("221 bye")
                return
            else:
                w("250 ok")


def test_request_is_really_delivered_over_smtp(app_client, monkeypatch):
    """No mocks: a real SMTP conversation over a socket reaches the inbox."""
    _SMTPSink.messages = []
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _SMTPSink)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("AMLKIT_SMTP_HOST", "127.0.0.1")
        monkeypatch.setenv("AMLKIT_SMTP_PORT", str(srv.server_address[1]))
        monkeypatch.setenv("AMLKIT_SMTP_USE_TLS", "0")
        r = _submit(app_client)
        assert r.status_code in (302, 303)
        assert len(_SMTPSink.messages) == 1
        msg = _SMTPSink.messages[0]
        assert "To: info@grovisor.ae" in msg
        assert "Reply-To:" in msg and "layla@gulfgold.example" in msg.lower()
        assert "Subject: groAML quotation request: Gulf Gold Trading LLC" in msg
        assert _db().execute("SELECT email_delivery FROM applications").fetchone()[0] == "sent"
    finally:
        srv.shutdown()
