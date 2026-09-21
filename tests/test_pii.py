"""Tests for amlkit/pii.py — PII redaction.

Emirates ID Luhn validation is the key mechanism for cutting false positives:
a random 15-digit number almost never passes, so redacting only Luhn-valid
patterns avoids masking invoice numbers and phone numbers that happen to
start with 784.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.pii import redact, _luhn_check  # noqa: E402


class TestEmiratesIdRedaction:
    def test_with_dashes(self):
        text = "Customer Emirates ID is 784-1985-1234560-8"
        result = redact(text)
        assert "784-1985-1234560-8" not in result
        assert "[REDACTED-EID]" in result

    def test_without_dashes(self):
        text = "EID: 784199012345676"
        result = redact(text)
        assert "784199012345676" not in result
        assert "[REDACTED-EID]" in result

    def test_luhn_invalid_not_redacted(self):
        text = "Invoice 784-2000-9999999-9"
        assert not _luhn_check("784200099999999")
        result = redact(text)
        assert "784-2000-9999999-9" in result

    def test_luhn_valid_redacted(self):
        eid = "784-1985-1234560-8"
        digits = "784198512345608"
        assert _luhn_check(digits)
        result = redact(f"Emirates ID: {eid}")
        assert eid not in result

    def test_embedded_in_sentence(self):
        text = "The customer with EID 784-1985-1234560-8 was verified."
        result = redact(text)
        assert "784-1985-1234560-8" not in result
        assert "customer" in result
        assert "verified" in result

    def test_multiple_eids_redacted(self):
        text = "EID1: 784-1985-1234560-8, EID2: 784-1985-1234560-8"
        result = redact(text)
        assert result.count("[REDACTED-EID]") == 2

    def test_partial_match_not_redacted(self):
        text = "Phone: 7841234567"
        result = redact(text)
        assert "7841234567" in result


class TestEmailRedaction:
    def test_simple_email(self):
        text = "Contact: john.doe@example.com for info"
        result = redact(text)
        assert "john.doe@example.com" not in result
        assert "[REDACTED-EMAIL]" in result

    def test_email_with_plus(self):
        text = "Email: user+tag@domain.co.uk"
        result = redact(text)
        assert "user+tag@domain.co.uk" not in result

    def test_multiple_emails(self):
        text = "From: a@b.com To: c@d.org"
        result = redact(text)
        assert result.count("[REDACTED-EMAIL]") == 2

    def test_not_an_email(self):
        text = "Version 2.0@final"
        result = redact(text)
        assert "2.0@final" in result


class TestPassportRedaction:
    def test_passport_with_label(self):
        text = "Passport: AB1234567"
        result = redact(text)
        assert "AB1234567" not in result
        assert "[REDACTED-PASSPORT]" in result

    def test_passport_number_label(self):
        text = "passport number N12345678"
        result = redact(text)
        assert "N12345678" not in result

    def test_no_label_not_redacted(self):
        text = "Reference: AB1234567"
        result = redact(text)
        assert "AB1234567" in result

    def test_passport_label_case_insensitive(self):
        text = "PASSPORT: XY9876543"
        result = redact(text)
        assert "XY9876543" not in result


class TestPassthrough:
    def test_normal_text_unchanged(self):
        text = "This is a normal sentence about compliance."
        assert redact(text) == text

    def test_empty_string(self):
        assert redact("") == ""

    def test_none_returns_empty(self):
        assert redact(None) == ""

    def test_numbers_not_matching_patterns(self):
        text = "Order #12345, Amount: 50000 AED"
        assert redact(text) == text


class TestLuhnCheck:
    def test_valid_emirates_id(self):
        assert _luhn_check("784198512345608") is True

    def test_invalid_check_digit(self):
        assert _luhn_check("784200099999999") is False

    def test_non_numeric_returns_false(self):
        assert _luhn_check("784abc1234567") is False

    def test_too_short_returns_false(self):
        assert _luhn_check("784") is False
