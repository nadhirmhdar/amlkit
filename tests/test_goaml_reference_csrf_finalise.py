"""goAML entity reference round-trip, CSRF on org-profile/logout, and
finalise-time export validation (lead findings L-4, L-8, L-7).

Real SQLite, TestClient, no DB mocks.
"""

from __future__ import annotations

import os
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_report_save_flow import (  # noqa: E402,F401  (client is a pytest fixture)
    NATURAL_PERSON_FORM, _csrf, _customer_id, client,
)
from test_mobile_api import api  # noqa: E402,F401  (pytest fixture)

PROFILE = {
    "org_address": "Office 1, Business Bay, Dubai",
    "reporting_person_name": "Alice MLRO",
    "reporting_person_title": "MLRO",
    "reporting_person_phone": "+971500000000",
}


def _org_row() -> sqlite3.Row:
    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute("SELECT * FROM organizations LIMIT 1").fetchone()
    finally:
        conn.close()


def _save_profile(client, **overrides):
    data = {**PROFILE, "goaml_entity_reference": "", "csrf_token": _csrf(client)}
    data.update(overrides)
    return client.post("/admin/org-profile", data=data, follow_redirects=False)


def _admin_inputs(client) -> dict[str, str]:
    """name -> value of every org-profile text input as /admin renders it."""
    page = client.get("/admin").text
    form = re.search(r'<form[^>]*action="/admin/org-profile".*?</form>', page, re.S).group(0)
    out = {}
    for tag in re.findall(r"<input[^>]*>", form):
        name = re.search(r'name="([^"]+)"', tag)
        if name and 'type="hidden"' not in tag and 'type="checkbox"' not in tag:
            value = re.search(r'value="([^"]*)"', tag)
            out[name.group(1)] = value.group(1) if value else ""
    return out


# ------------------------------------------------------------------ L-4

class TestEntityReferenceRoundTrip:
    def test_admin_renders_saved_reference(self, client) -> None:
        _save_profile(client, goaml_entity_reference="TEST-ORG-0001")
        assert _org_row()["goaml_entity_reference"] == "TEST-ORG-0001"
        assert _admin_inputs(client)["goaml_entity_reference"] == "TEST-ORG-0001"

    def test_untouched_form_round_trips_every_field(self, client) -> None:
        _save_profile(client, goaml_entity_reference="TEST-ORG-0001")
        before = dict(_org_row())
        rendered = _admin_inputs(client)
        r = client.post("/admin/org-profile",
                        data={**rendered, "csrf_token": _csrf(client)}, follow_redirects=False)
        assert r.status_code == 303
        after = dict(_org_row())
        for col in ("org_address", "reporting_person_name", "reporting_person_title",
                    "reporting_person_phone", "goaml_entity_reference"):
            assert after[col] == before[col], col

    def test_phone_only_edit_keeps_reference(self, client) -> None:
        _save_profile(client, goaml_entity_reference="TEST-ORG-0001")
        rendered = _admin_inputs(client)
        rendered["reporting_person_phone"] = "+971500000001"
        client.post("/admin/org-profile", data={**rendered, "csrf_token": _csrf(client)})
        row = _org_row()
        assert row["reporting_person_phone"] == "+971500000001"
        assert row["goaml_entity_reference"] == "TEST-ORG-0001"

    def test_blank_submit_does_not_erase_reference(self, client) -> None:
        _save_profile(client, goaml_entity_reference="TEST-ORG-0001")
        _save_profile(client, goaml_entity_reference="", reporting_person_phone="+971500000002")
        row = _org_row()
        assert row["goaml_entity_reference"] == "TEST-ORG-0001"
        assert row["reporting_person_phone"] == "+971500000002"

    def test_explicit_clear_erases_reference(self, client) -> None:
        _save_profile(client, goaml_entity_reference="TEST-ORG-0001")
        _save_profile(client, goaml_entity_reference="TEST-ORG-0001",
                      clear_goaml_entity_reference="1")
        assert _org_row()["goaml_entity_reference"] is None

    def test_reference_can_be_changed(self, client) -> None:
        _save_profile(client, goaml_entity_reference="TEST-ORG-0001")
        _save_profile(client, goaml_entity_reference="TEST-ORG-0002")
        assert _org_row()["goaml_entity_reference"] == "TEST-ORG-0002"


