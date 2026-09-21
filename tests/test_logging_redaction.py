"""Tests for PII redaction in the structured log formatter.

Verifies that Emirates IDs and emails never appear in log output,
even when passed directly in log messages or extra fields.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.logging_config import StructuredFormatter  # noqa: E402


@pytest.fixture()
def formatter():
    return StructuredFormatter()


def _make_record(msg, **kwargs):
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg=msg, args=(), exc_info=None,
    )
    if kwargs:
        record.extra_fields = kwargs
    return record


class TestFormatterRedactsEID:
    def test_eid_in_message_is_redacted(self, formatter):
        record = _make_record("Customer EID: 784-1985-1234560-8")
        output = formatter.format(record)
        data = json.loads(output)
        assert "784-1985-1234560-8" not in data["message"]
        assert "[REDACTED-EID]" in data["message"]

    def test_eid_without_dashes_in_message(self, formatter):
        record = _make_record("Verified 784199012345676")
        output = formatter.format(record)
        data = json.loads(output)
        assert "784199012345676" not in data["message"]


class TestFormatterRedactsEmail:
    def test_email_in_message_is_redacted(self, formatter):
        record = _make_record("Login by user@example.com")
        output = formatter.format(record)
        data = json.loads(output)
        assert "user@example.com" not in data["message"]
        assert "[REDACTED-EMAIL]" in data["message"]

    def test_email_in_extra_field_is_redacted(self, formatter):
        record = _make_record("Login event", email="admin@corp.test")
        output = formatter.format(record)
        data = json.loads(output)
        assert "admin@corp.test" not in data.get("email", "")


class TestFormatterPreservesNonPII:
    def test_normal_message_unchanged(self, formatter):
        record = _make_record("Screening completed for customer 42")
        output = formatter.format(record)
        data = json.loads(output)
        assert data["message"] == "Screening completed for customer 42"

    def test_json_structure_intact(self, formatter):
        record = _make_record("test")
        output = formatter.format(record)
        data = json.loads(output)
        assert "timestamp" in data
        assert "level" in data
        assert "logger" in data
        assert "message" in data
