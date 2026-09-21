"""First-run guided onboarding for empty orgs (p51)."""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_empty_org_shows_onboarding_guide_all_incomplete(tmp_path, monkeypatch):
    """Empty org (0 customers, no screening, no dashboard visit) shows guide with 3 incomplete steps."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.db import connect, utcnow
    from amlkit.auth import hash_password, create_session

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(db_file)
    now = utcnow()
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
                 ("Test Org", "test-org", "active", now))
    conn.execute("INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at, email_verified_at, disclaimer_acknowledged_at) VALUES (?,?,?,?,?,?,?,?,?)",
                 (1, "Test User", "test@example.ae", hash_password("TestPass123!"), "mlro", 1, now, now, now))
    conn.commit()

    token = create_session(conn, operator_id=1, org_id=1)
    conn.close()

    client = TestClient(app)
    client.cookies.set("amlkit_session", token)

    r = client.get("/")
    assert r.status_code == 200
    html = r.text

    # Onboarding guide should be visible
    assert "Get started with amlkit" in html
    assert "Step 1: Screen a name" in html
    assert "Step 2: Onboard your first customer" in html
    assert "Step 3: Review your dashboard" in html

    # No steps should be marked complete (no checkmark or "complete" indicator)
    # We'll add visual indicators in implementation
    assert html.count("step-complete") == 0 or "✓" not in html


def test_empty_org_with_screening_marks_step1_complete(tmp_path, monkeypatch):
    """Empty org with screening done marks step 1 as complete."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.db import connect, utcnow
    from amlkit.auth import hash_password, create_session

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(db_file)
    now = utcnow()
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
                 ("Test Org", "test-org", "active", now))
    conn.execute("INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at, email_verified_at, disclaimer_acknowledged_at) VALUES (?,?,?,?,?,?,?,?,?)",
                 (1, "Test User", "test@example.ae", hash_password("TestPass123!"), "mlro", 1, now, now, now))

    # Add a screening record to show step 1 is done
    conn.execute("INSERT INTO screenings (org_id, query_name, trigger, algorithm, threshold, run_at) VALUES (?,?,?,?,?,?)",
                 (1, "Test Name", "adhoc", "weighted", 0.75, now))
    conn.commit()

    token = create_session(conn, operator_id=1, org_id=1)
    conn.close()

    client = TestClient(app)
    client.cookies.set("amlkit_session", token)

    r = client.get("/")
    assert r.status_code == 200
    html = r.text

    # Guide still visible (0 customers)
    assert "Get started with amlkit" in html

    # Step 1 should be marked complete
    # Check for completion indicator - we'll use data attribute or class
    assert 'data-step="1" data-complete="true"' in html or 'step-1-complete' in html


def test_empty_org_with_dashboard_visit_marks_step3_complete(tmp_path, monkeypatch):
    """Empty org with dashboard visited marks step 3 as complete."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.db import connect, utcnow
    from amlkit.auth import hash_password, create_session

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(db_file)
    now = utcnow()
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
                 ("Test Org", "test-org", "active", now))
    conn.execute("INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at, email_verified_at, disclaimer_acknowledged_at) VALUES (?,?,?,?,?,?,?,?,?)",
                 (1, "Test User", "test@example.ae", hash_password("TestPass123!"), "mlro", 1, now, now, now))
    conn.commit()

    token = create_session(conn, operator_id=1, org_id=1)

    # Visit dashboard first to set the flag
    client = TestClient(app)
    client.cookies.set("amlkit_session", token)
    client.get("/dashboard")

    # Now check home page
    r = client.get("/")
    assert r.status_code == 200
    html = r.text

    # Guide still visible (0 customers)
    assert "Get started with amlkit" in html

    # Step 3 should be marked complete
    assert 'data-step="3" data-complete="true"' in html or 'step-3-complete' in html

    conn.close()


def test_org_with_customers_hides_onboarding_guide(tmp_path, monkeypatch):
    """Org with 1+ customers does not show the onboarding guide."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.db import connect, utcnow
    from amlkit.auth import hash_password, create_session

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(db_file)
    now = utcnow()
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
                 ("Test Org", "test-org", "active", now))
    conn.execute("INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at, email_verified_at, disclaimer_acknowledged_at) VALUES (?,?,?,?,?,?,?,?,?)",
                 (1, "Test User", "test@example.ae", hash_password("TestPass123!"), "mlro", 1, now, now, now))

    # Add a customer
    conn.execute("INSERT INTO customers (org_id, reference, customer_type, full_name, canonical_key, status, onboarded_at, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                 (1, "C-001", "natural", "Test Customer", "test|customer", "active", now, now, now))
    conn.commit()

    token = create_session(conn, operator_id=1, org_id=1)
    conn.close()

    client = TestClient(app)
    client.cookies.set("amlkit_session", token)

    r = client.get("/")
    assert r.status_code == 200
    html = r.text

    # Onboarding guide should NOT be visible
    assert "Get started with amlkit" not in html