class TestBuilderPrefill:
    def _entity_reference_value(self, client, customer_id: int, suffix: str = "") -> str:
        page = client.get(f"/reports/build?customer_id={customer_id}&report_type=STR{suffix}").text
        m = re.search(r'<input[^>]*name="entity_reference"[^>]*>', page)
        assert m, "entity_reference input not found"
        v = re.search(r'value="([^"]*)"', m.group(0))
        return v.group(1) if v else ""

    def test_prefills_org_saved_reference(self, client) -> None:
        _save_profile(client, goaml_entity_reference="TEST-ORG-0001")
        assert self._entity_reference_value(client, _customer_id(client)) == "TEST-ORG-0001"

    def test_neutral_empty_when_org_has_no_reference(self, client) -> None:
        value = self._entity_reference_value(client, _customer_id(client))
        assert value == ""
        assert "GROVISOR-LIC-2026" not in client.get(
            f"/reports/build?customer_id={_customer_id(client, reference='C-9')}&report_type=STR"
        ).text

    def test_draft_reference_wins_over_org_reference(self, client) -> None:
        customer_id = _customer_id(client)
        form = {**NATURAL_PERSON_FORM, "entity_reference": "DRAFT-REF-7"}
        client.post("/reports", data={"customer_id": customer_id, "report_type": "STR",
                                      "csrf_token": _csrf(client), **form})
        conn = sqlite3.connect(os.environ["AMLKIT_DB"])
        rid = conn.execute("SELECT id FROM reports ORDER BY id DESC LIMIT 1").fetchone()[0]
        conn.close()
        _save_profile(client, goaml_entity_reference="TEST-ORG-0001")
        assert self._entity_reference_value(
            client, customer_id, suffix=f"&report_id={rid}") == "DRAFT-REF-7"


# ------------------------------------------------------------------ L-8

def _signed_in(client) -> bool:
    return client.get("/admin", follow_redirects=False).status_code == 200


