"""HTTP route tests for freeze obligation ValueError handling.

Verifies that execute/resolve routes return user-friendly errors instead of 500
when freeze obligation is not found, wrong org, or already executed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Reuse test_api's client fixture and helpers
from test_api import client, _csrf  # noqa: E402,F401


def test_execute_nonexistent_freeze_returns_error_not_500(client):
    """POST /freeze-obligations/99999/execute returns error, not 500."""
    r = client.post("/freeze-obligations/99999/execute",
                    data={"csrf_token": _csrf(client), "notes": "Test"},
                    follow_redirects=True)

    # Should NOT be a 500
    assert r.status_code == 200, f"Expected 200 with error, got {r.status_code}"
    # Should show error message
    assert "not found" in r.text.lower() or "err=" in r.url.lower()


def test_resolve_nonexistent_freeze_returns_error_not_500(client):
    """POST /freeze-obligations/99999/resolve returns error, not 500."""
    r = client.post("/freeze-obligations/99999/resolve",
                    data={"csrf_token": _csrf(client),
                          "resolution_reason": "delisted",
                          "notes": "Test"},
                    follow_redirects=True)

    # Should NOT be a 500
    assert r.status_code == 200, f"Expected 200 with error, got {r.status_code}"
    # Should show error message
    assert "not found" in r.text.lower() or "err=" in r.url.lower()
