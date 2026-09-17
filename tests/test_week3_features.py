"""Tests for Week 3 Track A features: logging, caching, and feedback."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _csrf(client) -> str:
    return client.cookies.get("amlkit_csrf")


def _register(client, org_name: str, name: str, email: str, password: str = "a-strong-password-1"):
    from conftest import register_org
    return register_org(client, org_name, name, email, password)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    _register(c, "Test Firm", "alice", "alice@testfirm.ae")
    return c


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    conn.row_factory = sqlite3.Row
    return conn


def test_request_id_header_present(client):
    """Every response should include an X-Request-ID header."""
    r = client.get("/")
    assert "X-Request-ID" in r.headers
    request_id = r.headers["X-Request-ID"]
    assert len(request_id) > 20  # UUID format


def test_feedback_table_exists(client):
    """The feedback table should exist in the schema."""
    conn = _db()
    tables = [r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    assert "feedback" in tables
    conn.close()


def test_feedback_submission(client):
    """Authenticated users can submit feedback."""
    r = client.post("/feedback", data={
        "page": "/customers",
        "message": "The onboarding form is confusing",
        "csrf_token": _csrf(client),
    })
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert "Thank you" in data["message"]

    # Verify feedback was saved
    conn = _db()
    feedback = conn.execute("SELECT * FROM feedback ORDER BY id DESC LIMIT 1").fetchone()
    assert feedback is not None
    assert feedback["page"] == "/customers"
    assert feedback["message"] == "The onboarding form is confusing"
    conn.close()


def test_feedback_requires_auth(client):
    """Unauthenticated users cannot submit feedback."""
    # Logout first
    client.post("/logout")

    r = client.post("/feedback", data={
        "page": "/screen",
        "message": "This is great",
        "csrf_token": _csrf(client),
    })
    assert r.status_code == 401
    data = r.json()
    assert "error" in data


def test_feedback_button_hidden_on_unauthenticated_pages(client):
    """Feedback button should not appear on login/register pages."""
    # Logout to ensure no session
    client.post("/logout")

    # Check login page
    r = client.get("/login")
    assert r.status_code == 200
    assert "feedback-btn" not in r.text

    # Check register page
    r = client.get("/register-organization")
    assert r.status_code == 200
    assert "feedback-btn" not in r.text


def test_feedback_requires_message(client):
    """Feedback submission requires a non-empty message."""
    r = client.post("/feedback", data={
        "page": "/alerts",
        "message": "   ",
        "csrf_token": _csrf(client),
    })
    assert r.status_code == 400
    data = r.json()
    assert "error" in data
    assert "empty" in data["error"].lower()


def test_cache_invalidation():
    """Cache should be cleared after invalidation."""
    from amlkit.match.cache import invalidate, cache_size, _token_cache

    # Populate cache with some fake data
    _token_cache["test_token"] = [1, 2, 3]
    assert cache_size() > 0

    # Invalidate and check it's cleared
    invalidate()
    assert cache_size() == 0


def test_structured_logging_configuration():
    """Logging should be configured with structured JSON formatter."""
    from amlkit.logging_config import configure_logging, StructuredFormatter
    import logging

    configure_logging("INFO")
    root_logger = logging.getLogger()
    assert root_logger.level == logging.INFO
    assert len(root_logger.handlers) > 0
    assert isinstance(root_logger.handlers[0].formatter, StructuredFormatter)


def test_request_id_context():
    """Request ID should be gettable from context after being set."""
    from amlkit.logging_config import set_request_id, get_request_id, clear_request_id

    test_id = "test-request-123"
    set_request_id(test_id)
    assert get_request_id() == test_id

    clear_request_id()
    assert get_request_id() is None
