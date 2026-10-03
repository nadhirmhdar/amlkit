"""goAML export: org + transaction data must come from THIS tenant rows.

Kanban #268. test_goaml.py pins the serialiser required-field behaviour at
the unit level; test_report_save_flow.py exercises the save->export path for
a single org. The gap this file closes is the cross-tenant property of the
filed XML itself: when two firms each build a report, each firm exported
goAML XML must carry that firm own reporting entity and its own transaction
figures, never a hardcoded placeholder and never the other tenant data.

Integration tests against real SQLite + the live save/export routes (no DB
mocks), per repo conventions.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_api import _csrf, _register, _seed_sanctions_data  # noqa: E402


def _fresh_client(org_name, name, email):
    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app, cookies={})
    _register(c, org_name, name, email)
    return c


def _onboard(reference, full_name, **overrides) -> int:
    from amlkit.cases.manager import onboard
    from amlkit.db import connect

    conn = connect(os.environ["AMLKIT_DB"])
    org_id = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()["id"]
    kwargs = {"reference": reference, "full_name": full_name,
              "customer_type": "natural", "nationality": "ae"}
    kwargs.update(overrides)
    result = onboard(conn, org_id=org_id, actor="tester", **kwargs)
    conn.close()
    return result.customer_id


def _save_and_export(client, customer_id, form, report_type="STR"):
    r = client.post("/reports", data={
        "customer_id": customer_id, "report_type": report_type,
        "csrf_token": _csrf(client), **form,
    })
    assert r.status_code != 422, r.text

    from amlkit.db import connect
    conn = connect(os.environ["AMLKIT_DB"])
    row = conn.execute(
        "SELECT id FROM reports WHERE customer_id=? ORDER BY id DESC LIMIT 1",
        (customer_id,),
    ).fetchone()
    conn.close()
    assert row is not None, "no report row was saved"
    rid = row["id"]

    resp = client.get(f"/reports/{rid}/export")
    assert resp.status_code == 200, resp.text
    return ET.fromstring(resp.text)


@pytest.fixture()
def single_client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    _seed_sanctions_data(db_file)
    return _fresh_client("Falcon Compliance LLC", "alice", "alice@falcon.ae")


class TestReportingEntityIsTenantSpecific:
    def test_exported_entity_matches_the_submitting_firm(self, single_client) -> None:
        cid = _onboard("C-1", "Ahmed Al Mansoori")
        root = _save_and_export(single_client, cid, {
            "reporting_entity_name": "Falcon Compliance LLC",
            "entity_reference": "FAL-LIC-77",
            "reporter_name": "Alice MLRO", "reporter_email": "alice@falcon.ae",
            "first_name": "Ahmed", "last_name": "Al Mansoori", "nationality": "AE",
        })
        assert root.find("reporting_entity/reporting_entity_name").text == "Falcon Compliance LLC"
        assert root.find("entity_reference").text == "FAL-LIC-77"
        assert root.find("reporting_person/first_name").text == "Alice"
        assert root.find("reporting_person/email").text == "alice@falcon.ae"

    def test_two_firms_get_their_own_entity_not_each_others(self, tmp_path, monkeypatch) -> None:
        db_a = tmp_path / "a.db"
        monkeypatch.setenv("AMLKIT_DB", str(db_a))
        monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
        _seed_sanctions_data(db_a)
        firm_a = _fresh_client("Alpha Advisory FZE", "amal", "amal@alpha.ae")
        cid_a = _onboard("A-1", "Ahmed Al Mansoori")
        root_a = _save_and_export(firm_a, cid_a, {
            "reporting_entity_name": "Alpha Advisory FZE",
            "entity_reference": "ALPHA-LIC-1",
            "reporter_name": "Amal Officer", "reporter_email": "amal@alpha.ae",
            "first_name": "Ahmed", "last_name": "Al Mansoori", "nationality": "AE",
        })

        db_b = tmp_path / "b.db"
        monkeypatch.setenv("AMLKIT_DB", str(db_b))
        _seed_sanctions_data(db_b)
        firm_b = _fresh_client("Beta Partners LLC", "bilal", "bilal@beta.ae")
        cid_b = _onboard("B-1", "Ahmed Al Mansoori")
        root_b = _save_and_export(firm_b, cid_b, {
            "reporting_entity_name": "Beta Partners LLC",
            "entity_reference": "BETA-LIC-9",
            "reporter_name": "Bilal Officer", "reporter_email": "bilal@beta.ae",
            "first_name": "Ahmed", "last_name": "Al Mansoori", "nationality": "AE",
        })

        name_a = root_a.find("reporting_entity/reporting_entity_name").text
        name_b = root_b.find("reporting_entity/reporting_entity_name").text
        assert name_a == "Alpha Advisory FZE"
        assert name_b == "Beta Partners LLC"
        assert name_a != name_b
        assert "Beta Partners" not in ET.tostring(root_a, encoding="unicode")
        assert "Alpha Advisory" not in ET.tostring(root_b, encoding="unicode")


class TestTransactionDataIsFromTheSubmittedReport:
    def test_amount_and_accounts_are_the_submitted_values(self, single_client) -> None:
        cid = _onboard("C-2", "Ahmed Al Mansoori")
        root = _save_and_export(single_client, cid, {
            "reporting_entity_name": "Falcon Compliance LLC",
            "entity_reference": "FAL-LIC-77",
            "reporter_name": "Alice MLRO", "reporter_email": "alice@falcon.ae",
            "first_name": "Ahmed", "last_name": "Al Mansoori", "nationality": "AE",
            "amount": "123456.78", "transaction_type": "Cash Deposit",
            "transaction_date": "2026-02-15",
            "source_institution_name": "Mashreq Bank",
            "source_account": "AE060330000012345678901",
            "destination_institution_name": "First Abu Dhabi Bank",
            "destination_account": "AE980350000098765432109",
        })
        tx = root.find("transaction")
        assert tx is not None
        assert tx.find("amount_local").text == "123456.78"
        assert tx.find("transmode_code").text == "Cash Deposit"
        assert tx.find("date_transaction").text == "2026-02-15"
        assert tx.find("t_from/account/institution_name").text == "Mashreq Bank"
        assert tx.find("t_from/account/account_number").text == "AE060330000012345678901"
        assert tx.find("t_to/account/institution_name").text == "First Abu Dhabi Bank"
        assert tx.find("t_to/account/account_number").text == "AE980350000098765432109"

    def test_submitted_amount_is_not_overridden_by_a_hardcoded_default(self, single_client) -> None:
        cid = _onboard("C-3", "Ahmed Al Mansoori")
        root = _save_and_export(single_client, cid, {
            "reporting_entity_name": "Falcon Compliance LLC",
            "entity_reference": "FAL-LIC-77",
            "reporter_name": "Alice MLRO", "reporter_email": "alice@falcon.ae",
            "first_name": "Ahmed", "nationality": "AE",
            "amount": "500000", "transaction_type": "Wire Transfer",
            "source_institution_name": "Emirates NBD", "source_account": "AE1",
            "destination_institution_name": "ADCB", "destination_account": "AE2",
        })
        assert root.find("transaction/amount_local").text not in ("0.0", "0", None)
        assert float(root.find("transaction/amount_local").text) == 500000.0


class TestSubjectIdentityIsFromTheReport:
    def test_natural_person_subject_is_the_reported_customer(self, single_client) -> None:
        cid = _onboard("C-4", "Khalid Bin Zayed")
        root = _save_and_export(single_client, cid, {
            "reporting_entity_name": "Falcon Compliance LLC",
            "entity_reference": "FAL-LIC-77",
            "reporter_name": "Alice MLRO", "reporter_email": "alice@falcon.ae",
            "first_name": "Khalid", "last_name": "Bin Zayed", "nationality": "AE",
        })
        assert root.find("subject/person/first_name").text == "Khalid"
        assert root.find("subject/person/last_name").text == "Bin Zayed"
