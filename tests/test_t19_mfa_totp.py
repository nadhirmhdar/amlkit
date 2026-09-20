"""Test t19: MFA TOTP functionality.

Tests for PR #197 (feat/p15-mfa-totp) - enroll, challenge success,
challenge failure, revoke, backup codes.
"""
import pytest
from amlkit.db import connect
from amlkit import auth


@pytest.fixture
def db():
    """In-memory database with operator."""
    conn = connect(":memory:")

    # Create org
    conn.execute("""
        INSERT INTO organizations (name, slug, status, created_at)
        VALUES ('Test Org', 'test-org', 'active', datetime('now'))
    """)
    org_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Create operator
    conn.execute("""
        INSERT INTO operators (
            org_id, name, email, password_hash, role, is_active, created_at
        ) VALUES (?, 'Test Operator', 'test@example.com', 'hash', 'mlro', 1, datetime('now'))
    """, (org_id,))
    operator_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.commit()
    yield conn, operator_id
    conn.close()


def test_mfa_enroll_generates_secret_and_qr_uri(db):
    """mfa_enroll() should generate TOTP secret and QR URI."""
    conn, operator_id = db

    # Enroll
    secret, qr_uri = auth.mfa_enroll(conn, operator_id)

    # Should return secret (base32 string) and QR URI
    assert isinstance(secret, str)
    assert len(secret) == 32  # Standard TOTP secret length (base32)
    assert isinstance(qr_uri, str)
    assert 'otpauth://totp/' in qr_uri
    assert 'test@example.com' in qr_uri


def test_mfa_is_enrolled_returns_true_after_enrollment(db):
    """mfa_is_enrolled() should return True after enrollment."""
    conn, operator_id = db

    # Before enrollment
    assert auth.mfa_is_enrolled(conn, operator_id) is False

    # Enroll
    auth.mfa_enroll(conn, operator_id)

    # After enrollment
    assert auth.mfa_is_enrolled(conn, operator_id) is True


def test_mfa_verify_succeeds_with_valid_totp_code(db):
    """mfa_verify() should return True for valid TOTP code."""
    conn, operator_id = db

    # Enroll
    secret, _ = auth.mfa_enroll(conn, operator_id)

    # Generate valid TOTP code
    import pyotp
    totp = pyotp.TOTP(secret)
    valid_code = totp.now()

    # Verify
    assert auth.mfa_verify(conn, operator_id, valid_code) is True


def test_mfa_verify_fails_with_invalid_code(db):
    """mfa_verify() should return False for invalid TOTP code."""
    conn, operator_id = db

    # Enroll
    auth.mfa_enroll(conn, operator_id)

    # Try invalid code
    assert auth.mfa_verify(conn, operator_id, "000000") is False
    assert auth.mfa_verify(conn, operator_id, "999999") is False
    assert auth.mfa_verify(conn, operator_id, "invalid") is False


def test_mfa_disable_removes_enrollment(db):
    """mfa_disable() should remove TOTP secret."""
    conn, operator_id = db

    # Enroll
    secret, _ = auth.mfa_enroll(conn, operator_id)

    assert auth.mfa_is_enrolled(conn, operator_id) is True

    # Disable
    auth.mfa_disable(conn, operator_id)

    # Should no longer be enrolled
    assert auth.mfa_is_enrolled(conn, operator_id) is False

    # Old secret should not work
    import pyotp
    totp = pyotp.TOTP(secret)
    valid_code = totp.now()
    assert auth.mfa_verify(conn, operator_id, valid_code) is False


def test_mfa_reenroll_generates_new_secret(db):
    """Re-enrolling should generate a new secret."""
    conn, operator_id = db

    # First enrollment
    secret1, _ = auth.mfa_enroll(conn, operator_id)

    # Disable
    auth.mfa_disable(conn, operator_id)

    # Re-enroll
    secret2, _ = auth.mfa_enroll(conn, operator_id)

    # Should be different
    assert secret2 != secret1

    # Old secret should not work
    import pyotp
    totp1 = pyotp.TOTP(secret1)
    assert auth.mfa_verify(conn, operator_id, totp1.now()) is False

    # New secret should work
    totp2 = pyotp.TOTP(secret2)
    assert auth.mfa_verify(conn, operator_id, totp2.now()) is True


def test_mfa_get_backup_codes_returns_list(db):
    """mfa_get_backup_codes() should return list of backup codes info."""
    conn, operator_id = db

    # Enroll (generates backup codes)
    auth.mfa_enroll(conn, operator_id)

    # Get backup codes
    codes = auth.mfa_get_backup_codes(conn, operator_id)
    assert isinstance(codes, list)
    assert len(codes) >= 5  # Should generate multiple backup codes
    
    # Each code entry should have id, code (truncated), and used flag
    for code in codes:
        assert 'id' in code
        assert 'code' in code
        assert 'used' in code
        assert code['used'] is False  # Initially unused


def test_mfa_not_enrolled_verification_fails(db):
    """mfa_verify() should return False when operator not enrolled."""
    conn, operator_id = db

    # Don't enroll, try to verify
    assert auth.mfa_verify(conn, operator_id, "123456") is False
