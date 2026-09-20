"""MFA TOTP tests (p15): enrollment, verification, backup codes, and login flow."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest
import pyotp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def conn():
    from amlkit.db import connect, upsert_dataset, utcnow
    c = connect(":memory:")
    now = utcnow()
    ds = upsert_dataset(c, "test_list", "Test List", is_mandatory=True)
    c.execute("UPDATE datasets SET last_refresh=?, entity_count=1 WHERE id=?", (now, ds))
    c.commit()
    yield c
    c.close()


@pytest.fixture()
def org_id(conn) -> int:
    from amlkit.db import utcnow
    row = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?) RETURNING id",
        ("Test Org", "test-org", "active", utcnow())
    ).fetchone()
    conn.commit()
    return row["id"]


@pytest.fixture()
def operator_id(conn, org_id) -> int:
    from amlkit.db import utcnow
    row = conn.execute(
        "INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at, email_verified_at)"
        " VALUES (?,?,?,?,?,?,?,?) RETURNING id",
        (org_id, "Test MLRO", "mlro@test.ae", "hash", "mlro", 1, utcnow(), utcnow())
    ).fetchone()
    conn.commit()
    return row["id"]


class TestMFAEnrollment:
    def test_enroll_generates_secret_and_qr(self, conn, operator_id):
        from amlkit.auth import mfa_enroll
        secret, qr_uri, backup_codes = mfa_enroll(conn, operator_id)

        assert secret is not None
        assert len(secret) > 0
        assert "otpauth://totp/" in qr_uri
        assert "mlro%40test.ae" in qr_uri or "mlro@test.ae" in qr_uri

    def test_enroll_generates_10_backup_codes(self, conn, operator_id):
        from amlkit.auth import mfa_enroll
        _, _, backup_codes = mfa_enroll(conn, operator_id)

        assert len(backup_codes) == 10
        for code in backup_codes:
            assert len(code) == 8  # hex(4) = 8 chars

    def test_enroll_sets_enrolled_flag(self, conn, operator_id):
        from amlkit.auth import mfa_enroll, mfa_is_enrolled
        assert not mfa_is_enrolled(conn, operator_id)
        mfa_enroll(conn, operator_id)
        assert mfa_is_enrolled(conn, operator_id)


class TestMFAVerification:
    def test_correct_totp_code_succeeds(self, conn, operator_id):
        from amlkit.auth import mfa_enroll, mfa_verify
        secret, _, _ = mfa_enroll(conn, operator_id)

        totp = pyotp.TOTP(secret)
        assert mfa_verify(conn, operator_id, totp.now()) is True

    def test_wrong_code_fails(self, conn, operator_id):
        from amlkit.auth import mfa_enroll, mfa_verify
        mfa_enroll(conn, operator_id)
        assert mfa_verify(conn, operator_id, "000000") is False

    def test_verify_without_enrollment_fails(self, conn, operator_id):
        from amlkit.auth import mfa_verify
        assert mfa_verify(conn, operator_id, "123456") is False


class TestBackupCodes:
    def test_backup_code_works_once(self, conn, operator_id):
        from amlkit.auth import mfa_enroll, mfa_verify_backup_code
        _, _, backup_codes = mfa_enroll(conn, operator_id)

        raw_code = backup_codes[0]
        assert mfa_verify_backup_code(conn, operator_id, raw_code) is True
        assert mfa_verify_backup_code(conn, operator_id, raw_code) is False

    def test_wrong_backup_code_fails(self, conn, operator_id):
        from amlkit.auth import mfa_enroll, mfa_verify_backup_code
        mfa_enroll(conn, operator_id)
        assert mfa_verify_backup_code(conn, operator_id, "notacode") is False


class TestMFADisable:
    def test_disable_removes_enrollment(self, conn, operator_id):
        from amlkit.auth import mfa_enroll, mfa_disable, mfa_is_enrolled
        mfa_enroll(conn, operator_id)
        assert mfa_is_enrolled(conn, operator_id)
        mfa_disable(conn, operator_id)
        assert not mfa_is_enrolled(conn, operator_id)


def _csrf(client) -> str:
    return client.cookies.get("amlkit_csrf")


def _register(client, org_name, name, email, password="TestPass2026!"):
    client.get("/register-organization")
    r = client.post("/register-organization", data={
        "org_name": org_name, "name": name, "email": email, "password": password,
        "csrf_token": _csrf(client),
    }, follow_redirects=True)
    m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r.text)
    assert m, f"no verification link: {r.text[:500]}"
    client.get(f"/verify-email?token={m.group(1)}", follow_redirects=True)
    return client


def _seed_sanctions_data(db_file):
    from amlkit.db import connect, upsert_dataset, utcnow
    conn = connect(db_file)
    ds = upsert_dataset(conn, "test_list", "Test List", is_mandatory=True)
    now = utcnow()
    conn.execute("UPDATE datasets SET last_refresh=?, entity_count=1 WHERE id=?", (now, ds))
    conn.commit()
    conn.close()


class TestMFARoutes:
    """Integration tests for MFA web routes."""

    @pytest.fixture()
    def client(self, tmp_path, monkeypatch):
        db_file = tmp_path / "test.db"
        monkeypatch.setenv("AMLKIT_DB", str(db_file))
        monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
        _seed_sanctions_data(db_file)

        from fastapi.testclient import TestClient
        from amlkit.api.app import app
        c = TestClient(app)
        _register(c, "MFA Test Firm", "mlro_mfa", "mlro@mfa-test.ae")
        return c

    def test_mfa_setup_page_loads(self, client):
        r = client.get("/mfa/setup")
        assert r.status_code == 200
        assert "otpauth" in r.text or "MFA" in r.text or "authenticator" in r.text.lower()

    def test_mfa_setup_confirm_with_valid_code(self, client):
        r = client.get("/mfa/setup")
        assert r.status_code == 200

        from amlkit.db import connect
        conn = connect(os.environ["AMLKIT_DB"])
        row = conn.execute("SELECT id FROM operators LIMIT 1").fetchone()
        op_id = row["id"]
        secret_row = conn.execute(
            "SELECT secret FROM mfa_secrets WHERE operator_id=?", (op_id,)
        ).fetchone()
        conn.close()
        assert secret_row is not None

        totp = pyotp.TOTP(secret_row["secret"])
        r = client.post("/mfa/setup", data={
            "code": totp.now(),
            "csrf_token": _csrf(client),
        }, follow_redirects=True)
        assert r.status_code == 200

    def test_mfa_disable_works(self, client):
        client.get("/mfa/setup")
        r = client.post("/mfa/disable", data={
            "csrf_token": _csrf(client),
        }, follow_redirects=True)
        assert r.status_code == 200
