"""UAE PASS integration tests.

Everything here is mocked at the `httpx` layer (see TestClientErrorHandling's
`_client_returning` pattern in tests/test_adverse_media.py, which the
TestUaePassTransport class below mirrors) -- none of this hits UAE PASS's
real staging servers, which would need a live UAE PASS mobile-app
interaction a script cannot drive.

Manual end-to-end check against real UAE PASS staging (not run by this
suite): set UAEPASS_CLIENT_ID=sandbox_stage and
UAEPASS_CLIENT_SECRET=sandbox_stage (UAE PASS's own published POC sandbox
credentials -- see amlkit/uaepass.py's module docstring), start the app, and
visit /auth/uaepass/start (or a customer's "Verify via UAE PASS" button). UAE
PASS's staging app will prompt a real sandbox login and redirect back with a
real authorization code, exercising the full flow this test file can only
mock.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conftest import register_org, settle_mfa  # noqa: E402
from test_api import _csrf, _db, _seed_sanctions_data  # noqa: E402


# ======================================================================
# Unit tests: amlkit/uaepass.py -- pure, no DB, no app, no network.
# ======================================================================

class _FakeResponse:
    def __init__(self, status_code: int = 200, json_data=None, json_error: bool = False):
        self.status_code = status_code
        self._json_data = json_data
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise ValueError("not json")
        return self._json_data


class TestLoadConfig:
    def test_none_when_unset(self, monkeypatch):
        from amlkit import uaepass

        monkeypatch.delenv("UAEPASS_CLIENT_ID", raising=False)
        monkeypatch.delenv("UAEPASS_CLIENT_SECRET", raising=False)
        assert uaepass.load_config() is None

    def test_none_when_only_client_id_set(self, monkeypatch):
        from amlkit import uaepass

        monkeypatch.setenv("UAEPASS_CLIENT_ID", "sandbox_stage")
        monkeypatch.delenv("UAEPASS_CLIENT_SECRET", raising=False)
        assert uaepass.load_config() is None

    def test_staging_is_the_default(self, monkeypatch):
        from amlkit import uaepass

        monkeypatch.setenv("UAEPASS_CLIENT_ID", "sandbox_stage")
        monkeypatch.setenv("UAEPASS_CLIENT_SECRET", "sandbox_stage")
        monkeypatch.delenv("UAEPASS_ENV", raising=False)
        config = uaepass.load_config()
        assert config is not None
        assert config.environment == "staging"
        assert config.authorize_url == "https://stg-id.uaepass.ae/idshub/authorize"
        assert config.token_url == "https://stg-id.uaepass.ae/idshub/token"
        assert config.userinfo_url == "https://stg-id.uaepass.ae/idshub/userinfo"
        assert config.client_id == "sandbox_stage"
        assert config.client_secret == "sandbox_stage"

    def test_production_env_selects_production_endpoints(self, monkeypatch):
        from amlkit import uaepass

        monkeypatch.setenv("UAEPASS_CLIENT_ID", "real-client")
        monkeypatch.setenv("UAEPASS_CLIENT_SECRET", "real-secret")
        monkeypatch.setenv("UAEPASS_ENV", "production")
        config = uaepass.load_config()
        assert config.environment == "production"
        assert config.authorize_url == "https://id.uaepass.ae/idshub/authorize"
        assert config.token_url == "https://id.uaepass.ae/idshub/token"
        assert config.userinfo_url == "https://id.uaepass.ae/idshub/userinfo"


class TestBuildAuthorizeUrl:
    def test_exact_query_params(self):
        from amlkit import uaepass
        from urllib.parse import parse_qs, urlparse

        config = uaepass.UaePassConfig(
            client_id="sandbox_stage", client_secret="sandbox_stage", environment="staging",
            authorize_url="https://stg-id.uaepass.ae/idshub/authorize",
            token_url="https://stg-id.uaepass.ae/idshub/token",
            userinfo_url="https://stg-id.uaepass.ae/idshub/userinfo",
            logout_url="https://stg-id.uaepass.ae/idshub/logout",
        )
        url = uaepass.build_authorize_url(
            config, state="STATE123", redirect_uri="https://app.example/cb",
            acr=uaepass.ACR_LEVEL_DEFAULT,
        )
        parsed = urlparse(url)
        assert parsed.scheme == "https"
        assert parsed.netloc == "stg-id.uaepass.ae"
        assert parsed.path == "/idshub/authorize"
        qs = parse_qs(parsed.query)
        assert qs["response_type"] == ["code"]
        assert qs["client_id"] == ["sandbox_stage"]
        assert qs["scope"] == ["urn:uae:digitalid:profile:general"]
        assert qs["state"] == ["STATE123"]
        assert qs["redirect_uri"] == ["https://app.example/cb"]
        assert qs["acr_values"] == ["urn:safelayer:tws:policies:authentication:level:low"]


@pytest.fixture()
def config():
    from amlkit import uaepass

    return uaepass.UaePassConfig(
        client_id="sandbox_stage", client_secret="sandbox_stage", environment="staging",
        authorize_url="https://stg-id.uaepass.ae/idshub/authorize",
        token_url="https://stg-id.uaepass.ae/idshub/token",
        userinfo_url="https://stg-id.uaepass.ae/idshub/userinfo",
        logout_url="https://stg-id.uaepass.ae/idshub/logout",
    )


class TestExchangeCode:
    def test_success(self, monkeypatch, config):
        import httpx
        from amlkit import uaepass

        monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse(200, {"access_token": "tok-abc"}))
        result = uaepass.exchange_code(config, code="xyz", redirect_uri="https://app.example/cb")
        assert result["access_token"] == "tok-abc"

    def test_non_200_raises(self, monkeypatch, config):
        import httpx
        from amlkit import uaepass

        monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse(400, {}))
        with pytest.raises(uaepass.UaePassError, match="HTTP 400"):
            uaepass.exchange_code(config, code="xyz", redirect_uri="https://app.example/cb")

    def test_malformed_json_raises(self, monkeypatch, config):
        import httpx
        from amlkit import uaepass

        monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse(200, json_error=True))
        with pytest.raises(uaepass.UaePassError, match="non-JSON"):
            uaepass.exchange_code(config, code="xyz", redirect_uri="https://app.example/cb")

    def test_missing_access_token_raises(self, monkeypatch, config):
        import httpx
        from amlkit import uaepass

        monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse(200, {"token_type": "Bearer"}))
        with pytest.raises(uaepass.UaePassError, match="access_token"):
            uaepass.exchange_code(config, code="xyz", redirect_uri="https://app.example/cb")

    def test_transport_error_raises(self, monkeypatch, config):
        import httpx
        from amlkit import uaepass

        def boom(*a, **k):
            raise httpx.ConnectError("no route to host")

        monkeypatch.setattr(httpx, "post", boom)
        with pytest.raises(uaepass.UaePassError, match="request failed"):
            uaepass.exchange_code(config, code="xyz", redirect_uri="https://app.example/cb")


_SAMPLE_USERINFO = {
    "sub": "UAEPASS/7a05992e-3244-49d3-bcbc-7894c8fca25e",
    "uuid": "7a05992e-3244-49d3-bcbc-7894c8fca25e",
    "idn": "784189014978983",
    "firstnameEN": "Ram", "lastnameEN": "ABC", "fullnameEN": "Ram,,,,ABC,,",
    "gender": "Male",
    "mobile": "97151234003",
    "email": "ramabc1234@gmail.com",
    "nationalityEN": "IND", "nationalityAR": "الهند",
    "userType": "SOP3",
}


class TestFetchUserinfo:
    def test_success_parses_all_documented_fields(self, monkeypatch, config):
        import httpx
        from amlkit import uaepass

        monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse(200, dict(_SAMPLE_USERINFO)))
        profile = uaepass.fetch_userinfo(config, "tok-abc")
        assert profile.uuid == "7a05992e-3244-49d3-bcbc-7894c8fca25e"
        assert profile.idn == "784189014978983"
        assert profile.fullname_en == "Ram,,,,ABC,,"
        assert profile.nationality_en == "IND"
        assert profile.mobile == "97151234003"
        assert profile.email == "ramabc1234@gmail.com"
        assert profile.user_type == "SOP3"
        assert profile.raw == _SAMPLE_USERINFO

    def test_missing_fields_do_not_crash(self, monkeypatch, config):
        """Defensive parsing: an unexpected/partial shape degrades to None
        fields rather than raising -- see uaepass.py's module docstring."""
        import httpx
        from amlkit import uaepass

        monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse(200, {"sub": "x"}))
        profile = uaepass.fetch_userinfo(config, "tok-abc")
        assert profile.sub == "x"
        assert profile.idn is None
        assert profile.email is None
        assert profile.raw == {"sub": "x"}

    def test_non_200_raises(self, monkeypatch, config):
        import httpx
        from amlkit import uaepass

        monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse(401, {}))
        with pytest.raises(uaepass.UaePassError, match="HTTP 401"):
            uaepass.fetch_userinfo(config, "bad-token")

    def test_malformed_json_raises(self, monkeypatch, config):
        import httpx
        from amlkit import uaepass

        monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse(200, json_error=True))
        with pytest.raises(uaepass.UaePassError, match="non-JSON"):
            uaepass.fetch_userinfo(config, "tok-abc")

    def test_non_dict_body_raises(self, monkeypatch, config):
        import httpx
        from amlkit import uaepass

        monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse(200, ["not", "a", "dict"]))
        with pytest.raises(uaepass.UaePassError, match="JSON object"):
            uaepass.fetch_userinfo(config, "tok-abc")


