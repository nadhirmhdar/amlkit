"""Customer detail page: identity details read as people expect."""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test_api import client  # noqa: E402,F401


def _onboard(**kw) -> int:
    from amlkit.cases.manager import onboard
    from amlkit.db import connect
    conn = connect(os.environ["AMLKIT_DB"])
    try:
        org_id = conn.execute("SELECT id FROM organizations ORDER BY id LIMIT 1").fetchone()[0]
        return onboard(conn, org_id=org_id, reference="C-1", full_name="Layla Haddad", actor="test", **kw).customer_id
    finally:
        conn.close()


def test_nationalities_show_as_codes_not_json(client) -> None:
    cid = _onboard(nationalities=["AE", "GB"])
    html = client.get(f"/customers/{cid}").text
    assert "AE, GB" in html
    assert '["AE", "GB"]' not in html and "[&#34;AE&#34;" not in html


def test_empty_tax_residencies_are_hidden(client) -> None:
    cid = _onboard(nationalities=["AE"])
    html = client.get(f"/customers/{cid}").text
    assert "Tax residencies" not in html


def test_ownership_label_is_spelled_out(client) -> None:
    cid = _onboard(nationalities=["AE"])
    assert "Ownership %" in client.get(f"/customers/{cid}").text


def test_code_list_handles_odd_stored_values() -> None:
    from amlkit.api.app import _code_list
    assert _code_list('["AE", "GB"]') == "AE, GB"
    assert _code_list(["AE", " ", "GB"]) == "AE, GB"
    assert _code_list("[]") == "" and _code_list(None) == "" and _code_list("") == ""
    assert _code_list("AE") == "AE"          # legacy plain string
    assert _code_list('"AE"') == "AE"
