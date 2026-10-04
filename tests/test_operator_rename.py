"""MLRO rename of an operator's display name -- POST /admin/operators/{id}/rename.

There was no way to change an operator's name after creation, so a placeholder
name set when an account was provisioned stuck forever. The rename is
org-scoped (UNIQUE (org_id, name)), MLRO-only, CSRF-protected and audited.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test_admin_rbac import (  # noqa: E402,F401
    _add_operator, _csrf, _db, _register_and_login, client,
)


def _operator(email: str):
    conn = _db()
    try:
        return conn.execute(
            "SELECT id, org_id, name FROM operators WHERE email=?", (email,)
        ).fetchone()
    finally:
        conn.close()


def _rename(client, operator_id: int, name: str, **extra):
    return client.post(f"/admin/operators/{operator_id}/rename", data={
        "name": name, "csrf_token": _csrf(client), **extra,
    }, follow_redirects=True)


def _rename_audits(org_id: int):
    conn = _db()
    try:
        return conn.execute(
            "SELECT actor, detail, object_id FROM audit_log"
            " WHERE action='operator.rename' AND org_id=?", (org_id,)
        ).fetchall()
    finally:
        conn.close()


class TestRename:
    def test_mlro_renames_another_operator_and_it_is_audited(self, client) -> None:
        _add_operator(client, "YOUR NAME", "bob@testfirm.ae")
        bob = _operator("bob@testfirm.ae")

        r = _rename(client, bob["id"], "GROVISOR ADMIN")
        assert r.status_code == 200
        assert "Renamed YOUR NAME to GROVISOR ADMIN." in r.text

        assert _operator("bob@testfirm.ae")["name"] == "GROVISOR ADMIN"
        audits = _rename_audits(bob["org_id"])
        assert len(audits) == 1
        assert audits[0]["actor"] == "alice"
        assert audits[0]["object_id"] == str(bob["id"])
        assert json.loads(audits[0]["detail"]) == {"from": "YOUR NAME", "to": "GROVISOR ADMIN"}

    def test_new_name_shows_on_the_admin_page(self, client) -> None:
        _add_operator(client, "YOUR NAME", "bob@testfirm.ae")
        _rename(client, _operator("bob@testfirm.ae")["id"], "GROVISOR ADMIN")
        page = client.get("/admin").text
        assert "GROVISOR ADMIN" in page
        assert "YOUR NAME" not in page

    def test_mlro_can_rename_themselves(self, client) -> None:
        alice = _operator("alice@testfirm.ae")
        r = _rename(client, alice["id"], "Alice Admin")
        assert "Renamed alice to Alice Admin." in r.text
        assert _operator("alice@testfirm.ae")["name"] == "Alice Admin"

    def test_whitespace_is_trimmed_and_collapsed(self, client) -> None:
        _add_operator(client, "bob", "bob@testfirm.ae")
        _rename(client, _operator("bob@testfirm.ae")["id"], "  Grovisor    Admin  ")
        assert _operator("bob@testfirm.ae")["name"] == "Grovisor Admin"

    def test_unchanged_name_is_a_noop_with_no_audit_entry(self, client) -> None:
        _add_operator(client, "bob", "bob@testfirm.ae")
        bob = _operator("bob@testfirm.ae")
        r = _rename(client, bob["id"], "bob")
        assert "That is already this operator" in r.text  # apostrophe is HTML-escaped
        assert _rename_audits(bob["org_id"]) == []


class TestRefusals:
    def test_name_taken_by_another_operator_in_the_org_is_refused(self, client) -> None:
        _add_operator(client, "bob", "bob@testfirm.ae")
        bob = _operator("bob@testfirm.ae")
        r = _rename(client, bob["id"], "alice")
        assert "already has that name" in r.text
        assert _operator("bob@testfirm.ae")["name"] == "bob"
        assert _rename_audits(bob["org_id"]) == []

    def test_blank_name_is_refused(self, client) -> None:
        _add_operator(client, "bob", "bob@testfirm.ae")
        r = _rename(client, _operator("bob@testfirm.ae")["id"], "   ")
        assert "Enter a name." in r.text
        assert _operator("bob@testfirm.ae")["name"] == "bob"

    def test_over_long_name_is_refused(self, client) -> None:
        _add_operator(client, "bob", "bob@testfirm.ae")
        r = _rename(client, _operator("bob@testfirm.ae")["id"], "x" * 81)
        assert "80 characters or fewer" in r.text
        assert _operator("bob@testfirm.ae")["name"] == "bob"

    def test_exactly_80_characters_is_allowed(self, client) -> None:
        _add_operator(client, "bob", "bob@testfirm.ae")
        _rename(client, _operator("bob@testfirm.ae")["id"], "x" * 80)
        assert _operator("bob@testfirm.ae")["name"] == "x" * 80

    def test_unknown_operator_id_is_refused(self, client) -> None:
        r = _rename(client, 999999, "Whoever")
        assert "Operator not found." in r.text


class TestAccessControl:
    def test_officer_gets_403_and_nothing_changes(self, client) -> None:
        _add_operator(client, "bob", "bob@testfirm.ae", role="officer")
        _add_operator(client, "carol", "carol@testfirm.ae", role="officer")
        carol = _operator("carol@testfirm.ae")

        client.cookies.delete("amlkit_session")
        client.post("/login", data={
            "email": "bob@testfirm.ae", "password": "a-strong-password-2",
            "csrf_token": _csrf(client),
        })
        r = client.post(f"/admin/operators/{carol['id']}/rename", data={
            "name": "Hijacked", "csrf_token": _csrf(client),
        }, follow_redirects=False)
        assert r.status_code == 403
        assert _operator("carol@testfirm.ae")["name"] == "carol"

    def test_missing_csrf_token_is_rejected(self, client) -> None:
        _add_operator(client, "bob", "bob@testfirm.ae")
        bob = _operator("bob@testfirm.ae")
        r = client.post(f"/admin/operators/{bob['id']}/rename",
                        data={"name": "No CSRF"}, follow_redirects=False)
        assert r.status_code == 403
        assert _operator("bob@testfirm.ae")["name"] == "bob"

    def test_signed_out_request_redirects_to_login(self, client) -> None:
        _add_operator(client, "bob", "bob@testfirm.ae")
        bob = _operator("bob@testfirm.ae")
        client.cookies.delete("amlkit_session")
        r = client.post(f"/admin/operators/{bob['id']}/rename",
                        data={"name": "Anon", "csrf_token": _csrf(client)},
                        follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/login"
        assert _operator("bob@testfirm.ae")["name"] == "bob"

    def test_cannot_rename_an_operator_in_another_organisation(self, client) -> None:
        from fastapi.testclient import TestClient
        from amlkit.api.app import app

        other = TestClient(app)
        _register_and_login(other, "Other Firm", "zed", "zed@otherfirm.ae")
        zed = _operator("zed@otherfirm.ae")

        r = _rename(client, zed["id"], "Taken Over")
        assert "Operator not found." in r.text
        assert _operator("zed@otherfirm.ae")["name"] == "zed"
        assert _rename_audits(zed["org_id"]) == []