class TestAlpha3ToAlpha2:
    def test_known_codes(self):
        from amlkit import uaepass

        assert uaepass.alpha3_to_alpha2("ARE") == "AE"
        assert uaepass.alpha3_to_alpha2("IND") == "IN"
        assert uaepass.alpha3_to_alpha2("usa") == "US"  # case-insensitive

    def test_unrecognised_code_returned_unchanged(self):
        from amlkit import uaepass

        assert uaepass.alpha3_to_alpha2("ZZZ") == "ZZZ"

    def test_none_passthrough(self):
        from amlkit import uaepass

        assert uaepass.alpha3_to_alpha2(None) is None

    def test_every_mapped_value_is_a_valid_amlkit_country_code(self):
        """Every alpha-2 this table can produce must itself validate --
        otherwise a UAE PASS nationality would map onto a code onboard()
        rejects anyway."""
        from amlkit import uaepass
        from amlkit.datamodel import COUNTRY_CODES

        for alpha2 in uaepass.ALPHA3_TO_ALPHA2.values():
            assert alpha2 in COUNTRY_CODES, alpha2


class TestNormalizeGender:
    def test_maps_uaepass_capitalisation(self):
        from amlkit import uaepass

        assert uaepass.normalize_gender("Male") == "male"
        assert uaepass.normalize_gender("Female") == "female"

    def test_unrecognised_or_missing_is_none(self):
        from amlkit import uaepass

        assert uaepass.normalize_gender("Other") is None
        assert uaepass.normalize_gender(None) is None
        assert uaepass.normalize_gender("") is None


