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

class TestCsrf:
    def test_org_profile_rejects_missing_token(self, client) -> None:
        r = client.post("/admin/org-profile",
                        data={**PROFILE, "goaml_entity_reference": "NO-CSRF"},
                        follow_redirects=False)
        assert r.status_code == 403
        assert _org_row()["goaml_entity_reference"] is None

    def test_org_profile_rejects_invalid_token(self, client) -> None:
        r = client.post("/admin/org-profile",
                        data={**PROFILE, "goaml_entity_reference": "BAD-CSRF",
                              "csrf_token": "not-the-token"},
                        follow_redirects=False)
        assert r.status_code == 403
        assert _org_row()["goaml_entity_reference"] is None

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

    def test_logout_rejects_missing_token(self, client) -> None:
        assert client.post("/logout", follow_redirects=False).status_code == 403
        assert client.get("/admin").status_code == 200  # still signed in

    def test_logout_rejects_invalid_token(self, client) -> None:
        r = client.post("/logout", data={"csrf_token": "forged"}, follow_redirects=False)
        assert r.status_code == 403
        assert client.get("/admin").status_code == 200

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
        bearer-token /system/* routes (and the CSRF-exempt auth callbacks
        listed explicitly below)."""
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

    def test_missing_export_fields_helper_matches_exporter(self) -> None:
        from amlkit.reporting.goaml import (
            GoAMLValidationError, missing_export_fields, serialize_goaml_xml)
        payload = {"reporting_entity_name": "X", "reporter_name": "A B",
                   "reporter_email": "a@b.ae", "first_name": "Ahmed",
                   "amount": "10", "transaction_type": "Wire"}
        assert missing_export_fields(payload) == [
            "source account number", "destination account number"]
        assert "source_account" not in payload  # input untouched
        payload.update(source_account="1", destination_account="2")
        assert missing_export_fields(payload) == []
        serialize_goaml_xml(payload)  # exporter agrees: no GoAMLValidationError
        assert GoAMLValidationError  # imported for the symmetry above
