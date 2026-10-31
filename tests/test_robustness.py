"""WP-10 robustness fixes (L-21, L-83, L-22, L-34, L-35, L-36, L-12, L-42, L-56).

Real SQLite and TestClient throughout; each test fails on the pre-fix code.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_report_save_flow import (  # noqa: E402,F401  (client is a pytest fixture)
    NATURAL_PERSON_FORM, _csrf, _customer_id, client,
)
from test_mobile_api import api  # noqa: E402,F401  (pytest fixture)


# ------------------------------------------------------------ paging (L-21, L-83)

class TestPaging:
    @pytest.mark.parametrize("page", ["99999999999999999999", "-1", "0", "abc", "1.5", ""])
    def test_audit_page_never_500s(self, client, page) -> None:
        r = client.get("/audit", params={"page": page})
        assert r.status_code == 200, (page, r.status_code)

    @pytest.mark.parametrize("page", ["99999999999999999999", "-1", "abc"])
    def test_feedback_admin_page_never_500s(self, client, page) -> None:
        r = client.get("/admin/feedback", params={"page": page})
        assert r.status_code == 200, (page, r.status_code)

    def test_negative_page_is_page_one(self, client) -> None:
        assert client.get("/audit", params={"page": "-1"}).status_code == 200
        from amlkit.api.deps import clamp_page
        assert clamp_page(-1) == 1 and clamp_page("x") == 1 and clamp_page(None) == 1
        assert clamp_page("99999999999999999999") == 10_000
        assert clamp_page(7) == 7 and clamp_page(50, max_page=10) == 10

    def test_clamp_offset(self) -> None:
        from amlkit.api.deps import clamp_offset
        assert clamp_offset(-5) == 0 and clamp_offset("x") == 0
        assert clamp_offset(10**30) <= 2**31
        assert clamp_offset("40") == 40

    @pytest.mark.parametrize("offset", ["99999999999999999999", "-3", "abc"])
    def test_mobile_alerts_offset_never_500s(self, api, offset) -> None:
        c, headers = api
        r = c.get("/api/v1/alerts", params={"offset": offset}, headers=headers)
        assert r.status_code == 200, (offset, r.text)
        assert r.json()["offset"] >= 0


# ------------------------------------------------------------ threshold 0.0 (L-22)

class TestThresholdZero:
    def test_stored_zero_reads_as_zero_not_default(self, client) -> None:
        from amlkit import queries
        from amlkit.db import connect, set_org_alert_threshold
        from amlkit.match.engine import DEFAULT_THRESHOLD
        conn = connect(os.environ["AMLKIT_DB"])
        org_id = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()["id"]
        assert queries.org_alert_threshold_or_default(conn, org_id) == DEFAULT_THRESHOLD
        set_org_alert_threshold(conn, org_id, 0.0)  # legacy row; setters now refuse it
        assert queries.org_alert_threshold_or_default(conn, org_id) == 0.0
        set_org_alert_threshold(conn, org_id, None)
        assert queries.org_alert_threshold_or_default(conn, org_id) == DEFAULT_THRESHOLD
        conn.close()

    @pytest.mark.parametrize("value", ["0", "0.0", "0.49", "nan", "1.5"])
    def test_web_setter_rejects_out_of_range(self, client, value) -> None:
        r = client.post("/admin/threshold", data={"threshold": value, "csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert "Threshold must be between 0.5 and 1.0" in r.text
        conn = sqlite3.connect(os.environ["AMLKIT_DB"])
        row = conn.execute("SELECT alert_threshold FROM org_settings").fetchone()
        conn.close()
        assert row is None or row[0] is None

    def test_web_setter_accepts_floor(self, client) -> None:
        client.post("/admin/threshold", data={"threshold": "0.5", "csrf_token": _csrf(client)})
        conn = sqlite3.connect(os.environ["AMLKIT_DB"])
        assert conn.execute("SELECT alert_threshold FROM org_settings").fetchone()[0] == 0.5
        conn.close()

    @pytest.mark.parametrize("value", [0.0, 0.1, 1.2])
    def test_mobile_setter_rejects_out_of_range(self, api, value) -> None:
        c, headers = api
        r = c.post("/api/v1/admin/threshold", json={"threshold": value}, headers=headers)
        assert r.status_code == 400
        assert "0.5" in r.json()["detail"]


# ------------------------------------------------------------ freeze email (L-34)

def _freeze_org(conn, reference_a: str, reference_b: str) -> int:
    from datetime import datetime, timedelta, timezone
    from amlkit import db
    now = db.utcnow()
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
                 ("Org", "org", "active", now))
    org_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        """INSERT INTO operators (org_id, name, email, password_hash, role, is_active,
           failed_login_count, created_at) VALUES (?,?,?,?,?,?,?,?)""",
        (org_id, "MLRO", "mlro@test.com", "hash", "mlro", 1, 0, now))
    old = (datetime.now(timezone.utc) - timedelta(hours=36)).isoformat()
    for ref in (reference_a, reference_b):
        conn.execute(
            """INSERT INTO customers (org_id, reference, full_name, customer_type, canonical_key,
               onboarded_at, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)""",
            (org_id, ref, "Cust " + ref[:3], "natural", "k", now, "active", now, now))
        cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            """INSERT INTO freeze_obligations (org_id, customer_id, obligation_type, risk_category,
               identified_at, identified_by, status) VALUES (?,?,?,?,?,?,?)""",
            (org_id, cid, "sanctions", "high", old, "mlro", "pending_execution"))
    conn.commit()
    return org_id


class TestFreezeEmailHeader:
    def test_header_safe_strips_controls(self) -> None:
        from amlkit.mail import header_safe
        assert header_safe("C-1\r\nBcc: evil@x.test\x00\x0b") == "C-1 Bcc: evil@x.test"
        assert len(header_safe("x" * 500)) == 120

    def test_crlf_reference_does_not_stop_the_batch(self, monkeypatch) -> None:
        from amlkit import db
        from amlkit.cases import manager
        monkeypatch.setenv("AMLKIT_SMTP_HOST", "smtp.invalid")
        monkeypatch.setenv("AMLKIT_SMTP_USE_TLS", "0")
        conn = db.connect(":memory:")
        org_id = _freeze_org(conn, "BAD\r\nBcc: attacker@evil.test", "GOOD-2")
        sent = []
        smtp = MagicMock()
        smtp.__enter__.return_value.send_message.side_effect = lambda m: sent.append(m)
        with patch("amlkit.mail.smtplib.SMTP", return_value=smtp):
            manager.check_unexecuted_freeze_obligations(conn, org_id)  # must not raise
        assert len(sent) == 2, "the obligation after the bad reference must still be alerted"
        for m in sent:
            assert "\n" not in m["Subject"] and "\r" not in m["Subject"]
            assert m["Bcc"] is None
        assert conn.execute(
            "SELECT COUNT(*) FROM freeze_obligations WHERE overdue_notified_at IS NOT NULL"
        ).fetchone()[0] == 2
        conn.close()

    def test_sender_never_raises(self, monkeypatch) -> None:
        from amlkit import mail
        monkeypatch.setenv("AMLKIT_SMTP_HOST", "smtp.invalid")
        with patch("amlkit.mail.smtplib.SMTP", return_value=MagicMock()):
            out = mail.send_freeze_obligation_alert(
                "m@test.com", 1, "A\r\nB", "sanctions", "high")
        assert out == mail.SENT


# ------------------------------------------------------------ goAML control chars (L-35)

class TestGoamlIllegalChars:
    def _create(self, client, **overrides) -> int:
        customer_id = _customer_id(client)
        form = {**NATURAL_PERSON_FORM, **overrides}
        client.post("/reports", data={"customer_id": customer_id, "report_type": "STR",
                                      "csrf_token": _csrf(client), **form})
        conn = sqlite3.connect(os.environ["AMLKIT_DB"])
        rid = conn.execute("SELECT id FROM reports ORDER BY id DESC LIMIT 1").fetchone()[0]
        conn.close()
        return rid

    def test_vertical_tab_is_refused_at_finalise(self, client) -> None:
        rid = self._create(client, reason_description="Wire\x0b inconsistent with income")
        r = client.post(f"/reports/{rid}/submit", data={"csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert "Report finalized" not in r.text
        assert "not allowed in the goAML XML" in r.text
        conn = sqlite3.connect(os.environ["AMLKIT_DB"])
        status = conn.execute("SELECT status FROM reports WHERE id=?", (rid,)).fetchone()[0]
        conn.close()
        assert status == "draft"

    def test_clean_report_still_finalises_and_export_is_well_formed(self, client) -> None:
        import xml.etree.ElementTree as ET
        rid = self._create(client, reason_description="Tab\tand newline\nare fine")
        r = client.post(f"/reports/{rid}/submit", data={"csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert "Report finalized" in r.text
        ET.fromstring(client.get(f"/reports/{rid}/export").content)

    def test_serializer_strips_illegal_characters(self) -> None:
        import xml.etree.ElementTree as ET
        from amlkit.reporting.goaml import find_xml_illegal, serialize_goaml_xml
        assert find_xml_illegal({"a": ["ok", {"b": "x\x00"}], "c": "\ud800"}) == ["a[1].b", "c"]
        payload = {
            "report_type": "STR", "reporting_entity_name": "Firm\x0b", "reporter_name": "A B",
            "reporter_email": "a@b.test", "reason_description": "x\x0cy",
            **{k: v for k, v in NATURAL_PERSON_FORM.items() if k not in ("reporting_entity_name",)},
        }
        payload["reason_description"] = "x\x0cy"
        ET.fromstring(serialize_goaml_xml(payload))


# ------------------------------------------------------------ /system bearer (L-36)

class TestSystemBearer:
    ROUTES = [("/system/refresh", "SCHEDULER_SECRET"),
              ("/system/check-freeze-obligations", "SCHEDULER_SECRET"),
              ("/system/create-operator", "ADMIN_API_SECRET"),
              ("/system/super-admin", "ADMIN_API_SECRET")]

    @pytest.mark.parametrize("path,env", ROUTES)
    def test_non_ascii_bearer_is_401(self, client, monkeypatch, path, env) -> None:
        monkeypatch.setenv(env, "correct-secret")
        r = client.post(path, content=b"{}",
                        headers={"Authorization": "Bearer caf\xe9".encode("latin-1"),
                                 "Content-Type": "application/json"})
        assert r.status_code == 401, (path, r.status_code)

    def test_bearer_ok(self) -> None:
        from amlkit.api.deps import bearer_ok
        assert bearer_ok("Bearer s3", "s3")
        assert not bearer_ok("Bearer s4", "s3")
        assert not bearer_ok("Bearer s\xe9", "s3")
        assert not bearer_ok("", "")


# ------------------------------------------------------------ KYT (L-12)

def _kyt_conn():
    from amlkit import db
    conn = db.connect(":memory:")
    org_id = _freeze_org(conn, "K-1", "K-2")
    cid = conn.execute("SELECT id FROM customers WHERE reference='K-1'").fetchone()[0]
    return conn, org_id, cid


class TestKyt:
    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"), 1e30, 0, -5])
    def test_bad_amount_is_value_error(self, bad) -> None:
        from amlkit.cases.manager import record_transaction
        conn, org_id, cid = _kyt_conn()
        with pytest.raises(ValueError):
            record_transaction(conn, cid, org_id, direction="in", method="cash", amount=bad)
        conn.close()

    def test_nan_amount_is_400_on_mobile(self, api) -> None:
        c, headers = api
        cust = c.post("/api/v1/customers", headers=headers, json={
            "reference": "N-1", "full_name": "Nan Test", "customer_type": "natural",
            "nationality": "ae"})
        assert cust.status_code == 200, cust.text
        cid = cust.json().get("customer_id") or cust.json().get("id")
        r = c.post(f"/api/v1/customers/{cid}/transactions", headers={**headers,
                   "Content-Type": "application/json"},
                   content=b'{"direction":"in","method":"cash","amount":NaN}')
        assert r.status_code in (400, 422), r.text

    def test_nan_amount_does_not_500_on_web(self, client) -> None:
        cid = _customer_id(client)
        r = client.post(f"/customers/{cid}/transactions", data={
            "direction": "in", "method": "cash", "amount": "nan", "csrf_token": _csrf(client)},
            follow_redirects=False)
        assert r.status_code < 500

    def test_aed_amount_aed_mismatch_rejected(self) -> None:
        from amlkit.cases.manager import record_transaction
        conn, org_id, cid = _kyt_conn()
        with pytest.raises(ValueError, match="amount_aed must equal amount"):
            record_transaction(conn, cid, org_id, direction="in", method="cash",
                               amount=100_000, currency="AED", amount_aed=1)
        _, triggered = record_transaction(conn, cid, org_id, direction="in", method="cash",
                                          amount=100_000, currency="AED", amount_aed=100_000)
        assert any(t.rule_key == "large_cash" for t in triggered)
        conn.close()

    def test_out_of_order_structuring_is_detected(self) -> None:
        from amlkit.cases.manager import record_transaction
        results = {}
        for label, days in (("in_order", (0, 5)), ("out_of_order", (5, 0))):
            conn, org_id, cid = _kyt_conn()
            last = []
            for d in days:
                _, last = record_transaction(
                    conn, cid, org_id, direction="in", method="cash", amount=30_000,
                    occurred_at=f"2026-03-{10 + d:02d}T09:00:00+00:00")
            results[label] = [t.rule_key for t in last]
            conn.close()
        assert "structuring" in results["in_order"]
        assert "structuring" in results["out_of_order"]

    def test_outside_window_is_not_structuring(self) -> None:
        from amlkit.cases.manager import record_transaction
        conn, org_id, cid = _kyt_conn()
        for d in (20, 0):
            _, last = record_transaction(
                conn, cid, org_id, direction="in", method="cash", amount=30_000,
                occurred_at=f"2026-03-{1 + d:02d}T09:00:00+00:00")
        assert "structuring" not in [t.rule_key for t in last]
        conn.close()

    def test_config_cache_not_shared_with_a_new_connection(self, tmp_path) -> None:
        from amlkit.db import connect
        from amlkit.screening import kyt
        path = tmp_path / "k.db"
        seen = set()
        for _ in range(50):
            conn = connect(path)
            conn.execute("INSERT OR IGNORE INTO organizations (id,name,slug,status,created_at)"
                         " VALUES (1,'O','o','active','x')")
            conn.commit()
            kyt.get_rule_config(conn, 1)
            kyt.save_rule_config(conn, 1, {"large_cash_threshold_aed": 90_000}, actor="t")
            conn.commit()
            seen.add(kyt.get_rule_config(conn, 1)["large_cash_threshold_aed"])
            conn.execute("UPDATE org_settings SET kyt_large_cash_threshold=70000 WHERE org_id=1")
            conn.commit()
            conn.close()
            conn2 = connect(path)
            seen.add(kyt.get_rule_config(conn2, 1)["large_cash_threshold_aed"])
            conn2.close()
        assert 70_000 in seen and seen <= {90_000, 70_000}

    def test_save_rule_config_rejects_nan(self) -> None:
        from amlkit.screening.kyt import save_rule_config
        conn, org_id, _ = _kyt_conn()
        with pytest.raises(ValueError):
            save_rule_config(conn, org_id, {"large_cash_threshold_aed": float("nan")}, actor="t")
        conn.close()


# ------------------------------------------------------------ test encoding (L-42)

def test_a11y_review_reads_files_as_utf8() -> None:
    src = (Path(__file__).parent / "test_a11y_review.py").read_text(encoding="utf-8")
    import re
    assert not re.search(r"\.read_text\(\s*\)", src), "read_text() without encoding"


# ------------------------------------------------------------ customer search (L-56)

class TestCustomerSearch:
    @pytest.fixture()
    def seeded(self):
        from amlkit import db
        conn = db.connect(":memory:")
        conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES ('O','o','active','x')")
        org_id = conn.execute("SELECT id FROM organizations").fetchone()[0]
        conn.commit()
        for ref, name in (("Q-001", "Ahmad Abd Al-Jaleel"), ("Q-002", "Fatima Hassan")):
            conn.execute(
                """INSERT INTO customers (org_id, reference, full_name, customer_type, canonical_key,
                   onboarded_at, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                (org_id, ref, name, "natural", __import__("amlkit.names.arabic", fromlist=["x"]).canonical_key(name),
                 "x", "active", "x", "x"))
        conn.commit()
        yield conn, org_id
        conn.close()

    @pytest.mark.parametrize("q", ["a" * 2000, "aa", "e" * 50])
    def test_degenerate_queries_return_nothing(self, seeded, q) -> None:
        from amlkit import queries
        conn, org_id = seeded
        assert queries.search_customers(conn, org_id, q) == []

    def test_real_queries_still_match(self, seeded) -> None:
        from amlkit import queries
        conn, org_id = seeded
        assert [c["reference"] for c in queries.search_customers(conn, org_id, "Fatima")] == ["Q-002"]
        assert "Q-001" in [c["reference"] for c in queries.search_customers(conn, org_id, "jaleel")]
        assert len(queries.search_customers(conn, org_id, "")) == 2