# ======================================================================
# Integration tests: FastAPI TestClient, httpx mocked, real SQLite file.
# ======================================================================

def _mock_uaepass_exchange(monkeypatch, *, userinfo: dict):
    """Patch httpx.post/httpx.get so the token exchange and userinfo calls
    both succeed, returning `userinfo` as the parsed profile payload --
    mirrors tests/test_adverse_media.py's `_client_returning` pattern."""
    import httpx

    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse(200, {"access_token": "tok-abc"}))
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse(200, dict(userinfo)))


def _extract_state(location: str) -> str:
    from urllib.parse import parse_qs, urlparse

    return parse_qs(urlparse(location).query)["state"][0]


def _create_officer(client, name: str, email: str, password: str = "a-strong-password-1") -> None:
    r = client.post("/admin/operators", data={
        "name": name, "email": email, "password": password, "role": "officer",
        "csrf_token": _csrf(client),
    }, follow_redirects=True)
    assert "created" in r.text.lower(), r.text[:300]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """App wired to a throwaway database, UAE PASS configured with the
    sandbox POC credentials, with a fresh org registered and logged in as
    its MLRO ("alice")."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.setenv("UAEPASS_CLIENT_ID", "sandbox_stage")
    monkeypatch.setenv("UAEPASS_CLIENT_SECRET", "sandbox_stage")
    monkeypatch.delenv("UAEPASS_ENV", raising=False)
    monkeypatch.delenv("AMLKIT_BEHIND_PROXY", raising=False)

    _seed_sanctions_data(db_file)

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    register_org(c, "Test Firm", "alice", "alice@testfirm.ae")
    return c


class TestUaePassInert:
    def test_routes_404_when_unconfigured(self, tmp_path, monkeypatch):
        db_file = tmp_path / "inert.db"
        monkeypatch.setenv("AMLKIT_DB", str(db_file))
        monkeypatch.delenv("UAEPASS_CLIENT_ID", raising=False)
        monkeypatch.delenv("UAEPASS_CLIENT_SECRET", raising=False)
        _seed_sanctions_data(db_file)

        from fastapi.testclient import TestClient
        from amlkit.api.app import app

        c = TestClient(app)
        r = c.get("/auth/uaepass/start", follow_redirects=False)
        assert r.status_code == 404

    def test_no_button_on_login_page_when_unconfigured(self, tmp_path, monkeypatch):
        db_file = tmp_path / "inert2.db"
        monkeypatch.setenv("AMLKIT_DB", str(db_file))
        monkeypatch.delenv("UAEPASS_CLIENT_ID", raising=False)
        monkeypatch.delenv("UAEPASS_CLIENT_SECRET", raising=False)
        _seed_sanctions_data(db_file)

        from fastapi.testclient import TestClient
        from amlkit.api.app import app

        c = TestClient(app)
        r = c.get("/login")
        assert "uaepass" not in r.text.lower()

    def test_button_shown_on_login_page_when_configured(self, client):
        r = client.get("/login")
        assert "uae pass" in r.text.lower()


class TestOperatorSsoHappyPath:
    def test_prelinked_identity_logs_in_without_mfa(self, client, monkeypatch):
        """An operator (officer role, no MFA gate) whose uaepass_uuid is
        already on file signs in directly via the first lookup branch of
        resolve_uaepass_operator()."""
        _create_officer(client, "omar", "omar@testfirm.ae")
        conn = _db()
        conn.execute("UPDATE operators SET uaepass_uuid=? WHERE email=?",
                     ("uuid-omar-123", "omar@testfirm.ae"))
        conn.commit()
        conn.close()

        _mock_uaepass_exchange(monkeypatch, userinfo={**_SAMPLE_USERINFO, "uuid": "uuid-omar-123"})

        fresh = client  # same cookie jar is fine: /start doesn't require a session
        start = fresh.get("/auth/uaepass/start", follow_redirects=False)
        assert start.status_code in (302, 303)
        state = _extract_state(start.headers["location"])

        callback = fresh.get(
            f"/auth/uaepass/callback?code=fake-code&state={state}", follow_redirects=False
        )
        assert callback.status_code == 303
        assert callback.headers["location"] == "/"
        assert "amlkit_session" in callback.cookies

        conn = _db()
        row = conn.execute(
            "SELECT action, org_id, detail FROM audit_log WHERE action='operator.login'"
            " ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        assert row is not None
        assert "uaepass" in row["detail"]

    def test_first_time_link_via_verified_email(self, client, monkeypatch):
        """No uaepass_uuid on file yet, but the operator's own (already
        verified) email matches the UAE PASS profile's email -- links and
        logs in, and persists the uuid for next time."""
        _create_officer(client, "zoya", "zoya@testfirm.ae")
        _mock_uaepass_exchange(
            monkeypatch, userinfo={**_SAMPLE_USERINFO, "uuid": "uuid-zoya-999", "email": "zoya@testfirm.ae"}
        )

        start = client.get("/auth/uaepass/start", follow_redirects=False)
        state = _extract_state(start.headers["location"])
        callback = client.get(
            f"/auth/uaepass/callback?code=fake-code&state={state}", follow_redirects=False
        )
        assert callback.status_code == 303
        assert callback.headers["location"] == "/"

        conn = _db()
        row = conn.execute(
            "SELECT uaepass_uuid FROM operators WHERE email=?", ("zoya@testfirm.ae",)
        ).fetchone()
        conn.close()
        assert row["uaepass_uuid"] == "uuid-zoya-999"

    def test_unverified_email_is_not_linked(self, client, monkeypatch):
        """An operator row whose email_verified_at is NULL must never be
        linked by email match -- that would let someone claim the account via
        UAE PASS before proving they control the email at all."""
        conn = _db()
        conn.execute(
            "INSERT INTO operators (org_id, name, email, password_hash, role, is_active,"
            " email_verified_at, created_at) VALUES ("
            " (SELECT org_id FROM operators WHERE name='alice'),"
            " 'unverified', 'unverified@testfirm.ae', 'x', 'officer', 1, NULL, '2026-01-01T00:00:00+00:00')"
        )
        conn.commit()
        conn.close()

        _mock_uaepass_exchange(
            monkeypatch,
            userinfo={**_SAMPLE_USERINFO, "uuid": "uuid-unverified", "email": "unverified@testfirm.ae"},
        )

        start = client.get("/auth/uaepass/start", follow_redirects=False)
        state = _extract_state(start.headers["location"])
        callback = client.get(
            f"/auth/uaepass/callback?code=fake-code&state={state}", follow_redirects=True
        )
        assert "ask an admin" in callback.text.lower()

        conn = _db()
        row = conn.execute(
            "SELECT uaepass_uuid FROM operators WHERE email='unverified@testfirm.ae'"
        ).fetchone()
        conn.close()
        assert row["uaepass_uuid"] is None


class TestOperatorSsoRejections:
    def test_no_match_does_not_create_an_account(self, client, monkeypatch):
        before = _db()
        count_before = before.execute("SELECT COUNT(*) c FROM operators").fetchone()["c"]
        before.close()

        _mock_uaepass_exchange(
            monkeypatch, userinfo={**_SAMPLE_USERINFO, "uuid": "uuid-nobody", "email": "nobody@nowhere.ae"}
        )
        start = client.get("/auth/uaepass/start", follow_redirects=False)
        state = _extract_state(start.headers["location"])
        callback = client.get(
            f"/auth/uaepass/callback?code=fake-code&state={state}", follow_redirects=True
        )
        assert "no groaml account is linked" in callback.text.lower()

        after = _db()
        count_after = after.execute("SELECT COUNT(*) c FROM operators").fetchone()["c"]
        after.close()
        assert count_after == count_before, "UAE PASS SSO must never auto-provision an operator"

    def test_state_mismatch_is_rejected(self, client):
        """A state value this app never issued must be rejected outright --
        this check IS the flow's CSRF/replay defense."""
        r = client.get(
            "/auth/uaepass/callback?code=fake-code&state=not-a-real-state", follow_redirects=True
        )
        assert "expired" in r.text.lower() or "already been used" in r.text.lower() \
            or "already used" in r.text.lower()

    def test_state_cannot_be_replayed(self, client, monkeypatch):
        _create_officer(client, "nina", "nina@testfirm.ae")
        conn = _db()
        conn.execute("UPDATE operators SET uaepass_uuid=? WHERE email=?",
                     ("uuid-nina", "nina@testfirm.ae"))
        conn.commit()
        conn.close()

        _mock_uaepass_exchange(monkeypatch, userinfo={**_SAMPLE_USERINFO, "uuid": "uuid-nina"})
        start = client.get("/auth/uaepass/start", follow_redirects=False)
        state = _extract_state(start.headers["location"])

        first = client.get(f"/auth/uaepass/callback?code=c1&state={state}", follow_redirects=False)
        assert first.status_code == 303 and first.headers["location"] == "/"

        second = client.get(
            f"/auth/uaepass/callback?code=c2&state={state}", follow_redirects=True
        )
        assert "already used" in second.text.lower() or "expired" in second.text.lower()


