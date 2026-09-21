"""Test p30: goAML serializer should gate unsupported report types.

Only report types with UI creation routes should be serializable:
- STR (Suspicious Transaction Report) - via /reports/build
- SAR (Suspicious Activity Report) - via /reports/build
- FFR (Fund Freeze Report) - via /freeze-obligations/{id}/file-ffr

Other types (HRCT, HRCA, DPMSR, REAR, DTR, CTR, PNMR) lack creation routes
and should be rejected by serialize_goaml_xml.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from amlkit.reporting.goaml import GoAMLValidationError, serialize_goaml_xml  # noqa: E402


class TestP30GoAMLGate:
    """Test goAML serializer gates unsupported report types."""

    def test_supported_types_are_serializable(self) -> None:
        """STR, SAR, and FFR should be serializable (have creation routes)."""
        supported_types = ["STR", "SAR", "FFR"]

        for report_type in supported_types:
            payload = {
                "report_type": report_type,
                "reporter_name": "Test Officer",
                "reporter_email": "test@example.com",
            }

            # Add FFR-specific required fields
            if report_type == "FFR":
                payload["freeze_obligation_id"] = 123

            # Should NOT raise ValueError
            try:
                xml = serialize_goaml_xml(payload)
                assert xml, f"{report_type} should produce XML output"
            except GoAMLValidationError:
                # Other validation errors are OK (missing fields etc)
                pass

    def test_unsupported_types_are_rejected(self) -> None:
        """Report types without creation routes should raise ValueError."""
        unsupported_types = ["HRCT", "HRCA", "DPMSR", "REAR", "DTR", "PNMR"]

        for report_type in unsupported_types:
            payload = {
                "report_type": report_type,
                "reporter_name": "Test Officer",
                "reporter_email": "test@example.com",
            }

            # Should raise ValueError BEFORE other validation runs
            # (type gating should be first check)
            with pytest.raises(ValueError, match="not supported"):
                serialize_goaml_xml(payload)

    def test_unsupported_type_error_message_is_clear(self) -> None:
        """Error message should explain which types ARE supported."""
        payload = {
            "report_type": "INVALID_TYPE",
            "reporter_name": "Test Officer",
            "reporter_email": "test@example.com",
        }

        with pytest.raises(ValueError) as exc_info:
            serialize_goaml_xml(payload)

        error_msg = str(exc_info.value).lower()
        # Should mention what types ARE supported
        assert "str" in error_msg or "sar" in error_msg or "ffr" in error_msg, \
            "Error should list supported types"
