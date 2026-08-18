"""Electronic signature (typed-signature acknowledgment) tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases.manager import onboard, record_signature  # noqa: E402
from amlkit.db import connect, utcnow  # noqa: E402


@pytest.fixture()
def conn():
    c = connect(":memory:")
    yield c
    c.close()


@pytest.fixture()
def org_id(conn) -> int:
    row = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)"
        " RETURNING id",
        ("Test Firm", "test-firm-sig", "active", utcnow()),
    ).fetchone()
    conn.commit()
    return row["id"]


@pytest.fixture()
def customer_id(conn, org_id) -> int:
    res = onboard(conn, org_id=org_id, reference="C-SIG-1", full_name="Fatima Al Suwaidi",
                  customer_type="natural", nationality="ae")
    return res.customer_id


class TestRecordSignature:
    def test_records_a_signature(self, conn, org_id, customer_id) -> None:
        sig_id = record_signature(
            conn, customer_id, org_id, purpose="Risk acknowledgment",
            statement="I acknowledge the assigned risk rating.",
            signer_name="Fatima Al Suwaidi", actor="operator@firm.ae",
        )
        row = conn.execute("SELECT * FROM signatures WHERE id=?", (sig_id,)).fetchone()
        assert row["signer_name"] == "Fatima Al Suwaidi"
        assert row["signer_role"] == "customer"
        assert len(row["content_hash"]) == 64  # sha256 hex digest

    def test_rejects_empty_statement(self, conn, org_id, customer_id) -> None:
        with pytest.raises(ValueError):
            record_signature(conn, customer_id, org_id, purpose="x", statement="   ",
                             signer_name="Fatima Al Suwaidi", actor="tester")

    def test_signature_is_audited(self, conn, org_id, customer_id) -> None:
        record_signature(conn, customer_id, org_id, purpose="Risk acknowledgment",
                         statement="I acknowledge.", signer_name="Fatima Al Suwaidi",
                         actor="operator@firm.ae")
        n = conn.execute(
            "SELECT COUNT(*) c FROM audit_log WHERE action='signature.record'"
        ).fetchone()["c"]
        assert n == 1

    def test_cross_org_customer_is_rejected(self, conn, org_id, customer_id) -> None:
        other_org = conn.execute(
            "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)"
            " RETURNING id",
            ("Other Firm", "other-firm-sig", "active", utcnow()),
        ).fetchone()["id"]
        with pytest.raises(ValueError):
            record_signature(conn, customer_id, other_org, purpose="x", statement="y",
                             signer_name="Someone", actor="tester")
        n = conn.execute("SELECT COUNT(*) c FROM signatures").fetchone()["c"]
        assert n == 0


class TestContentHash:
    def test_identical_content_hashes_identically(self, conn, org_id, customer_id) -> None:
        id1 = record_signature(conn, customer_id, org_id, purpose="P", statement="S",
                               signer_name="Same Name", actor="tester")
        id2 = record_signature(conn, customer_id, org_id, purpose="P", statement="S",
                               signer_name="Same Name", actor="tester")
        h1 = conn.execute("SELECT content_hash FROM signatures WHERE id=?", (id1,)).fetchone()[0]
        h2 = conn.execute("SELECT content_hash FROM signatures WHERE id=?", (id2,)).fetchone()[0]
        assert h1 == h2

    def test_different_statement_hashes_differently(self, conn, org_id, customer_id) -> None:
        id1 = record_signature(conn, customer_id, org_id, purpose="P", statement="Original text",
                               signer_name="Same Name", actor="tester")
        id2 = record_signature(conn, customer_id, org_id, purpose="P", statement="Edited text",
                               signer_name="Same Name", actor="tester")
        h1 = conn.execute("SELECT content_hash FROM signatures WHERE id=?", (id1,)).fetchone()[0]
        h2 = conn.execute("SELECT content_hash FROM signatures WHERE id=?", (id2,)).fetchone()[0]
        assert h1 != h2

    def test_field_boundary_does_not_collide(self, conn, org_id, customer_id) -> None:
        """'ab' + 'c' must not hash the same as 'a' + 'bc' -- guards against a
        naive concatenation join in the hash construction."""
        id1 = record_signature(conn, customer_id, org_id, purpose="ab", statement="c",
                               signer_name="Name", actor="tester")
        id2 = record_signature(conn, customer_id, org_id, purpose="a", statement="bc",
                               signer_name="Name", actor="tester")
        h1 = conn.execute("SELECT content_hash FROM signatures WHERE id=?", (id1,)).fetchone()[0]
        h2 = conn.execute("SELECT content_hash FROM signatures WHERE id=?", (id2,)).fetchone()[0]
        assert h1 != h2
