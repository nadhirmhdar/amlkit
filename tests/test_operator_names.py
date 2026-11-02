"""O1: operator names are normalised, and look-alikes / reserved actors refused.

Probes (red-team 1 Nov): a Cyrillic homoglyph copy of an existing name, a
trailing zero-width space, and the reserved audit actor name `system`. Covered
on every write path to operators.name: admin create, admin rename, setup-token
claim, provision_operator and register_organization.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit import auth, db as dbm  # noqa: E402
from amlkit.cases import operators as ops  # noqa: E402
from amlkit.names.confusables import fold_confusables  # noqa: E402
from test_api import client, _csrf, _db  # noqa: E402,F401

CYR_A = "а"          # Cyrillic a
ZWSP = "​"
GOOD_PW = "A-strong-password-2"


# ------------------------------------------------------------------ unit
def test_fold_confusables():
    assert fold_confusables("\u03bf\u0440\u0435\u0440") == "opep"  # Greek o; Cyrillic r/e/r look-alikes
    assert fold_confusables(f"{CYR_A}lice") == "alice"
    assert fold_confusables("οрер") == "oрep".replace("р", "p")  # Greek o, Cyrillic р/е
    assert fold_confusables("") == "" and fold_confusables(None) == ""


@pytest.mark.parametrize("raw,expected", [
    (f"Bob{ZWSP}", "Bob"),
    ("​Bo‌b‍﻿", "Bob"),
    ("‮Bob‬", "Bob"),
    ("⁦Bob⁩", "Bob"),
    ("Ｂob", "Bob"),            # fullwidth B -> NFKC
    ("  Bob   Smith ", "Bob Smith"),
])
def test_clean_name(raw, expected):
    assert auth.check_operator_identity(raw)[0] == expected


@pytest.mark.parametrize("raw", ["", "   ", ZWSP, "​‌‍﻿", "‪‮⁦⁩"])
def test_empty_after_strip_rejected(raw):
    with pytest.raises(auth.IdentityError):
        auth.check_operator_identity(raw)


@pytest.mark.parametrize("raw", [
    "system", "System", "SYSTEM", f"system{ZWSP}", "s​y​stem",
    "ѕystem",                       # Cyrillic dze
    "systеm",                       # Cyrillic e
    "scheduler", "cloud-scheduler", "stripe",
    "system:scheduled-refresh", "system:anything", "SYSTEM:x",
])
def test_reserved_names_rejected(raw):
    with pytest.raises(auth.IdentityError, match="reserved"):
        auth.check_operator_identity(raw)


def test_ordinary_names_still_accepted():
    for n in ("alice", "Systems Admin", "Fatima Al Mansoori", "محمد"):
        assert auth.check_operator_identity(n)[0] == n


# ------------------------------------------------------------ db level
@pytest.fixture()
def c():
    conn = dbm.connect(":memory:")
    now = dbm.utcnow()
    conn.execute("INSERT INTO organizations (name,slug,status,created_at) VALUES ('One','one','active',?)", (now,))
    conn.execute("INSERT INTO organizations (name,slug,status,created_at) VALUES ('Two','two','active',?)", (now,))
    conn.commit()
    return conn


def _op(conn, name, org_id=1):
    now = dbm.utcnow()
    cur = conn.execute(
        "INSERT INTO operators (org_id,email,password_hash,name,role,is_active,email_verified_at,created_at)"
        " VALUES (?,?,?,?,?,1,?,?)",
        (org_id, f"{abs(hash(name))}@x.test", "x", name, "mlro", now, now))
    conn.commit()
    return cur.lastrowid


def test_taken_detects_homoglyph_and_zero_width(c):
    _op(c, "alice")
    assert ops.operator_name_taken(c, 1, f"{CYR_A}lice")
    assert ops.operator_name_taken(c, 1, f"alice{ZWSP}")
    assert ops.operator_name_taken(c, 1, "ALICE")
    assert not ops.operator_name_taken(c, 2, f"{CYR_A}lice")  # other org: fine
    assert not ops.operator_name_taken(c, 1, "alicia")


def test_taken_sees_existing_stored_lookalike(c):
    _op(c, f"{CYR_A}lice")  # stored before the rule existed
    assert ops.operator_name_taken(c, 1, "alice")


def test_rename_rejects_lookalike_zwsp_reserved(c):
    _op(c, "alice")
    bob = _op(c, "bob")
    for bad in (f"{CYR_A}lice", f"alice{ZWSP}", "system", "System​"):
        with pytest.raises(ValueError):
            ops.rename_operator(c, bob, 1, bad)
    assert c.execute("SELECT name FROM operators WHERE id=?", (bob,)).fetchone()[0] == "bob"
    r = ops.rename_operator(c, bob, 1, f"Robert{ZWSP}")
    assert r["new_name"] == "Robert"
    assert c.execute("SELECT name FROM operators WHERE id=?", (bob,)).fetchone()[0] == "Robert"


def test_provision_operator_refuses_lookalike_and_reserved(c):
    _op(c, "alice")
    for bad in (f"{CYR_A}lice", "system"):
        with pytest.raises(ValueError):
            ops.provision_operator(c, bad, "n@x.test", GOOD_PW, "officer", org_slug="one")


def test_register_organization_refuses_reserved(c):
    with pytest.raises(ValueError):
        ops.register_organization(c, "Fresh Org", "system", "f@x.test", GOOD_PW)


def _setup_token(conn, raw, org_id=1):
    exp = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(timespec="seconds")
    conn.execute("INSERT INTO setup_tokens (org_id, token_hash, created_at, expires_at) VALUES (?,?,?,?)",
                 (org_id, sha256(raw.encode()).hexdigest(), exp, exp))
    conn.commit()


def test_setup_token_claim_refuses_lookalike_zwsp_reserved_and_keeps_token(c):
    _op(c, "alice")
    _setup_token(c, "tok")
    for bad in (f"{CYR_A}lice", f"alice{ZWSP}", "system", ZWSP):
        with pytest.raises(ValueError):
            ops.complete_initial_setup(c, "tok", bad, "new@x.test", GOOD_PW)
    # Token not burned by the refusals; a clean name still works, normalised.
    out = ops.complete_initial_setup(c, "tok", f"Carol{ZWSP}", "new@x.test", GOOD_PW)
    assert c.execute("SELECT name FROM operators WHERE id=?", (out["operator_id"],)).fetchone()[0] == "Carol"


# ------------------------------------------------------------------ HTTP
def _create(client, name, email):
    return client.post("/admin/operators", data={
        "name": name, "email": email, "password": GOOD_PW, "role": "officer",
        "csrf_token": _csrf(client)}, follow_redirects=True)


def _names():
    conn = _db()
    try:
        return [r[0] for r in conn.execute("SELECT name FROM operators ORDER BY id")]
    finally:
        conn.close()


def test_admin_create_refuses_probes_and_normalises(client):
    for i, bad in enumerate((f"{CYR_A}lice", f"alice{ZWSP}", "system", "System", ZWSP)):
        _create(client, bad, f"bad{i}@testfirm.ae")
    assert _names() == ["alice"]
    _create(client, f"Dave{ZWSP}", "dave@testfirm.ae")
    assert _names() == ["alice", "Dave"]


def test_admin_rename_refuses_probes(client):
    _create(client, "bob", "bob@testfirm.ae")
    conn = _db()
    bob = conn.execute("SELECT id FROM operators WHERE name='bob'").fetchone()[0]
    conn.close()
    for bad in (f"{CYR_A}lice", f"alice{ZWSP}", "system"):
        client.post(f"/admin/operators/{bob}/rename", data={
            "name": bad, "csrf_token": _csrf(client)}, follow_redirects=True)
    assert _names() == ["alice", "bob"]
    client.post(f"/admin/operators/{bob}/rename", data={
        "name": f"Robert{ZWSP}", "csrf_token": _csrf(client)}, follow_redirects=True)
    assert _names() == ["alice", "Robert"]
