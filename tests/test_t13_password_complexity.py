"""Test t13: Password complexity enforced at auth.py layer."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_password_under_10_chars_rejected():
    """Password under 10 chars → rejected."""
    from amlkit import auth

    with pytest.raises(auth.PasswordComplexityError, match="10 characters"):
        auth.validate_password_complexity("Short1!")


def test_password_no_uppercase_rejected():
    """No uppercase → rejected."""
    from amlkit import auth

    with pytest.raises(auth.PasswordComplexityError, match="uppercase"):
        auth.validate_password_complexity("lowercase123!")


def test_password_no_digit_rejected():
    """No digit → rejected."""
    from amlkit import auth

    with pytest.raises(auth.PasswordComplexityError, match="digit"):
        auth.validate_password_complexity("NoDigitsHere!")


def test_password_no_special_char_rejected():
    """No special char → rejected."""
    from amlkit import auth

    with pytest.raises(auth.PasswordComplexityError, match="special"):
        auth.validate_password_complexity("NoSpecial123")


def test_valid_password_accepted():
    """Valid password → accepted."""
    from amlkit import auth

    # Should not raise
    auth.validate_password_complexity("ValidPass123!")
