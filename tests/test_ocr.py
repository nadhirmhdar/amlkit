"""Passport MRZ authenticity-signal tests.

Uses a plain object standing in for passporteye's MRZ result rather than a
real passport image -- `_authenticity_from_mrz` only reads attributes off
that object, so a fake with the same attribute names exercises the same
logic without needing image fixtures or a tesseract/passporteye runtime.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases.ocr import _authenticity_from_mrz  # noqa: E402


def _mrz(**valid_fields):
    defaults = {
        "valid_number": True,
        "valid_date_of_birth": True,
        "valid_expiration_date": True,
        "valid_composite": True,
        "valid_personal_number": True,
        "valid_score": None,
    }
    defaults.update(valid_fields)
    return SimpleNamespace(**defaults)


class TestAuthenticityFromMrz:
    def test_all_checksums_valid_has_no_flags(self) -> None:
        result = _authenticity_from_mrz(_mrz())
        assert result["checksum_failures"] == []
        assert result["flags"] == []

    def test_failed_checksum_is_flagged(self) -> None:
        result = _authenticity_from_mrz(_mrz(valid_date_of_birth=False))
        assert "date_of_birth" in result["checksum_failures"]
        assert any("date of birth" in f for f in result["flags"])

    def test_multiple_failures_all_flagged(self) -> None:
        result = _authenticity_from_mrz(_mrz(valid_number=False, valid_composite=False))
        assert set(result["checksum_failures"]) == {"number", "composite"}
        assert len(result["flags"]) == 2

    def test_uses_library_provided_score_when_present(self) -> None:
        result = _authenticity_from_mrz(_mrz(valid_score=97))
        assert result["mrz_valid_score"] == 97

    def test_derives_score_when_library_omits_it(self) -> None:
        # 4 of 5 fields valid -> 80
        result = _authenticity_from_mrz(_mrz(valid_score=None, valid_personal_number=False))
        assert result["mrz_valid_score"] == 80

    def test_missing_attributes_degrade_gracefully(self) -> None:
        """An MRZ object from a passporteye version that lacks these
        attributes entirely must not crash the scan."""
        bare = SimpleNamespace()
        result = _authenticity_from_mrz(bare)
        assert result["checksum_failures"] == []
        assert result["mrz_valid_score"] is None
