"""Test aria-label on password toggle button (Issue #103)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Test client with fresh database."""
    from amlkit.db import connect

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    # Initialize database
    connect(str(db_file))

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    return TestClient(app)


class TestPasswordToggleAria:
    """Test password toggle button accessibility."""

    def test_toggle_button_has_initial_aria_label(self, client) -> None:
        """Password toggle button has initial aria-label="Show password"."""
        r = client.get("/login")
        assert r.status_code == 200
        # Check that button has aria-label attribute
        assert 'aria-label="Show password"' in r.text
        # Button should be present
        assert 'data-action="toggle-password"' in r.text

    def test_toggle_button_present_on_login_page(self, client) -> None:
        """Password toggle button is present on login page."""
        r = client.get("/login")
        assert r.status_code == 200
        assert '<button type="button" data-action="toggle-password"' in r.text

    def test_password_input_has_correct_id(self, client) -> None:
        """Password input has id="password-input" for JS to target."""
        r = client.get("/login")
        assert r.status_code == 200
        assert 'id="password-input"' in r.text
        assert 'type="password"' in r.text
