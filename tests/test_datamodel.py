"""Tests for amlkit/datamodel.py — Google AML AI enum alignment."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.datamodel import (
    CIVIL_STATUS_CODES,
    map_customer_type,
    map_direction,
    map_transaction_method,
    validate_civil_status,
    validate_occupation,
)


class TestMapCustomerType:
    def test_natural_to_consumer(self):
        assert map_customer_type("natural") == "CONSUMER"

    def test_legal_to_company(self):
        assert map_customer_type("legal") == "COMPANY"

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="customer_type"):
            map_customer_type("corporate")

    def test_case_insensitive(self):
        assert map_customer_type("Natural") == "CONSUMER"


class TestMapDirection:
    def test_outbound_to_debit(self):
        assert map_direction("outbound") == "DEBIT"

    def test_inbound_to_credit(self):
        assert map_direction("inbound") == "CREDIT"

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="direction"):
            map_direction("transfer")


class TestMapTransactionMethod:
    def test_wire(self):
        assert map_transaction_method("wire") == "WIRE"

    def test_cash(self):
        assert map_transaction_method("cash") == "CASH"

    def test_cheque(self):
        assert map_transaction_method("cheque") == "CHECK"

    def test_card(self):
        assert map_transaction_method("card") == "CARD"

    def test_crypto(self):
        assert map_transaction_method("crypto") == "CRYPTO"

    def test_other(self):
        assert map_transaction_method("other") == "OTHER"

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="method"):
            map_transaction_method("barter")


class TestCivilStatus:
    def test_valid_codes(self):
        for code in ["SING", "MARR", "DIVR", "WIDW", "SEPR", "UNKNOWN"]:
            validate_civil_status(code)

    def test_none_accepted(self):
        validate_civil_status(None)

    def test_empty_accepted(self):
        validate_civil_status("")

    def test_invalid_rejected(self):
        with pytest.raises(ValueError, match="civil_status"):
            validate_civil_status("MARRIED")


class TestOccupation:
    def test_valid_string_accepted(self):
        validate_occupation("Engineer")

    def test_none_accepted(self):
        validate_occupation(None)

    def test_empty_accepted(self):
        validate_occupation("")

    def test_too_long_rejected(self):
        with pytest.raises(ValueError, match="occupation"):
            validate_occupation("x" * 201)
