"""Cross-module tenant-isolation regression suite (issue #266).

Every read query function in amlkit.queries and every write operation in
amlkit.cases.manager takes an explicit org_id. This suite pins the contract
that those arguments are enforced, not merely accepted: data created under one
organization must never surface in, or be mutated through, a call made with
another organizations id.

Additive tests only -- they exercise existing public functions through real
in-memory SQLite databases (no mocks, per repo convention) and change no
application logic. A failure here is a genuine cross-tenant leak.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit import queries  # noqa: E402
from amlkit.cases.manager import (  # noqa: E402
    add_case_note,
    add_ubo,
    onboard,
    record_signature,
    record_transaction,
)
from amlkit.db import connect, set_org_alert_threshold, upsert_dataset, utcnow  # noqa: E402
from amlkit.names.arabic import blocking_keys, canonical_key  # noqa: E402

LISTED = "AHMED ABD AL-JALEEL AL-HASNAWI"


def _make_org(conn, name, slug):
    row = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at)"
        " VALUES (?,?,?,?) RETURNING id",
        (name, slug, "active", utcnow()),
    ).fetchone()
    conn.commit()
    return row["id"]


def _seed_dataset(conn):
    """One fresh mandatory dataset so the onboarding staleness gate passes."""
    ds = upsert_dataset(conn, "test_list", "Synthetic Test List", is_mandatory=True)
    now = utcnow()
    conn.execute("UPDATE datasets SET last_refresh=?, entity_count=1 WHERE id=?", (now, ds))
    countries = "[\"ly\"]"
    topics = "[\"sanction\"]"
    cur = conn.execute(
        "INSERT INTO entities (dataset_id, source_id, schema_type, caption,"
        " countries, birth_date, gender, topics, raw, first_seen, last_seen)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (ds, "SYN-1", "Person", LISTED, countries, "1975-03-12", "male",
         topics, "{}", now, now),
    )
    eid = cur.lastrowid
    conn.execute(
        "INSERT INTO entity_names (entity_id, name, name_type, canonical_key, script)"
        " VALUES (?,?,?,?,?)", (eid, LISTED, "primary", canonical_key(LISTED), "latin"))
    for tok in blocking_keys(LISTED):
        conn.execute("INSERT OR IGNORE INTO name_tokens (token, entity_id) VALUES (?,?)",
                     (tok, eid))
    conn.commit()


@pytest.fixture()
def conn():
    c = connect(":memory:")
    _seed_dataset(c)
    yield c
    c.close()


@pytest.fixture()
def org_a(conn):
    return _make_org(conn, "Firm A", "firm-a")


@pytest.fixture()
def org_b(conn):
    return _make_org(conn, "Firm B", "firm-b")


def _onboard(conn, org_id, ref, name, **kw):
    return onboard(conn, org_id=org_id, reference=ref, full_name=name, **kw)


class TestReadIsolation:
    def test_customer_list_scoped(self, conn, org_a, org_b):
        _onboard(conn, org_a, "A-1", "Alpha Customer")
        _onboard(conn, org_b, "B-1", "Bravo Customer")
        a_names = {c["full_name"] for c in queries.customer_list(conn, org_a)}
        b_names = {c["full_name"] for c in queries.customer_list(conn, org_b)}
        assert a_names == {"Alpha Customer"}
        assert b_names == {"Bravo Customer"}

    def test_customer_detail_cross_tenant_is_404(self, conn, org_a, org_b):
        res = _onboard(conn, org_a, "A-1", "Alpha Customer")
        assert queries.customer(conn, res.customer_id, org_b) is None
        assert queries.customer(conn, res.customer_id, org_a) is not None

    def test_report_cross_tenant_is_404(self, conn, org_a, org_b):
        res = _onboard(conn, org_a, "A-1", "Alpha Customer")
        rid = conn.execute(
            "INSERT INTO reports (org_id, customer_id, report_type, status, payload, created_at)"
            " VALUES (?,?,?,?,?,?) RETURNING id",
            (org_a, res.customer_id, "STR", "draft", "{}", utcnow()),
        ).fetchone()["id"]
        conn.commit()
        assert queries.report(conn, rid, org_b) is None
        assert queries.report(conn, rid, org_a) is not None
        assert rid not in {r["id"] for r in queries.report_list(conn, org_b)}

    def test_transactions_for_customer_scoped(self, conn, org_a, org_b):
        a = _onboard(conn, org_a, "A-1", "Alpha Customer")
        record_transaction(conn, a.customer_id, org_a, direction="in",
                            method="cash", amount=1000.0)
        assert queries.transactions_for_customer(conn, a.customer_id, org_b) == []
        assert len(queries.transactions_for_customer(conn, a.customer_id, org_a)) == 1

    def test_case_notes_scoped(self, conn, org_a, org_b):
        a = _onboard(conn, org_a, "A-1", "Alpha Customer")
        add_case_note(conn, a.customer_id, org_a, author="auditor", body="A note")
        assert queries.case_notes(conn, a.customer_id, org_b) == []
        assert len(queries.case_notes(conn, a.customer_id, org_a)) == 1

    def test_signatures_scoped(self, conn, org_a, org_b):
        a = _onboard(conn, org_a, "A-1", "Alpha Customer")
        record_signature(conn, a.customer_id, org_a, purpose="cdd",
                          statement="I confirm", signer_name="Alpha")
        assert queries.signatures_for_customer(conn, a.customer_id, org_b) == []
        assert len(queries.signatures_for_customer(conn, a.customer_id, org_a)) == 1

    def test_operators_scoped(self, conn, org_a, org_b):
        conn.execute(
            "INSERT INTO operators (org_id, name, email, role, is_active, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (org_a, "A Op", "a@firm-a.test", "operator", 1, utcnow()))
        conn.execute(
            "INSERT INTO operators (org_id, name, email, role, is_active, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (org_b, "B Op", "b@firm-b.test", "operator", 1, utcnow()))
        conn.commit()
        assert {o["email"] for o in queries.operators(conn, org_a)} == {"a@firm-a.test"}
        assert {o["email"] for o in queries.operators(conn, org_b)} == {"b@firm-b.test"}

    def test_customer_counts_scoped(self, conn, org_a, org_b):
        _onboard(conn, org_a, "A-1", "Alpha Customer")
        _onboard(conn, org_a, "A-2", "Alpha Two")
        _onboard(conn, org_b, "B-1", "Bravo Customer")
        assert isinstance(queries.dashboard(conn, org_a), dict)
        assert isinstance(queries.dashboard(conn, org_b), dict)
        assert len(queries.customer_list(conn, org_a)) == 2
        assert len(queries.customer_list(conn, org_b)) == 1

    def test_alert_queue_scoped(self, conn, org_a, org_b):
        _onboard(conn, org_a, "A-1", LISTED)
        assert len(queries.alert_queue(conn, org_a, status=None)) >= 1
        assert queries.alert_queue(conn, org_b, status=None) == []

    def test_audit_trail_does_not_leak_other_tenant(self, conn, org_a, org_b):
        _onboard(conn, org_a, "A-1", "Alpha Customer")
        _onboard(conn, org_b, "B-1", "Bravo Customer")
        joined = " ".join(str(e.get("detail")) for e in queries.audit_trail(conn, org_a))
        assert "Bravo Customer" not in joined

    def test_org_alert_threshold_scoped(self, conn, org_a, org_b):
        set_org_alert_threshold(conn, org_a, 0.91)
        assert queries.org_alert_threshold(conn, org_a) == 0.91
        assert queries.org_alert_threshold(conn, org_b) is None


class TestWriteIsolation:
    def test_add_case_note_rejects_cross_tenant(self, conn, org_a, org_b):
        a = _onboard(conn, org_a, "A-1", "Alpha Customer")
        with pytest.raises(ValueError):
            add_case_note(conn, a.customer_id, org_b, author="intruder", body="leak")
        assert queries.case_notes(conn, a.customer_id, org_a) == []

    def test_record_transaction_rejects_cross_tenant(self, conn, org_a, org_b):
        a = _onboard(conn, org_a, "A-1", "Alpha Customer")
        with pytest.raises(ValueError):
            record_transaction(conn, a.customer_id, org_b, direction="in",
                               method="cash", amount=500.0)
        assert queries.transactions_for_customer(conn, a.customer_id, org_a) == []

    def test_record_signature_rejects_cross_tenant(self, conn, org_a, org_b):
        a = _onboard(conn, org_a, "A-1", "Alpha Customer")
        with pytest.raises(ValueError):
            record_signature(conn, a.customer_id, org_b, purpose="cdd",
                             statement="I confirm", signer_name="Intruder")
        assert queries.signatures_for_customer(conn, a.customer_id, org_a) == []

    def test_add_ubo_rejects_cross_tenant(self, conn, org_a, org_b):
        a = _onboard(conn, org_a, "A-1", "Alpha LLC", customer_type="legal")
        with pytest.raises(ValueError):
            add_ubo(conn, a.customer_id, org_id=org_b, person_name="Intruder UBO",
                    ownership_pct=60.0)
        detail = queries.customer(conn, a.customer_id, org_a)
        assert all(u["person_name"] != "Intruder UBO" for u in detail["ubos"])

    def test_onboard_isolates_identical_references(self, conn, org_a, org_b):
        """Two tenants may reuse one customer reference without collision."""
        a = _onboard(conn, org_a, "SHARED-REF", "Alpha Customer")
        b = _onboard(conn, org_b, "SHARED-REF", "Bravo Customer")
        assert a.customer_id != b.customer_id
        assert queries.customer(conn, a.customer_id, org_a)["customer"]["full_name"] == "Alpha Customer"
        assert queries.customer(conn, b.customer_id, org_b)["customer"]["full_name"] == "Bravo Customer"