class TestCustomerVerification:
    def _make_customer(self, client, reference: str, full_name: str) -> int:
        client.post("/customers", data={
            "reference": reference, "full_name": full_name,
            "customer_type": "natural", "csrf_token": _csrf(client),
        }, follow_redirects=True)
        conn = _db()
        row = conn.execute("SELECT id FROM customers WHERE reference=?", (reference,)).fetchone()
        conn.close()
        return row["id"]

    def test_happy_path_records_verification_and_audit(self, client, monkeypatch):
        customer_id = self._make_customer(client, "UP-1", "Empty Identity Customer")
        _mock_uaepass_exchange(monkeypatch, userinfo=dict(_SAMPLE_USERINFO))

        start = client.get(f"/customers/{customer_id}/uaepass/start", follow_redirects=False)
        assert start.status_code in (302, 303)
        state = _extract_state(start.headers["location"])

        callback = client.get(
            f"/customers/{customer_id}/uaepass/callback?code=fake-code&state={state}",
            follow_redirects=True,
        )
        assert "verified via uae pass" in callback.text.lower()

        conn = _db()
        org_id = conn.execute(
            "SELECT org_id FROM customers WHERE id=?", (customer_id,)
        ).fetchone()["org_id"]

        verif = conn.execute(
            "SELECT * FROM uaepass_verifications WHERE customer_id=?", (customer_id,)
        ).fetchone()
        assert verif is not None
        assert verif["org_id"] == org_id
        assert verif["idn"] == _SAMPLE_USERINFO["idn"]
        assert verif["user_type"] == "SOP3"

        audit_row = conn.execute(
            "SELECT * FROM audit_log WHERE action='customer.uaepass_verify' AND object_id=?",
            (str(customer_id),),
        ).fetchone()
        assert audit_row is not None
        assert audit_row["org_id"] == org_id

        # Best-effort backfill: the customer had no id_number/nationality/etc.
        # on file, so the verified fields should now be set.
        cust = conn.execute(
            "SELECT id_number, id_type, nationality, phone FROM customers WHERE id=?",
            (customer_id,),
        ).fetchone()
        conn.close()
        assert cust["id_number"] == _SAMPLE_USERINFO["idn"]
        assert cust["id_type"] == "emirates_id"
        assert cust["nationality"] == "IN"  # alpha-3 IND -> alpha-2 IN
        assert cust["phone"] == _SAMPLE_USERINFO["mobile"]

    def test_does_not_overwrite_existing_identity_fields(self, client, monkeypatch):
        """Non-destructive: a field already recorded on the customer is not
        silently replaced by the UAE PASS value. (The web onboarding form has
        no field for `customers.phone` directly, so this sets it straight on
        the row -- exactly the state record_uaepass_verification() must
        respect regardless of how it got there.)"""
        customer_id = self._make_customer(client, "UP-2", "Already Has Phone")
        conn = _db()
        conn.execute("UPDATE customers SET phone=? WHERE id=?", ("+971500000000", customer_id))
        conn.commit()
        conn.close()

        _mock_uaepass_exchange(monkeypatch, userinfo=dict(_SAMPLE_USERINFO))
        start = client.get(f"/customers/{customer_id}/uaepass/start", follow_redirects=False)
        state = _extract_state(start.headers["location"])
        client.get(
            f"/customers/{customer_id}/uaepass/callback?code=fake-code&state={state}",
            follow_redirects=True,
        )

        conn = _db()
        phone = conn.execute("SELECT phone FROM customers WHERE id=?", (customer_id,)).fetchone()["phone"]
        conn.close()
        assert phone == "+971500000000"

    def test_cross_org_customer_id_is_rejected(self, client, tmp_path, monkeypatch):
        customer_id = self._make_customer(client, "UP-ISO", "Isolated Customer")

        from fastapi.testclient import TestClient
        from amlkit.api.app import app

        other = TestClient(app)
        register_org(other, "Second Firm", "sara", "sara@secondfirm.ae")

        # Second org's session must not even be able to START a verification
        # for the first org's customer_id.
        start = other.get(f"/customers/{customer_id}/uaepass/start", follow_redirects=True)
        assert "not found" in start.text.lower()

        conn = _db()
        count = conn.execute(
            "SELECT COUNT(*) c FROM uaepass_verifications WHERE customer_id=?", (customer_id,)
        ).fetchone()["c"]
        states = conn.execute(
            "SELECT COUNT(*) c FROM uaepass_states WHERE customer_id=?", (customer_id,)
        ).fetchone()["c"]
        conn.close()
        assert count == 0
        assert states == 0, "no state should be issued for a customer outside the caller's org"

    def test_missing_uuid_in_userinfo_fails_gracefully(self, client, monkeypatch):
        """A malformed UAE PASS response with no `uuid` must not 500 against
        uaepass_verifications' NOT NULL constraint -- see uaepass.py's
        defensive-parsing caveat and the explicit guard in the callback."""
        customer_id = self._make_customer(client, "UP-4", "Malformed Response")
        _mock_uaepass_exchange(monkeypatch, userinfo={"sub": "x"})  # no uuid at all

        start = client.get(f"/customers/{customer_id}/uaepass/start", follow_redirects=False)
        state = _extract_state(start.headers["location"])
        r = client.get(
            f"/customers/{customer_id}/uaepass/callback?code=fake-code&state={state}",
            follow_redirects=True,
        )
        assert r.status_code == 200
        assert "did not return a verifiable identity" in r.text.lower()

        conn = _db()
        count = conn.execute(
            "SELECT COUNT(*) c FROM uaepass_verifications WHERE customer_id=?", (customer_id,)
        ).fetchone()["c"]
        conn.close()
        assert count == 0

    def test_requires_a_session(self, client):
        customer_id = self._make_customer(client, "UP-3", "Needs Session")

        from fastapi.testclient import TestClient
        from amlkit.api.app import app

        anon_client = TestClient(app)
        r = anon_client.get(f"/customers/{customer_id}/uaepass/start", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/login"
