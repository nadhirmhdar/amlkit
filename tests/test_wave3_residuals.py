"""Wave-3 residuals: L-100 (safe_equals), L-102 (dataset-aware freeze wording),
L-105 (periodic-review errors), L-81 residual (evicted-session notice),
L-106 (Stripe event ordering)."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_api import _csrf, _db, _login, _register, client  # noqa: E402,F401
from test_mobile_api import api  # noqa: E402,F401
from test_periodic_review import NOTE, _web_customer  # noqa: E402

from amlkit import auth  # noqa: E402

ARABIC_INDIC = "١٢٣٤٥٦"


# ------------------------------------------------------------------ L-100
class TestSafeEquals:
    def test_matches_and_mismatches(self):
        assert auth.safe_equals("abc", "abc")
        assert auth.safe_equals(b"abc", "abc")
        assert not auth.safe_equals("abc", "abd")

    @pytest.mark.parametrize("a,b", [(None, "x"), ("x", None), (None, None),
                                     ("abé", "abc"), ("abé", "abé "), (ARABIC_INDIC, "123456")])
    def test_never_raises(self, a, b):
        assert auth.safe_equals(a, b) is False

    def test_identical_non_ascii_is_equal(self):
        assert auth.safe_equals("é", "é")

    def test_csrf_valid_non_ascii(self):
        assert auth.csrf_valid("abc", "abé") is False
        assert auth.csrf_valid("abé", "abc") is False

    def test_compare_digest_only_on_bytes(self):
        root = Path(__file__).resolve().parent.parent / "amlkit"
        for f in ("auth.py", "billing/stripe_client.py"):
            for line in (root / f).read_text().splitlines():
                if "compare_digest(" in line and "def " not in line and not line.lstrip().startswith("#"):
                    assert "encode" in line or "compare_digest(a, b)" in line, line

    def test_stripe_signature_non_ascii_is_signature_error(self):
        from amlkit.billing import stripe_client
        with pytest.raises(stripe_client.SignatureError):
            stripe_client.verify_webhook_signature(b"{}", "t=100,v1=é", "whsec_x", now=100)


def test_csrf_non_ascii_form_token_is_403(client):
    client.get("/login")
    r = client.post("/logout", data={"csrf_token": "tökén-é"}, follow_redirects=False)
    assert r.status_code in (303, 403)  # a refusal, never a 500


def test_csrf_non_ascii_on_a_real_form_post(client):
    cid = _web_customer()
    client.get(f"/customers/{cid}")
    r = client.post(f"/customers/{cid}/periodic-review",
                    data={"outcome": "no_change", "note": NOTE, "csrf_token": "tökén-é"},
                    follow_redirects=False)
    assert r.status_code < 500
    c = sqlite3.connect(os.environ["AMLKIT_DB"])
    assert c.execute("SELECT COUNT(*) FROM periodic_reviews").fetchone()[0] == 0


def test_mfa_verify_non_ascii_code_is_refused_not_500(client):
    client.post("/logout", data={"csrf_token": _csrf(client)})
    client.get("/login")
    client.post("/login", data={"email": "alice@testfirm.ae", "password": "A-strong-password-1",
                                "csrf_token": _csrf(client)}, follow_redirects=False)
    r = client.post("/mfa/verify", data={"code": ARABIC_INDIC, "csrf_token": _csrf(client)},
                    follow_redirects=False)
    assert r.status_code == 303, r.text[:200]
    assert r.headers["location"] != "/"  # not signed in
    # and the dashboard stays locked
    assert client.get("/dashboard", follow_redirects=False).status_code in (303, 307)


def test_mfa_verify_function_non_ascii_code_false():
    from amlkit.db import connect, utcnow
    import pyotp
    conn = connect(":memory:")
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES ('O','o','active',?)",
                 (utcnow(),))
    conn.execute("INSERT INTO operators (org_id,name,email,password_hash,role,is_active,created_at,"
                 "email_verified_at) VALUES (1,'A','a@o.ae','h','mlro',1,?,?)", (utcnow(), utcnow()))
    conn.commit()
    auth.mfa_enroll(conn, 1)
    assert auth.mfa_verify(conn, 1, ARABIC_INDIC, confirmed_only=False) is False
    secret = conn.execute("SELECT secret FROM mfa_secrets WHERE operator_id=1").fetchone()["secret"]
    assert auth.mfa_verify(conn, 1, pyotp.TOTP(secret).now(), confirmed_only=False) is True


def test_webhook_non_ascii_signature_is_400(client, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_x")
    payload = b"{}"
    r = client.post("/billing/webhook", content=payload,
                    headers={"Stripe-Signature": f"t={int(time.time())},v1=é".encode("utf-8"),
                             "Content-Type": "application/json"})
    assert r.status_code == 400


# ------------------------------------------------------------------ L-102
class TestFreezeWordingByList:
    def test_ofac_eu_uk_sanction_has_no_freeze_wording(self):
        from amlkit.screening.pf import NON_UAE_SANCTIONS_OBLIGATION, obligation_note
        for ds in ("us_ofac_sdn", "eu_fsf", "gb_hmt_sanctions"):
            note = obligation_note({"sanction"}, ds)
            assert note == NON_UAE_SANCTIONS_OBLIGATION
            assert "freeze without delay" not in note.lower()
            assert "STR/SAR" in note and "no UAE freeze obligation" in note

    @pytest.mark.parametrize("ds", ["un_consolidated", "un_sc_sanctions", "ae_local_terrorists",
                                    "eocn_local_list"])
    def test_un_and_uae_local_keep_freeze_wording(self, ds):
        from amlkit.screening.pf import obligation_note
        assert "Freeze without delay" in obligation_note({"sanction"}, ds)

    def test_hit_obligation_uses_its_dataset(self):
        from amlkit.match.engine import Hit
        base = dict(entity_id=1, caption="c", schema_type="Person", score=0.9,
                    matched_name="n", detail={}, topics=["sanction"], programs=[])
        assert "Freeze without delay" not in Hit(dataset="us_ofac_sdn", **base).obligation
        assert "Freeze without delay" in Hit(dataset="un_consolidated", **base).obligation

    def test_onboarding_banner_ofac_vs_un(self, client):
        from amlkit.cases.manager import OnboardingResult
        from amlkit.match.engine import Hit, ScreeningResult

        def result(ds):
            h = Hit(entity_id=1, dataset=ds, caption="c", schema_type="Person", score=1.0,
                    matched_name="n", topics=["sanction"], detail={}, programs=[])
            sr = ScreeningResult(query="n", trigger="onboarding", threshold=0.8, candidates=1, hits=[h])
            return OnboardingResult(customer_id=1, reference="R", screening=sr, ubo_screenings=[],
                                    risk=None, blocked=True)
        assert result("un_consolidated").freeze_required is True
        assert result("us_ofac_sdn").freeze_required is False

    def test_onboarding_page_banner_for_non_uae_list(self, client):
        # The seeded "test_list" is not a UN / UAE-local dataset.
        from test_api import LISTED
        r = client.post("/customers", data={
            "reference": "BN-1", "full_name": LISTED, "customer_type": "natural",
            "csrf_token": _csrf(client)}, follow_redirects=True)
        assert "MATCH FOUND" in r.text
        assert "freeze without delay" not in r.text
        assert "no UAE freeze obligation" in r.text


# ------------------------------------------------------------------ L-105
class TestPeriodicReviewErrors:
    def test_web_bad_note_shows_page_with_error(self, client):
        cid = _web_customer()
        client.get(f"/customers/{cid}")
        r = client.post(f"/customers/{cid}/periodic-review",
                        data={"outcome": "no_change", "note": "x", "csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert r.status_code == 200
        assert "review note of at least" in r.text
        assert "Customer" in r.text and '"detail"' not in r.text

    def test_mobile_bad_note_is_json_error(self, api):
        c, h = api
        cid = _web_customer()
        r = c.post(f"/api/v1/customers/{cid}/periodic-review", headers=h,
                   json={"outcome": "no_change", "note": "x"})
        assert r.status_code == 400
        assert "review note" in r.json()["error"]


# ------------------------------------------------------------------ L-81
def test_evicted_session_sees_the_limit_notice_on_login(client, monkeypatch):
    monkeypatch.setenv("MAX_CONCURRENT_SESSIONS", "1")
    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    other = TestClient(app)
    other.get("/login")
    r = other.post("/login", data={"email": "alice@testfirm.ae", "password": "A-strong-password-1",
                                   "csrf_token": other.cookies.get("amlkit_csrf")},
                   follow_redirects=False)
    assert r.status_code == 303  # second sign-in evicted the first (the fixture's) session

    r = client.get("/dashboard", follow_redirects=True)
    assert r.status_code == 200
    assert "You were signed out because this account reached its limit of 1 sessions" in r.text
    # one-shot: shown once only
    again = client.get("/login")
    assert "reached its limit" not in again.text


def test_never_evicted_session_gets_no_notice(client):
    assert "reached its limit" not in client.get("/login").text


# ------------------------------------------------------------------ L-106
class TestStripeOrdering:
    def _setup(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
        monkeypatch.setenv("STRIPE_PRICE_STARTER", "price_starter_1")
        monkeypatch.setenv("STRIPE_PRICE_PROFESSIONAL", "price_pro_1")

    def _evt(self, eid, status, created, price="price_pro_1", etype="customer.subscription.updated"):
        return {"id": eid, "type": etype, "created": created,
                "data": {"object": {"id": "sub_1", "customer": "cus_1", "status": status,
                                    "metadata": {}, "current_period_end": created + 86400 * 30,
                                    "items": {"data": [{"price": {"id": price}}]}}}}

    def test_out_of_order_updates_do_not_regress(self, client, monkeypatch):
        from amlkit.billing.service import handle_event
        from amlkit.billing import stripe_client
        self._setup(monkeypatch)
        cfg = stripe_client.load_config()
        c = _db()
        org = c.execute("SELECT id FROM organizations ORDER BY id LIMIT 1").fetchone()["id"]
        c.execute("UPDATE organizations SET billing_customer_id='cus_1' WHERE id=?", (org,))
        c.commit()
        now = int(time.time())
        assert handle_event(c, self._evt("evt_new", "canceled", now), cfg) == "processed"
        # a delayed, older "active" update arrives afterwards
        assert handle_event(c, self._evt("evt_old", "active", now - 3600), cfg) == "processed"
        row = c.execute("SELECT plan_status FROM organizations WHERE id=?", (org,)).fetchone()
        assert row["plan_status"] == "canceled"
        # both events are stored
        n = c.execute("SELECT COUNT(*) FROM billing_events").fetchone()[0]
        assert n == 2
        # a newer event still applies
        handle_event(c, self._evt("evt_newer", "active", now + 60), cfg)
        assert c.execute("SELECT plan_status FROM organizations WHERE id=?",
                         (org,)).fetchone()["plan_status"] == "active"
        c.close()

    def test_invoice_events_unaffected_by_ordering(self, client, monkeypatch):
        from amlkit.billing.service import handle_event
        from amlkit.billing import stripe_client
        self._setup(monkeypatch)
        cfg = stripe_client.load_config()
        c = _db()
        org = c.execute("SELECT id FROM organizations ORDER BY id LIMIT 1").fetchone()["id"]
        c.execute("UPDATE organizations SET billing_customer_id='cus_1' WHERE id=?", (org,))
        c.commit()
        now = int(time.time())
        handle_event(c, self._evt("e1", "active", now), cfg)
        inv = {"id": "evt_inv", "type": "invoice.payment_failed", "created": now - 7200,
               "data": {"object": {"id": "in_1", "customer": "cus_1", "subscription": "sub_1"}}}
        handle_event(c, inv, cfg)
        assert c.execute("SELECT plan_status FROM organizations WHERE id=?",
                         (org,)).fetchone()["plan_status"] == "past_due"
        c.close()
