"""Tests for p50: contextual third card on home page.

The home page's third card should change based on org state:
1. open alerts > 0 -> "Review N open alerts" (already exists)
2. else customers due for adverse media check -> "Check adverse media"
3. else datasets stale (> 20h) -> "Refresh sanctions lists"
4. else -> "All clear" fallback
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.db import connect
from test_api import _register, _seed_sanctions_data


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Test client with fresh database and registered org."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)

    _seed_sanctions_data(db_file)

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    _register(c, "Test Org", "Test User", "test@example.com")
    return c


def test_contextual_card_shows_open_alerts_when_present(client):
    """Branch 1: When open alerts > 0, existing card shows 'Review alerts'."""
    # This already works in current code - third card shows alerts when present
    # Onboard a customer that will trigger an alert
    from test_api import _csrf, LISTED

    r = client.post("/customers", data={
        "reference": "C-ALERT-1",
        "full_name": LISTED,  # Matches sanctions entity
        "customer_type": "natural",
        "csrf_token": _csrf(client),
    }, follow_redirects=True)
    assert r.status_code == 200

    # Now check home page - should show alerts
    r = client.get("/")
    assert r.status_code == 200
    assert "review" in r.text.lower() and "alert" in r.text.lower()


def test_contextual_card_shows_adverse_media_due_when_no_alerts(client):
    """Branch 2: No alerts, but customers due for adverse media check."""
    from test_api import _csrf

    # Onboard a clean customer (no sanctions match, no adverse media run)
    r = client.post("/customers", data={
        "reference": "C-MEDIA-1",
        "full_name": "John Smith Clean",
        "customer_type": "natural",
        "csrf_token": _csrf(client),
    }, follow_redirects=True)
    assert r.status_code == 200

    # Customer now exists but has no adverse media screening record
    # So they're "due" for one. Check home page.
    r = client.get("/")
    assert r.status_code == 200
    # Should mention adverse media
    assert "adverse" in r.text.lower() or "media" in r.text.lower()


def test_contextual_card_shows_refresh_datasets_when_stale(client):
    """Branch 3: No alerts, no customers due for adverse media, but datasets stale."""
    from test_api import _csrf
    import os

    # Onboard a clean customer
    r = client.post("/customers", data={
        "reference": "C-DATASET-1",
        "full_name": "Jane Doe Recent",
        "customer_type": "natural",
        "csrf_token": _csrf(client),
    }, follow_redirects=True)
    assert r.status_code == 200

    # Add an adverse media screening record so they're NOT due
    db_file = os.getenv("AMLKIT_DB")
    conn = connect(db_file)
    # Get customer_id
    cust = conn.execute(
        "SELECT id, org_id FROM customers WHERE full_name = ?",
        ("Jane Doe Recent",)
    ).fetchone()
    # Add a recent successful adverse media screening
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO adverse_media_screenings
           (org_id, customer_id, query_name, trigger, provider, window_months,
            status, run_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (cust["org_id"], cust["id"], "Jane Doe Recent", "onboarding", "gdelt",
         6, "ok", now)
    )

    # Now backdate datasets to > 20 hours old
    old_refresh = (datetime.now(timezone.utc) - timedelta(hours=21)).isoformat()
    conn.execute("UPDATE datasets SET last_refresh = ?", (old_refresh,))
    conn.commit()
    conn.close()

    # Check home page
    r = client.get("/")
    assert r.status_code == 200
    # Should mention refresh or sanctions
    assert "refresh" in r.text.lower() or "sanction" in r.text.lower()


def test_contextual_card_shows_all_clear_fallback(client):
    """Branch 4: No alerts, no due checks, datasets fresh -> 'All clear'."""
    from test_api import _csrf
    import os

    # Onboard a clean customer
    r = client.post("/customers", data={
        "reference": "C-CLEAR-1",
        "full_name": "Bob Perfect Clean",
        "customer_type": "natural",
        "csrf_token": _csrf(client),
    }, follow_redirects=True)
    assert r.status_code == 200

    # Add recent adverse media screening
    db_file = os.getenv("AMLKIT_DB")
    conn = connect(db_file)
    cust = conn.execute(
        "SELECT id, org_id FROM customers WHERE full_name = ?",
        ("Bob Perfect Clean",)
    ).fetchone()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO adverse_media_screenings
           (org_id, customer_id, query_name, trigger, provider, window_months,
            status, run_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (cust["org_id"], cust["id"], "Bob Perfect Clean", "onboarding", "gdelt",
         6, "ok", now)
    )

    # Ensure datasets are fresh
    fresh_refresh = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    conn.execute("UPDATE datasets SET last_refresh = ?", (fresh_refresh,))
    conn.commit()
    conn.close()

    # Check home page
    r = client.get("/")
    assert r.status_code == 200
    # Should show "all clear" or "looking good" type message
    assert "clear" in r.text.lower() or "good" in r.text.lower()
