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


class TestCardTransactionAccepted:
    """Card transactions are accepted and evaluated by KYT."""

    def test_card_method_accepted_by_record_transaction(self):
        from amlkit.db import connect, utcnow
        from amlkit.cases.manager import record_transaction, onboard
        conn = connect(":memory:")
        org_id = _create_test_org(conn)
        conn.execute(
            "INSERT INTO datasets (key, title, publisher, is_mandatory, "
            "last_refresh, entity_count, max_age_hours) "
            "VALUES ('test_list', 'Test', 'Test', 1, ?, 1, 24)",
            (utcnow(),),
        )
        conn.commit()
        result = onboard(
            conn, org_id=org_id, reference="CARD-TEST",
            full_name="Card Tester", customer_type="natural",
            actor="test",
        )
        txn_id, triggered = record_transaction(
            conn, result.customer_id, org_id,
            direction="inbound", method="card", amount=500.0,
            actor="test",
        )
        assert txn_id > 0
        row = conn.execute(
            "SELECT method FROM transactions WHERE id=?", (txn_id,)
        ).fetchone()
        assert row["method"] == "card"

    def test_unknown_method_rejected(self):
        from amlkit.db import connect, utcnow
        from amlkit.cases.manager import record_transaction, onboard
        conn = connect(":memory:")
        org_id = _create_test_org(conn)
        conn.execute(
            "INSERT INTO datasets (key, title, publisher, is_mandatory, "
            "last_refresh, entity_count, max_age_hours) "
            "VALUES ('test_list', 'Test', 'Test', 1, ?, 1, 24)",
            (utcnow(),),
        )
        conn.commit()
        result = onboard(
            conn, org_id=org_id, reference="BAD-METHOD",
            full_name="Bad Method", customer_type="natural",
            actor="test",
        )
        with pytest.raises(ValueError, match="method"):
            record_transaction(
                conn, result.customer_id, org_id,
                direction="inbound", method="barter", amount=100.0,
                actor="test",
            )


class TestCivilStatusValidationOnboard:
    """Civil status is validated during onboarding."""

    def test_valid_civil_status_accepted(self):
        from amlkit.db import connect, utcnow
        from amlkit.cases.manager import onboard
        conn = connect(":memory:")
        org_id = _create_test_org(conn)
        conn.execute(
            "INSERT INTO datasets (key, title, publisher, is_mandatory, "
            "last_refresh, entity_count, max_age_hours) "
            "VALUES ('test_list', 'Test', 'Test', 1, ?, 1, 24)",
            (utcnow(),),
        )
        conn.commit()
        result = onboard(
            conn, org_id=org_id, reference="CIVIL-TEST",
            full_name="Civil Tester", customer_type="natural",
            civil_status_code="MARR", occupation="Engineer",
            actor="test",
        )
        row = conn.execute(
            "SELECT civil_status_code, occupation FROM customers WHERE id=?",
            (result.customer_id,),
        ).fetchone()
        assert row["civil_status_code"] == "MARR"
        assert row["occupation"] == "Engineer"

    def test_invalid_civil_status_rejected(self):
        from amlkit.db import connect, utcnow
        from amlkit.cases.manager import onboard
        conn = connect(":memory:")
        org_id = _create_test_org(conn)
        conn.execute(
            "INSERT INTO datasets (key, title, publisher, is_mandatory, "
            "last_refresh, entity_count, max_age_hours) "
            "VALUES ('test_list', 'Test', 'Test', 1, ?, 1, 24)",
            (utcnow(),),
        )
        conn.commit()
        with pytest.raises(ValueError, match="civil_status"):
            onboard(
                conn, org_id=org_id, reference="CIVIL-BAD",
                full_name="Bad Status", customer_type="natural",
                civil_status_code="MARRIED",
                actor="test",
            )

    def test_none_civil_status_accepted(self):
        from amlkit.db import connect, utcnow
        from amlkit.cases.manager import onboard
        conn = connect(":memory:")
        org_id = _create_test_org(conn)
        conn.execute(
            "INSERT INTO datasets (key, title, publisher, is_mandatory, "
            "last_refresh, entity_count, max_age_hours) "
            "VALUES ('test_list', 'Test', 'Test', 1, ?, 1, 24)",
            (utcnow(),),
        )
        conn.commit()
        result = onboard(
            conn, org_id=org_id, reference="CIVIL-NONE",
            full_name="No Status", customer_type="natural",
            actor="test",
        )
        assert result.customer_id > 0


def _create_test_org(conn):
    """Helper: create a minimal org and return its id."""
    cur = conn.execute(
        "INSERT INTO organizations (name, slug, created_at) "
        "VALUES ('Test Org', 'test-org', '2026-01-01')"
    )
    conn.commit()
    return cur.lastrowid