class TestCsrf:
    """Repo convention: a form route that fails CSRF redirects back with a
    flash error (``back(url, err=...)``), never a bare JSON 403 on a blank
    page, so the user keeps their place and can retry. Only the bearer-token
    /system/* routes and /api/v1 answer with an HTTP error status."""

    def test_org_profile_bad_token_redirects_back_with_error_and_changes_nothing(self, client) -> None:
        _save_profile(client, goaml_entity_reference="KEEP-ME")
        for data in ({**PROFILE, "goaml_entity_reference": "NO-CSRF"},
                     {**PROFILE, "goaml_entity_reference": "BAD-CSRF", "csrf_token": "not-the-token"}):
            r = client.post("/admin/org-profile", data=data, follow_redirects=False)
            assert r.status_code == 303 and r.headers["location"] == "/admin"
            row = _org_row()
            assert row["goaml_entity_reference"] == "KEEP-ME"
            assert row["reporting_person_name"] == "Alice MLRO"
            page = client.get("/admin")
            assert "stale page" in page.text  # the flash error is shown on /admin
            # the form is re-rendered with the saved values, not blanked
            assert _admin_inputs(client)["goaml_entity_reference"] == "KEEP-ME"

    def test_org_profile_succeeds_with_valid_token(self, client) -> None:
        r = _save_profile(client, goaml_entity_reference="OK-REF")
        assert r.status_code == 303
        assert _org_row()["goaml_entity_reference"] == "OK-REF"

    def test_org_profile_unauthenticated_still_redirects_to_login(self, client) -> None:
        from fastapi.testclient import TestClient
        from amlkit.api.app import app
        anon = TestClient(app)
        anon.get("/login")
        r = anon.post("/admin/org-profile", data={"csrf_token": _csrf(anon)},
                      follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login"

    # -- /logout: three ways the token can be wrong, plus the happy path

    def test_logout_stale_token_while_signed_in_keeps_session_and_asks_to_retry(self, client) -> None:
        r = client.post("/logout", data={"csrf_token": "stale-from-another-tab"},
                        follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/"
        assert "Please try logging out again" in client.get("/").text  # flash, not JSON
        assert _signed_in(client)  # a forged/stale logout must not sign anyone out

    def test_logout_missing_token_while_signed_in_is_blocked_the_same_way(self, client) -> None:
        """A cross-site form POST carries no token: still blocked."""
        r = client.post("/logout", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/"
        assert _signed_in(client)

    def test_logout_session_cookie_without_csrf_cookie_keeps_session(self, client) -> None:
        token = _csrf(client)
        client.cookies.delete("amlkit_csrf")
        r = client.post("/logout", data={"csrf_token": token}, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/"
        assert _signed_in(client)

    def test_logout_signed_out_user_on_stale_tab_goes_to_login(self, client) -> None:
        stale = _csrf(client)
        ok = client.post("/logout", data={"csrf_token": stale}, follow_redirects=False)
        assert ok.status_code == 303 and ok.headers["location"] == "/login"
        # second tab, already signed out, token now stale: nothing to protect
        r = client.post("/logout", data={"csrf_token": "stale"}, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login"
        r = client.post("/logout", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login"

    def test_logout_anonymous_without_any_cookies_goes_to_login(self) -> None:
        from fastapi.testclient import TestClient
        from amlkit.api.app import app
        r = TestClient(app).post("/logout", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login"

    def test_logout_succeeds_with_valid_token(self, client) -> None:
        r = client.post("/logout", data={"csrf_token": _csrf(client)}, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login"
        assert client.get("/admin", follow_redirects=False).status_code == 303

    def test_every_logout_and_org_profile_form_carries_the_token(self, client) -> None:
        templates = Path(__file__).resolve().parent.parent / "amlkit" / "web" / "templates"
        form_re = re.compile(
            r'<form[^>]*action="(?:/logout|/admin/org-profile)"[^>]*>(.*?)</form>', re.S)
        found = 0
        for path in templates.rglob("*.html"):
            for m in form_re.finditer(path.read_text(encoding="utf-8")):
                found += 1
                assert 'name="csrf_token"' in m.group(1), f"{path.name}: form lacks csrf_token"
        assert found >= 3  # base.html desktop + mobile logout, admin.html profile

    def test_only_bearer_routes_lack_csrf(self) -> None:
        """Every state-changing app.py route validates CSRF except the
        bearer-token /system/* routes."""
        src = (Path(__file__).resolve().parent.parent / "amlkit" / "api" / "app.py").read_text(encoding="utf-8")
        parts = re.split(r"\n(?=@app\.(?:post|put|delete|patch)\()", src)
        missing = []
        for p in parts[1:]:
            body = re.split(r"\n(?=@app\.)", p)[0]
            if "require_csrf" not in body and "csrf_valid" not in body:
                missing.append(p.split("\n")[0])
        unexpected = [m for m in missing if "/system/" not in m]
        assert "/logout" not in "".join(missing)
        assert "/admin/org-profile" not in "".join(missing)
        assert not unexpected, unexpected


# ------------------------------------------------------------------ L-7

class TestFinaliseValidatesExport:
    def _create(self, client, **overrides) -> int:
        customer_id = self.customer_id = _customer_id(client)
        form = {**NATURAL_PERSON_FORM, **overrides}
        client.post("/reports", data={"customer_id": customer_id, "report_type": "STR",
                                      "csrf_token": _csrf(client), **form})
        conn = sqlite3.connect(os.environ["AMLKIT_DB"])
        rid = conn.execute("SELECT id FROM reports ORDER BY id DESC LIMIT 1").fetchone()[0]
        conn.close()
        return rid

    def _status(self, rid: int) -> str:
        conn = sqlite3.connect(os.environ["AMLKIT_DB"])
        try:
            return conn.execute("SELECT status FROM reports WHERE id=?", (rid,)).fetchone()[0]
        finally:
            conn.close()

    def test_missing_source_account_refuses_finalise_and_keeps_draft_editable(self, client) -> None:
        rid = self._create(client, source_account="")
        r = client.post(f"/reports/{rid}/submit", data={"csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert "source account number" in r.text
        assert "still a draft" in r.text
        assert "Report finalized" not in r.text
        assert self._status(rid) == "draft"

        # the draft can still be edited ...
        customer_id = self.customer_id
        client.post("/reports", data={
            "customer_id": customer_id, "report_type": "STR", "report_id": rid,
            "csrf_token": _csrf(client), **NATURAL_PERSON_FORM})
        assert "can no longer be edited" not in client.get(f"/reports/{rid}").text
        # ... and then finalises and exports.
        r = client.post(f"/reports/{rid}/submit", data={"csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert "Report finalized" in r.text
        assert self._status(rid) == "submitted"
        assert client.get(f"/reports/{rid}/export").status_code == 200

    def test_all_missing_fields_are_named(self, client) -> None:
        rid = self._create(client, source_account="", destination_account="")
        r = client.post(f"/reports/{rid}/submit", data={"csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert "source account number" in r.text
        assert "destination account number" in r.text
        assert self._status(rid) == "draft"

    def test_missing_reporting_officer_email_is_named(self, client) -> None:
        rid = self._create(client, reporter_email=" ")
        r = client.post(f"/reports/{rid}/submit", data={"csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert "reporting officer email" in r.text
        assert self._status(rid) == "draft"

    def test_complete_report_still_finalises_and_exports(self, client) -> None:
        rid = self._create(client)
        r = client.post(f"/reports/{rid}/submit", data={"csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert "Report finalized" in r.text
        assert self._status(rid) == "submitted"
        x = client.get(f"/reports/{rid}/export")
        assert x.status_code == 200 and "<report_code>STR</report_code>" in x.text

    # ---- org-reference fallback at finalise

    def _set_org_reference(self, value) -> None:
        conn = sqlite3.connect(os.environ["AMLKIT_DB"])
        conn.execute("UPDATE organizations SET goaml_entity_reference=?", (value,))
        conn.commit()
        conn.close()

    def test_blank_report_reference_falls_back_to_org_reference_at_finalise(self, client) -> None:
        self._set_org_reference("TEST-ORG-0001")
        rid = _insert_report("STR", {**self.COMPLETE, "report_type": "STR", "entity_reference": ""})
        r = client.post(f"/reports/{rid}/submit", data={"csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert "Report finalized" in r.text
        assert self._status(rid) == "submitted"
        x = client.get(f"/reports/{rid}/export")
        assert x.status_code == 200
        assert "<entity_reference>TEST-ORG-0001</entity_reference>" in x.text

    def test_no_reference_anywhere_refuses_finalise_and_names_it(self, client) -> None:
        self._set_org_reference(None)
        rid = _insert_report("STR", {**self.COMPLETE, "report_type": "STR", "entity_reference": ""})
        r = client.post(f"/reports/{rid}/submit", data={"csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert "goAML entity reference" in r.text
        assert "still a draft" in r.text
        assert self._status(rid) == "draft"

    def test_report_reference_wins_over_org_reference_at_finalise(self, client) -> None:
        self._set_org_reference("TEST-ORG-0001")
        rid = self._create(client, entity_reference="DRAFT-REF-7")
        client.post(f"/reports/{rid}/submit", data={"csrf_token": _csrf(client)})
        x = client.get(f"/reports/{rid}/export")
        assert "<entity_reference>DRAFT-REF-7</entity_reference>" in x.text

    # ---- report types the exporter refuses

    COMPLETE = {"reporting_entity_name": "Test Firm", "entity_reference": "LIC-1",
                "reporter_name": "Alice MLRO", "reporter_email": "alice@testfirm.ae",
                "first_name": "Ahmed", "amount": "10", "transaction_type": "Wire",
                "source_account": "1", "destination_account": "2"}

    def test_unsupported_report_type_refuses_finalise_with_a_grammatical_message(self, client) -> None:
        rid = _insert_report("CTR", {**self.COMPLETE, "report_type": "CTR"})
        r = client.post(f"/reports/{rid}/submit", data={"csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert "This report cannot be exported as goAML" in r.text
        assert "Report type &#39;CTR&#39; is not supported" in r.text
        assert "requires Report type" not in r.text  # the old "requires <sentence>" splice
        assert "fill these in" not in r.text  # nothing the user can fill in
        assert self._status(rid) == "draft"

    def test_ffr_without_freeze_obligation_id_refuses_finalise_with_a_grammatical_message(self, client) -> None:
        rid = _insert_report("FFR", {**self.COMPLETE, "report_type": "FFR"})
        r = client.post(f"/reports/{rid}/submit", data={"csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert "This report cannot be exported as goAML" in r.text
        assert "freeze obligation ID is required" in r.text
        assert "requires Cannot" not in r.text
        assert self._status(rid) == "draft"

    def test_complete_ffr_finalises_and_exports(self, client) -> None:
        rid = _insert_report("FFR", {**self.COMPLETE, "report_type": "FFR",
                                     "freeze_obligation_id": 1})
        r = client.post(f"/reports/{rid}/submit", data={"csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert "Report finalized" in r.text
        assert self._status(rid) == "submitted"
        x = client.get(f"/reports/{rid}/export")
        assert x.status_code == 200 and "<report_code>FFR</report_code>" in x.text


def _insert_report(report_type: str, payload: dict) -> int:
    import json
    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    org_id = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()[0]
    cur = conn.execute(
        "INSERT INTO reports (org_id, report_type, reference, status, payload, created_at)"
        " VALUES (?,?,?,?,?, '2026-01-01T00:00:00Z')",
        (org_id, report_type, "REP-X", "draft", json.dumps(payload)))
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid


# ----------------------------------------------- dry-run == exporter, keyed errors

class TestDryRunAgreesWithExporter:
    INCOMPLETE = {"reporting_entity_name": "X", "reporter_name": "A B",
                  "reporter_email": "a@b.ae", "first_name": "Ahmed",
                  "amount": "10", "transaction_type": "Wire"}

    def test_incomplete_payload_both_refuse_with_the_same_fields(self) -> None:
        from amlkit.reporting.goaml import (
            GoAMLValidationError, missing_export_fields, serialize_goaml_xml)
        dry_run = missing_export_fields(self.INCOMPLETE)
        assert dry_run == ["source account number", "destination account number"]
        assert "source_account" not in self.INCOMPLETE  # input untouched

        # Walk the real exporter: fill in each gap it names until it succeeds.
        probe, exporter_gaps = dict(self.INCOMPLETE), []
        while True:
            try:
                serialize_goaml_xml(probe)
                break
            except GoAMLValidationError as exc:
                assert not probe.get(exc.key)  # it really was a gap
                exporter_gaps.append(exc.label)
                probe[exc.key] = "x"
        assert exporter_gaps == dry_run
        assert missing_export_fields(probe) == []  # a payload the exporter takes is clean

    def test_complete_payload_is_clean_in_both(self) -> None:
        from amlkit.reporting.goaml import missing_export_fields, serialize_goaml_xml
        payload = {**self.INCOMPLETE, "source_account": "1", "destination_account": "2"}
        assert missing_export_fields(payload) == []
        serialize_goaml_xml(payload)  # raises GoAMLValidationError if the dry-run lied

    def test_non_field_refusals_are_marked_and_not_offered_as_fields(self) -> None:
        from amlkit.reporting.goaml import is_field_gap, missing_export_fields
        for payload in ({**self.INCOMPLETE, "report_type": "CTR"},
                        {**self.INCOMPLETE, "report_type": "FFR"}):
            problems = missing_export_fields(payload)
            assert problems
            assert not is_field_gap(problems[-1])
            assert problems[-1].startswith("This report cannot be exported as goAML: ")


def _org_without_reference():
    from amlkit.db import connect
    conn = connect(os.environ["AMLKIT_DB"])
    org_id = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()["id"]
    conn.execute("UPDATE organizations SET goaml_entity_reference=NULL WHERE id=?", (org_id,))
    conn.commit()
    return conn, org_id


class TestEntityReferenceIsKeyedNotTextMatched:
    GAP_FREE = {"reporting_entity_name": "X", "reporter_name": "A", "reporter_email": "a@b.ae",
                "first_name": "F", "amount": "1", "transaction_type": "W",
                "source_account": "1", "destination_account": "2"}

    def test_error_carries_structured_key_and_label(self, client) -> None:
        from amlkit.reporting.goaml import (
            GoAMLValidationError, inject_reporting_entity, is_entity_reference_error)
        conn, org_id = _org_without_reference()
        try:
            inject_reporting_entity({"entity_reference": ""}, conn, org_id)
        except GoAMLValidationError as exc:
            assert exc.key == "entity_reference"
            assert "entity reference" in exc.label
            assert is_entity_reference_error(exc)
        else:
            raise AssertionError("expected GoAMLValidationError")
        finally:
            conn.close()

    def test_rewording_the_message_does_not_change_behaviour(self, client, monkeypatch) -> None:
        from amlkit.reporting import goaml
        conn, org_id = _org_without_reference()
        before = goaml.missing_export_fields(dict(self.GAP_FREE), conn, org_id)
        assert len(before) == 1 and "entity reference" in before[0]

        real = goaml.inject_reporting_entity

        def reworded(payload, db, org):
            try:
                real(payload, db, org)
            except goaml.GoAMLValidationError as exc:
                new = goaml.GoAMLValidationError("Org setup incomplete: no filing identifier.")
                new.key, new.label = exc.key, exc.label
                raise new from exc

        monkeypatch.setattr(goaml, "inject_reporting_entity", reworded)
        assert goaml.missing_export_fields(dict(self.GAP_FREE), conn, org_id) == before
        conn.close()

        # The export route reacts to the key too, not to the wording.
        rid = _insert_report("STR", {**TestFinaliseValidatesExport.COMPLETE,
                                     "report_type": "STR", "entity_reference": ""})
        x = client.get(f"/reports/{rid}/export")
        assert x.status_code == 400 and "Set your goAML entity reference" in x.text

    def test_unkeyed_error_mentioning_entity_reference_is_not_misclassified(self) -> None:
        from amlkit.reporting.goaml import GoAMLValidationError, is_entity_reference_error
        assert not is_entity_reference_error(
            GoAMLValidationError("goAML entity reference is mentioned but this is another error"))
        assert not is_entity_reference_error(ValueError("anything"))


# ------------------------------------------------------------ finalise contract

class TestFinaliseContract:
    def test_report_finalize_error_requires_db_and_org_id(self) -> None:
        import inspect
        from amlkit.cases.manager import report_finalize_error
        params = inspect.signature(report_finalize_error).parameters
        assert params["db"].default is inspect.Parameter.empty
        assert params["org_id"].default is inspect.Parameter.empty

    def test_mobile_finalise_of_unexportable_report_is_422_and_stays_draft(self, api) -> None:
        mclient, headers = api
        cid = mclient.post("/api/v1/customers", headers=headers, json={
            "reference": "CUST-422", "full_name": "Refused Subject",
        }).json()["customer_id"]
        body = {
            "customer_id": cid, "report_type": "STR",
            "reporting_entity_name": "Test Firm", "entity_reference": "TF-1",
            "reporter_name": "alice", "reporter_email": "alice@testfirm.ae",
            "first_name": "Refused", "last_name": "Subject",
            "reason_description": "narrative", "amount": 10, "transaction_type": "Wire",
            "source_account": "", "destination_account": "ACC-2",
        }
        rid = mclient.post("/api/v1/reports", headers=headers, json=body).json()["report_id"]

        r = mclient.post(f"/api/v1/reports/{rid}/submit", headers=headers)
        assert r.status_code == 422, r.text
        detail = r.json()["detail"]
        assert "source account number" in detail and "still a draft" in detail
        conn = sqlite3.connect(os.environ["AMLKIT_DB"])
        assert conn.execute("SELECT status FROM reports WHERE id=?", (rid,)).fetchone()[0] == "draft"

        # fixing the gap lets the same draft finalise
        mclient.post("/api/v1/reports", headers=headers,
                     json={**body, "report_id": rid, "source_account": "ACC-1"})
        r = mclient.post(f"/api/v1/reports/{rid}/submit", headers=headers)
        assert r.status_code == 200, r.text
        assert conn.execute("SELECT status FROM reports WHERE id=?", (rid,)).fetchone()[0] == "submitted"
        conn.close()

    def test_mobile_finalise_of_unsupported_type_is_422_with_the_distinct_message(self, api) -> None:
        mclient, headers = api
        rid = _insert_report("CTR", {"report_type": "CTR", "reporting_entity_name": "Test Firm"})
        r = mclient.post(f"/api/v1/reports/{rid}/submit", headers=headers)
        assert r.status_code == 422, r.text
        assert "This report cannot be exported as goAML" in r.json()["detail"]
