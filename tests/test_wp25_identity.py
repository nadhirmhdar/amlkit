"""WP-25: identity and auth residuals.

C1  one UAE PASS identity verified for two customers raises a review alert
S1  UAE PASS SSO does not bypass the password lock
N8  four-eyes has no name-comparison fallback; backfill script for legacy rows
UL1 lockout without SMTP tells the operator, and /admin shows a badge
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from conftest import register_org  # noqa: E402
from test_api import _csrf, _db  # noqa: E402
from test_uaepass import (  # noqa: E402,F401
    _SAMPLE_USERINFO, _create_officer, _extract_state, _mock_uaepass_exchange, client,
)


# ------------------------------------------------------------------ C1
def _make_customer(c, ref: str, name: str) -> int:
    c.post("/customers", data={"reference": ref, "full_name": name,
                               "customer_type": "natural", "csrf_token": _csrf(c)},
           follow_redirects=True)
    conn = _db()
    cid = conn.execute("SELECT id FROM customers WHERE reference=?", (ref,)).fetchone()["id"]
    conn.close()
    return cid


def _verify(c, monkeypatch, cid: int, name: str, **over):
    _mock_uaepass_exchange(monkeypatch, userinfo={**_SAMPLE_USERINFO, "fullnameEN": name, **over})
    start = c.get(f"/customers/{cid}/uaepass/start", follow_redirects=False)
    state = _extract_state(start.headers["location"])
    return c.get(f"/customers/{cid}/uaepass/callback?code=x&state={state}", follow_redirects=True)


class TestIdentityReuse:
    def test_second_customer_with_same_idn_gets_a_review_alert(self, client, monkeypatch):
        a = _make_customer(client, "IR-A", "Ram Abc")
        b = _make_customer(client, "IR-B", "Ram Abc")
        ra = _verify(client, monkeypatch, a, "Ram Abc")
        assert "verified via uae pass" in ra.text.lower()
        rb = _verify(client, monkeypatch, b, "Ram Abc")
        assert "already verified for another customer" in rb.text

        conn = _db()
        assert conn.execute("SELECT COUNT(*) FROM uaepass_verifications").fetchone()[0] == 2
        alerts = conn.execute("SELECT * FROM identity_reuse_alerts").fetchall()
        assert len(alerts) == 1
        al = alerts[0]
        assert (al["customer_id"], al["other_customer_id"], al["reason"], al["status"]) == \
            (b, a, "identity_reuse", "open")
        assert json.loads(al["detail"])["other_customer_id"] == a
        assert _SAMPLE_USERINFO["idn"] not in al["detail"]
        # nothing poured into the second customer's file
        assert conn.execute("SELECT id_number FROM customers WHERE id=?", (b,)).fetchone()[0] is None
        assert conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action='customer.identity_reuse_alert'"
        ).fetchone()[0] == 1
        conn.close()

        page = client.get(f"/customers/{b}")
        assert "data-identity-reuse" in page.text and "IR-A" in page.text
        # the first customer is not flagged
        assert "data-identity-reuse" not in client.get(f"/customers/{a}").text

    def test_name_mismatch_flag_and_reuse_notice_both_render(self, client, monkeypatch):
        a = _make_customer(client, "IR-A2", "Ram Abc")
        b = _make_customer(client, "IR-B2", "Somebody Different")
        _verify(client, monkeypatch, a, "Ram Abc")
        _verify(client, monkeypatch, b, "Ram Abc")
        page = client.get(f"/customers/{b}").text
        assert "does not match the customer file" in page
        assert "data-identity-reuse" in page

    def test_reverifying_same_customer_or_repeat_does_not_duplicate(self, client, monkeypatch):
        a = _make_customer(client, "IR-A3", "Ram Abc")
        b = _make_customer(client, "IR-B3", "Ram Abc")
        _verify(client, monkeypatch, a, "Ram Abc")
        _verify(client, monkeypatch, a, "Ram Abc")  # same customer again: no alert
        conn = _db()
        assert conn.execute("SELECT COUNT(*) FROM identity_reuse_alerts").fetchone()[0] == 0
        conn.close()
        _verify(client, monkeypatch, b, "Ram Abc")
        _verify(client, monkeypatch, b, "Ram Abc")
        conn = _db()
        assert conn.execute("SELECT COUNT(*) FROM identity_reuse_alerts").fetchone()[0] == 1
        conn.close()

    def test_idn_used_in_another_org_is_neither_visible_nor_alerted(self, client, monkeypatch):
        from fastapi.testclient import TestClient
        from amlkit.api.app import app

        a = _make_customer(client, "IR-A4", "Ram Abc")
        _verify(client, monkeypatch, a, "Ram Abc")

        other = TestClient(app)
        register_org(other, "Second Firm", "sara", "sara@secondfirm.ae")
        b = _make_customer(other, "IR-B4", "Ram Abc")
        r = _verify(other, monkeypatch, b, "Ram Abc")
        assert "verified via uae pass" in r.text.lower()
        assert "data-identity-reuse" not in other.get(f"/customers/{b}").text
        conn = _db()
        assert conn.execute("SELECT COUNT(*) FROM identity_reuse_alerts").fetchone()[0] == 0
        conn.close()


# ------------------------------------------------------------------ S1
class TestSsoRespectsPasswordLock:
    def _prelink(self):
        conn = _db()
        conn.execute("UPDATE operators SET uaepass_uuid=? WHERE email=?",
                     ("uuid-omar-lock", "omar@testfirm.ae"))
        conn.commit()
        conn.close()

    def _sso(self, client, monkeypatch):
        _mock_uaepass_exchange(monkeypatch, userinfo={**_SAMPLE_USERINFO, "uuid": "uuid-omar-lock"})
        start = client.get("/auth/uaepass/start", follow_redirects=False)
        state = _extract_state(start.headers["location"])
        return client.get(f"/auth/uaepass/callback?code=x&state={state}", follow_redirects=False)

    def test_locked_operator_gets_no_session(self, client, monkeypatch):
        _create_officer(client, "omar", "omar@testfirm.ae")
        self._prelink()
        future = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat(timespec="seconds")
        conn = _db()
        conn.execute("UPDATE operators SET locked_until=?, failed_login_count=8 WHERE email=?",
                     (future, "omar@testfirm.ae"))
        conn.commit()
        conn.close()
        client.cookies.clear()

        r = self._sso(client, monkeypatch)
        assert r.status_code == 303 and r.headers["location"].startswith("/login")
        assert "amlkit_session" not in r.cookies
        assert "Incorrect email or password." in client.get("/login").text
        conn = _db()
        assert conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action='operator.sso_refused_locked'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action='operator.login'"
            " AND detail LIKE '%uaepass%'").fetchone()[0] == 0
        conn.close()

    def test_expired_lock_does_not_block_sso(self, client, monkeypatch):
        _create_officer(client, "omar", "omar@testfirm.ae")
        self._prelink()
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(timespec="seconds")
        conn = _db()
        conn.execute("UPDATE operators SET locked_until=? WHERE email=?", (past, "omar@testfirm.ae"))
        conn.commit()
        conn.close()
        client.cookies.clear()
        r = self._sso(client, monkeypatch)
        assert r.headers["location"] == "/" and "amlkit_session" in r.cookies


# ------------------------------------------------------------------ N8
def _legacy_setup():
    from tests.test_issue_167_foureyes_double_disposition import _create_test_db
    conn, org_id, alert_id = _create_test_db()
    return conn, org_id, alert_id


def _add_op(conn, org_id, name, email):
    cur = conn.execute(
        "INSERT INTO operators (org_id, name, email, role, is_active, created_at)"
        " VALUES (?,?,?,?,1,?)", (org_id, name, email, "mlro", "2026-01-01T00:00:00+00:00"))
    conn.commit()
    return cur.lastrowid


class TestFourEyesNoNameFallback:
    def test_renamed_officer_cannot_confirm_legacy_own_proposal_by_name_trick(self):
        """Before: a NULL-operator_id proposal compared names, so a confirmer using
        the same display name was refused but a renamed proposer was waved through.
        Now the proposer cannot be inferred: a confirm without an id is refused."""
        from amlkit.cases.review import ReviewError, confirm_disposition, propose_disposition
        conn, org_id, alert_id = _legacy_setup()
        propose_disposition(conn, alert_id, org_id=org_id, status="false_positive",
                            reason_code="different_dob", operator="Old Name")
        with pytest.raises(ReviewError, match="operator id is required"):
            confirm_disposition(conn, alert_id, org_id=org_id, operator="New Name", agree=True)

    def test_legacy_proposal_confirmed_by_any_operator_id(self):
        from amlkit.cases.review import confirm_disposition, propose_disposition
        conn, org_id, alert_id = _legacy_setup()
        propose_disposition(conn, alert_id, org_id=org_id, status="false_positive",
                            reason_code="different_dob", operator="Old Name")
        out = confirm_disposition(conn, alert_id, org_id=org_id, operator="Old Name",
                                  operator_id=5, agree=True)
        assert out.status == "false_positive"

    def test_no_legacy_warning_logged(self, caplog):
        import logging
        from amlkit.cases.review import confirm_disposition, propose_disposition
        conn, org_id, alert_id = _legacy_setup()
        propose_disposition(conn, alert_id, org_id=org_id, status="false_positive",
                            reason_code="different_dob", operator="x")
        with caplog.at_level(logging.WARNING, logger="amlkit.cases.review"):
            confirm_disposition(conn, alert_id, org_id=org_id, operator="y", operator_id=3, agree=True)
        assert "legacy name comparison" not in caplog.text

    def test_same_id_still_refused(self):
        from amlkit.cases.review import ReviewError, confirm_disposition, propose_disposition
        conn, org_id, alert_id = _legacy_setup()
        propose_disposition(conn, alert_id, org_id=org_id, status="false_positive",
                            reason_code="different_dob", operator="a", operator_id=1)
        with pytest.raises(ReviewError, match="different operator"):
            confirm_disposition(conn, alert_id, org_id=org_id, operator="b", operator_id=1, agree=True)


class TestBackfillProposalOperator:
    def test_dry_run_then_apply_fills_unique_actor(self, capsys):
        import backfill_proposal_operator as bf
        from amlkit.cases.review import propose_disposition
        conn, org_id, alert_id = _legacy_setup()
        oid = _add_op(conn, org_id, "Uma Unique", "uma@x.ae")
        propose_disposition(conn, alert_id, org_id=org_id, status="false_positive",
                            reason_code="different_dob", operator="Uma Unique")
        fill, amb = bf.plan(conn)
        assert [f["operator_id"] for f in fill] == [oid] and amb == []
        # dry run writes nothing
        assert conn.execute("SELECT operator_id FROM alert_reviews").fetchone()[0] is None
        assert bf.apply(conn, fill) == 1
        assert conn.execute("SELECT operator_id FROM alert_reviews").fetchone()[0] == oid
        assert bf.plan(conn) == ([], [])

    def test_two_propose_events_are_ambiguous_and_left_null(self):
        import backfill_proposal_operator as bf
        from amlkit.cases.review import propose_disposition
        from amlkit.db import audit
        conn, org_id, alert_id = _legacy_setup()
        _add_op(conn, org_id, "Ann", "ann@x.ae")
        _add_op(conn, org_id, "Bob", "bob@x.ae")
        propose_disposition(conn, alert_id, org_id=org_id, status="false_positive",
                            reason_code="different_dob", operator="Ann")
        audit(conn, "Bob", "alert.propose", "alert", alert_id, {}, org_id=org_id)
        conn.commit()
        fill, amb = bf.plan(conn)
        assert fill == [] and len(amb) == 1 and "2 matching audit" in amb[0]["reason"]
        assert bf.apply(conn, fill) == 0
        assert conn.execute("SELECT operator_id FROM alert_reviews").fetchone()[0] is None

    def test_unknown_actor_left_null(self):
        import backfill_proposal_operator as bf
        from amlkit.cases.review import propose_disposition
        conn, org_id, alert_id = _legacy_setup()
        propose_disposition(conn, alert_id, org_id=org_id, status="false_positive",
                            reason_code="different_dob", operator="Renamed Away")
        fill, amb = bf.plan(conn)
        assert fill == [] and len(amb) == 1

    def test_does_not_match_operator_of_another_org(self):
        import backfill_proposal_operator as bf
        from amlkit.cases.review import propose_disposition
        conn, org_id, alert_id = _legacy_setup()
        other = conn.execute(
            "INSERT INTO organizations (name, slug, status, created_at) VALUES ('O2','o2','active','2026-01-01')"
        ).lastrowid
        _add_op(conn, other, "Elsewhere", "e@y.ae")
        propose_disposition(conn, alert_id, org_id=org_id, status="false_positive",
                            reason_code="different_dob", operator="Elsewhere")
        fill, amb = bf.plan(conn)
        assert fill == [] and len(amb) == 1

    def test_main_defaults_to_dry_run_and_apply_writes(self, monkeypatch, capsys):
        import backfill_proposal_operator as bf
        from amlkit.cases.review import propose_disposition
        conn, org_id, alert_id = _legacy_setup()
        oid = _add_op(conn, org_id, "Uma", "uma@x.ae")
        propose_disposition(conn, alert_id, org_id=org_id, status="false_positive",
                            reason_code="different_dob", operator="Uma")
        monkeypatch.setattr(bf, "connect", lambda: conn)
        assert bf.main([]) == 0
        assert "DRY RUN" in capsys.readouterr().out
        assert conn.execute("SELECT operator_id FROM alert_reviews").fetchone()[0] is None
        assert bf.main(["--apply"]) == 0
        assert conn.execute("SELECT operator_id FROM alert_reviews").fetchone()[0] == oid


# ------------------------------------------------------------------ UL1
class TestUnlockMailNotDeliverable:
    def _verified_operator(self, client):
        conn = _db()
        conn.execute("UPDATE operators SET email_verified_at='2026-01-01T00:00:00+00:00'")
        conn.commit()
        conn.close()

    def test_lock_message_when_smtp_missing(self, client, monkeypatch):
        monkeypatch.delenv("AMLKIT_SMTP_HOST", raising=False)
        from amlkit import auth
        conn = _db()
        for _ in range(auth.MAX_FAILED_LOGINS - 1):
            with pytest.raises(auth.AuthError):
                auth.login(conn, "alice@testfirm.ae", "wrong-password-x")
        with pytest.raises(auth.AuthLockedMailUndeliverable) as ei:
            auth.login(conn, "alice@testfirm.ae", "wrong-password-x")
        conn.close()
        assert "could not be sent" in str(ei.value) and "other MLRO" in str(ei.value)

    def test_login_page_shows_message_on_locking_attempt(self, client, monkeypatch):
        monkeypatch.delenv("AMLKIT_SMTP_HOST", raising=False)
        from amlkit import auth
        conn = _db()
        for _ in range(auth.MAX_FAILED_LOGINS - 1):
            with pytest.raises(auth.AuthError):
                auth.login(conn, "alice@testfirm.ae", "wrong-password-x")
        conn.close()
        client.cookies.clear()
        client.get("/login")
        r = client.post("/login", data={"email": "alice@testfirm.ae", "password": "wrong-password-x",
                                        "csrf_token": _csrf(client)})
        assert "could not be sent" in r.text and "other MLRO" in r.text

    def test_generic_message_when_smtp_configured(self, client, monkeypatch):
        monkeypatch.setenv("AMLKIT_SMTP_HOST", "smtp.invalid")
        from amlkit import auth, mail
        monkeypatch.setattr(mail, "send_unlock_email", lambda *a, **k: mail.SENT)
        conn = _db()
        for _ in range(auth.MAX_FAILED_LOGINS - 1):
            with pytest.raises(auth.AuthError):
                auth.login(conn, "alice@testfirm.ae", "wrong-password-x")
        with pytest.raises(auth.AuthError) as ei:
            auth.login(conn, "alice@testfirm.ae", "wrong-password-x")
        conn.close()
        assert not isinstance(ei.value, auth.AuthLockedMailUndeliverable)
        assert str(ei.value) == "Incorrect email or password."

    def test_admin_badge_only_when_mail_not_configured(self, client, monkeypatch):
        _create_officer(client, "omar", "omar@testfirm.ae")
        future = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat(timespec="seconds")
        conn = _db()
        conn.execute("UPDATE operators SET locked_until=? WHERE email=?", (future, "omar@testfirm.ae"))
        conn.commit()
        conn.close()
        monkeypatch.delenv("AMLKIT_SMTP_HOST", raising=False)
        assert "unlock mail not deliverable" in client.get("/admin").text
        monkeypatch.setenv("AMLKIT_SMTP_HOST", "smtp.invalid")
        page = client.get("/admin").text
        assert "Sign-in locked" in page and "unlock mail not deliverable" not in page

