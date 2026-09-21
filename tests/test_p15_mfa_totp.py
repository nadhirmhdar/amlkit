"""MFA TOTP implementation tests (p15)."""
import pytest
import sys
from pathlib import Path
from urllib.parse import unquote
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def test_mfa_enrollment_generates_secret(conn, org_id):
    """Enrolling in MFA generates a TOTP secret."""
    from amlkit.auth import mfa_enroll
    from amlkit.db import utcnow

    # Create operator
    conn.execute(
        "INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at, email_verified_at) VALUES (?,?,?,?,?,?,?,?)",
        (org_id, "Test User", "test@example.ae", "hash", "mlro", 1, utcnow(), utcnow())
    )
    conn.commit()

    secret, qr_uri = mfa_enroll(conn, operator_id=1)

    assert secret is not None
    assert len(secret) > 0
    assert "otpauth://totp/" in qr_uri
    assert "test@example.ae" in unquote(qr_uri)
    # pending until confirmed; a second call resumes rather than rotates
    assert mfa_enroll(conn, operator_id=1)[0] == secret

def test_mfa_verify_correct_code(conn, org_id):
    """MFA verification succeeds with correct TOTP code."""
    from amlkit.auth import mfa_enroll, mfa_verify
    from amlkit.db import utcnow
    import pyotp
    
    conn.execute(
        "INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at, email_verified_at) VALUES (?,?,?,?,?,?,?,?)",
        (org_id, "Test User", "test@example.ae", "hash", "mlro", 1, utcnow(), utcnow())
    )
    conn.commit()
    
    secret, _ = mfa_enroll(conn, operator_id=1)
    
    # Generate valid TOTP code
    totp = pyotp.TOTP(secret)
    valid_code = totp.now()
    
    assert mfa_verify(conn, operator_id=1, code=valid_code) is True

def test_mfa_verify_incorrect_code(conn, org_id):
    """MFA verification fails with incorrect code."""
    from amlkit.auth import mfa_enroll, mfa_verify
    from amlkit.db import utcnow
    
    conn.execute(
        "INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at, email_verified_at) VALUES (?,?,?,?,?,?,?,?)",
        (org_id, "Test User", "test@example.ae", "hash", "mlro", 1, utcnow(), utcnow())
    )
    conn.commit()
    
    mfa_enroll(conn, operator_id=1)
    
    assert mfa_verify(conn, operator_id=1, code="000000") is False

def test_mfa_backup_codes_generated(conn, org_id):
    """Enrolling in MFA generates backup codes."""
    from amlkit.auth import mfa_confirm, mfa_enroll, mfa_get_backup_codes
    from amlkit.db import utcnow
    
    conn.execute(
        "INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at, email_verified_at) VALUES (?,?,?,?,?,?,?,?)",
        (org_id, "Test User", "test@example.ae", "hash", "mlro", 1, utcnow(), utcnow())
    )
    conn.commit()
    
    mfa_enroll(conn, operator_id=1)
    plaintext_codes = mfa_confirm(conn, operator_id=1)

    assert len(plaintext_codes) == 10
    for code in plaintext_codes:
        assert len(code) == 8

    metadata = mfa_get_backup_codes(conn, operator_id=1)
    assert len(metadata) == 10
    for entry in metadata:
        assert "id" in entry
        assert not entry["used"]

def test_mfa_backup_code_verify_and_consume(conn, org_id):
    """Backup codes work once and are consumed."""
    from amlkit.auth import mfa_confirm, mfa_enroll, mfa_get_backup_codes, mfa_verify_backup_code
    from amlkit.db import utcnow
    
    conn.execute(
        "INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at, email_verified_at) VALUES (?,?,?,?,?,?,?,?)",
        (org_id, "Test User", "test@example.ae", "hash", "mlro", 1, utcnow(), utcnow())
    )
    conn.commit()
    
    mfa_enroll(conn, operator_id=1)
    plaintext_codes = mfa_confirm(conn, operator_id=1)
    code = plaintext_codes[0]

    # First use succeeds
    assert mfa_verify_backup_code(conn, operator_id=1, code=code) is True

    # Second use fails (consumed)
    assert mfa_verify_backup_code(conn, operator_id=1, code=code) is False

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
