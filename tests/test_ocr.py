"""Passport MRZ authenticity-signal tests, plus Tier 1 IDV additions:
expiry checking, Emirates ID field parsing, and image-quality signal.

Uses a plain object standing in for passporteye's MRZ result rather than a
real passport image -- `_authenticity_from_mrz` only reads attributes off
that object, so a fake with the same attribute names exercises the same
logic without needing image fixtures or a tesseract/passporteye runtime.

The Emirates ID and image-quality tests follow the same principle: they
exercise `_parse_emirates_id_text` (a pure string-in, dict-out function) and
`assess_image_quality` against synthetic PIL images, never the pytesseract-
calling wrappers themselves -- this environment has no tesseract binary
installed, and the module is designed so that isn't required to test the
logic that actually decides what a field means.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases.ocr import (  # noqa: E402
    _authenticity_from_mrz,
    _parse_emirates_id_text,
    _resolve_two_digit_year,
    assess_image_quality,
    check_expiry,
    validate_emirates_id_number,
)


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


class TestResolveTwoDigitYear:
    """Regression coverage for a real bug: the first version of expiry-date
    parsing hardcoded a "20" century prefix, so an already-expired document
    with a last-century MRZ year (e.g. "99" meaning 1999) was silently
    reinterpreted as expiring in 2099 -- the opposite of what expiry
    checking exists to catch. `_resolve_two_digit_year` picks the century
    closest to today instead.

    These specific two-digit years are chosen so the nearer-century answer
    stays correct for decades either side of today, not just on the day
    this was written.
    """

    def test_year_far_in_the_past_resolves_to_last_century(self) -> None:
        # 1999 (~27 years back) is far closer than 2099 (~73 years out) for
        # every year from roughly now through the mid-2040s.
        assert _resolve_two_digit_year("99", "01", "01") == "1999-01-01"

    def test_year_close_to_now_resolves_to_this_century(self) -> None:
        # 2030 is close; 1930 is not, for every year through roughly 2080.
        assert _resolve_two_digit_year("30", "06", "15") == "2030-06-15"

    def test_neither_century_valid_returns_none(self) -> None:
        assert _resolve_two_digit_year("02", "13", "40") is None


class TestCheckExpiry:
    def test_far_future_is_neither_expired_nor_expiring(self) -> None:
        future = (date.today() + timedelta(days=365)).isoformat()
        result = check_expiry(future)
        assert result["expired"] is False
        assert result["expiring_soon"] is False
        assert result["flags"] == []

    def test_within_warn_window_flags_expiring_soon(self) -> None:
        soon = (date.today() + timedelta(days=10)).isoformat()
        result = check_expiry(soon, warn_days=30)
        assert result["expired"] is False
        assert result["expiring_soon"] is True
        assert result["days_until_expiry"] == 10
        assert any("expires in" in f for f in result["flags"])

    def test_past_date_is_expired(self) -> None:
        past = (date.today() - timedelta(days=5)).isoformat()
        result = check_expiry(past)
        assert result["expired"] is True
        assert result["expiring_soon"] is False
        assert any("expired 5 day" in f for f in result["flags"])

    def test_none_input_is_unknown_not_a_crash(self) -> None:
        result = check_expiry(None)
        assert result["expired"] is None
        assert result["expiring_soon"] is None
        assert result["days_until_expiry"] is None
        assert result["flags"] == []

    def test_unparseable_date_is_flagged_not_a_crash(self) -> None:
        result = check_expiry("31/12/2030")
        assert result["expired"] is None
        assert "unparseable" in result["flags"][0]


class TestValidateEmiratesIdNumber:
    def test_well_formed_number_passes_format_check(self) -> None:
        result = validate_emirates_id_number("784-1990-1234567-1")
        assert result["valid_format"] is True
        assert any("check digit not verified" in f for f in result["flags"])

    def test_wrong_shape_fails_format_check(self) -> None:
        result = validate_emirates_id_number("784-99-1234567-1")
        assert result["valid_format"] is False
        assert any("does not match" in f for f in result["flags"])

    def test_implausible_birth_year_fails(self) -> None:
        result = validate_emirates_id_number("784-1850-1234567-1")
        assert result["valid_format"] is False
        assert any("implausible birth year" in f for f in result["flags"])

    def test_none_input_is_flagged_not_a_crash(self) -> None:
        result = validate_emirates_id_number(None)
        assert result["valid_format"] is False
        assert result["flags"] == ["no ID number extracted"]

    def test_checksum_caveat_always_present_even_when_valid(self) -> None:
        """The check-digit algorithm is undocumented -- every result, valid
        or not, must say so rather than implying the digit was verified."""
        result = validate_emirates_id_number("784-1990-1234567-1")
        assert any("not publicly documented" in f for f in result["flags"])


class TestParseEmiratesIdText:
    def test_extracts_id_number_with_dashes(self) -> None:
        result = _parse_emirates_id_text("Name: Ahmed Ali ID Number 784-1990-1234567-1")
        assert result["id_number"] == "784-1990-1234567-1"

    def test_extracts_id_number_with_spaces_instead_of_dashes(self) -> None:
        result = _parse_emirates_id_text("784 1990 1234567 1 Emirates ID")
        assert result["id_number"] == "784-1990-1234567-1"

    def test_no_id_number_in_text_leaves_field_none(self) -> None:
        result = _parse_emirates_id_text("some unrelated OCR noise")
        assert result["id_number"] is None
        assert "id_number" not in result["field_confidence"]

    def test_two_dates_sort_into_birth_and_expiry(self) -> None:
        # DOB 1990, expiry 2028 -- expiry is the later date regardless of
        # which order they appear in the OCR text.
        result = _parse_emirates_id_text("Expiry 15/06/2028 DOB 03/04/1990")
        assert result["birth_date"] == "1990-04-03"
        assert result["expiry_date"] == "2028-06-15"

    def test_single_date_is_treated_as_birth_date_only(self) -> None:
        result = _parse_emirates_id_text("Date of Birth 03/04/1990")
        assert result["birth_date"] == "1990-04-03"
        assert result["expiry_date"] is None

    def test_name_extracted_after_label(self) -> None:
        result = _parse_emirates_id_text("Name: Ahmed Mohammed Al Maktoum ID Number")
        assert result["full_name"] == "Ahmed Mohammed Al Maktoum"

    def test_name_stops_at_multi_word_label_not_just_last_word(self) -> None:
        """Regression: an earlier version only stripped trailing words that
        were themselves exact label words, so "Date of Birth" (label words
        "Date" and "Birth" bracketing the unlabelled connector "of") left
        "... Date of" stuck onto the extracted name instead of cutting at
        the first label word encountered."""
        result = _parse_emirates_id_text(
            "Name: AHMED ALI KHAN Nationality IND Sex M Date of Birth 03/04/1990 "
            "ID Number 784-1990-1234567-1"
        )
        assert result["full_name"] == "AHMED ALI KHAN"

    def test_mean_confidence_attached_to_every_extracted_field(self) -> None:
        result = _parse_emirates_id_text(
            "Name: Ahmed Ali 784-1990-1234567-1 03/04/1990",
            mean_confidence=87.5,
        )
        assert result["field_confidence"]["id_number"] == 87.5
        assert result["field_confidence"]["full_name"] == 87.5
        assert result["field_confidence"]["birth_date"] == 87.5

    def test_id_type_is_always_emirates_id(self) -> None:
        result = _parse_emirates_id_text("")
        assert result["id_type"] == "emirates_id"

    def test_no_mrz_means_authenticity_is_none(self) -> None:
        """Emirates ID cards carry no MRZ -- unlike the passport path, there
        is never a checksum-based authenticity signal to report."""
        result = _parse_emirates_id_text("784-1990-1234567-1")
        assert result["authenticity"] is None

    def test_embeds_expiry_check_and_id_validation(self) -> None:
        result = _parse_emirates_id_text("784-1990-1234567-1 03/04/1990")
        assert "expiry_check" in result
        assert "id_validation" in result
        assert result["id_validation"]["valid_format"] is True


class TestAssessImageQuality:
    def test_small_image_flagged_low_resolution(self) -> None:
        img = Image.new("RGB", (200, 150), color=(120, 120, 120))
        result = assess_image_quality(img)
        assert any("low resolution" in f for f in result["flags"])

    def test_large_image_not_flagged_low_resolution(self) -> None:
        img = Image.new("RGB", (1200, 900), color=(120, 120, 120))
        result = assess_image_quality(img)
        assert not any("low resolution" in f for f in result["flags"])

    def test_reports_dimensions(self) -> None:
        img = Image.new("RGB", (800, 600), color="white")
        result = assess_image_quality(img)
        assert result["width"] == 800
        assert result["height"] == 600

    def test_plain_solid_image_does_not_crash_and_has_low_ela_error(self) -> None:
        # A flat, single-color image is the easiest case for a JPEG
        # re-encode to reproduce near-exactly, so this exercises the ELA
        # path without needing a real scanned document fixture.
        img = Image.new("RGB", (800, 600), color=(200, 100, 50))
        result = assess_image_quality(img)
        assert isinstance(result["max_ela_error"], int)
        assert not any("re-compression" in f for f in result["flags"])


# ---------------------------------------------------------------------------
# Trade licence (legal-person onboarding) field parsing.
#
# UAE trade licences have no MRZ and no fixed template -- unlike Emirates ID
# (a single national format), there are 40+ issuing authorities (mainland
# DED per emirate, dozens of free zones) each with their own layout. So, like
# the Emirates ID path, this is regex-against-free-text with a shared
# `field_confidence`, and it is materially weaker than the passport MRZ path:
# see `_parse_trade_licence_text`'s docstring.
# ---------------------------------------------------------------------------

from amlkit.cases.ocr import _parse_trade_licence_text  # noqa: E402


def test_trade_licence_extracts_mainland_ded_fields():
    text = (
        "GOVERNMENT OF DUBAI\nDEPARTMENT OF ECONOMY AND TOURISM\nTRADE LICENSE\n"
        "License Number : 749278\n"
        "Trade Name : FALCON RIDGE TRADING FZE\n"
        "Legal Type : Free Zone Establishment\n"
        "Issue Date : 12/01/2023\n"
        "Expiry Date : 11/01/2025\n"
    )
    r = _parse_trade_licence_text(text, mean_confidence=91.0)
    assert r["id_number"] == "749278"
    assert r["full_name"] == "FALCON RIDGE TRADING FZE"
    assert r["legal_type"] == "Free Zone Establishment"
    assert r["issue_date"] == "2023-01-12"
    assert r["expiry_date"] == "2025-01-11"
    assert r["issuing_authority"] == "Dubai Department of Economy and Tourism"
    assert r["id_type"] == "trade_licence"
    assert r["field_confidence"]["id_number"] == 91.0


def test_trade_licence_extracts_free_zone_fields_and_authority():
    text = (
        "DMCC\nDUBAI MULTI COMMODITIES CENTRE\n"
        "Licence No: DMCC123456\n"
        "Company Name: SILVER PEAK COMMODITIES DMCC\n"
        "Legal Form: Branch of a Foreign Company\n"
        "Date of Issue: 05-03-2022\n"
        "Date of Expiry: 04-03-2024\n"
    )
    r = _parse_trade_licence_text(text, mean_confidence=88.0)
    assert r["id_number"] == "DMCC123456"
    assert r["full_name"] == "SILVER PEAK COMMODITIES DMCC"
    assert r["legal_type"] == "Branch of a Foreign Company"
    assert r["issue_date"] == "2022-03-05"
    assert r["expiry_date"] == "2024-03-04"
    assert r["issuing_authority"] == "Dubai Multi Commodities Centre (DMCC)"


def test_trade_licence_legal_type_falls_back_to_name_suffix_when_unlabelled():
    text = "Trade Name : HARBOURVIEW BROKERS LLC\nLicense No : 55021\n"
    r = _parse_trade_licence_text(text)
    assert r["full_name"] == "HARBOURVIEW BROKERS LLC"
    assert r["legal_type"] == "LLC"


def test_trade_licence_never_guesses_an_unlabelled_number():
    """No safe universal pattern exists (unlike Emirates ID's fixed prefix),
    so a bare number never becomes id_number without an explicit label --
    guessing wrong here would misfile a customer's licence number."""
    text = "Some certificate mentions 749278 in passing, no label at all."
    r = _parse_trade_licence_text(text)
    assert r["id_number"] is None


def test_trade_licence_missing_fields_degrade_to_none_not_crash():
    r = _parse_trade_licence_text("completely illegible garbage !!! ###")
    assert r["id_number"] is None
    assert r["full_name"] is None
    assert r["legal_type"] is None
    assert r["issue_date"] is None
    assert r["expiry_date"] is None
    assert r["issuing_authority"] is None
    assert r["expiry_check"]["expired"] is None  # check_expiry(None) contract


def test_trade_licence_expiry_check_flags_an_expired_licence():
    text = (
        "License Number: 1\nTrade Name: OLD CO LLC\n"
        "Issue Date: 01/01/2018\nExpiry Date: 01/01/2020\n"
    )
    r = _parse_trade_licence_text(text)
    assert r["expiry_date"] == "2020-01-01"
    assert r["expiry_check"]["expired"] is True
