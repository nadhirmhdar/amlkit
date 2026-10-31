"""Freeze obligation scope (L-38, L-39) and resolution controls (L-95, L-96, L-97).

Only UN Security Council and UAE-local (EOCN) list matches raise a freeze
obligation / email / CNMR. EU, UK and OFAC-only confirmed matches stay alerts.
"""
import os
import sqlite3
import tempfile

import pytest

from amlkit.cases import manager
from amlkit.cases.review import propose_disposition
from amlkit.db import connect, upsert_dataset, utcnow
from amlkit.names.arabic import blocking_keys, canonical_key
from amlkit.sanctions_scope import freeze_obligation_in_scope, is_uae_freeze_list


@pytest.fixture(autouse=True)
def _single_operator(monkeypatch):
    monkeypatch.setenv("AMLKIT_SINGLE_OPERATOR_MODE", "1")


@pytest.fixture
def env():
    from amlkit.match import cache
    cache._token_cache.clear()  # process-global token -> entity cache
    c = connect(os.path.join(tempfile.mkdtemp(), "fz.db"))
    c.row_factory = sqlite3.Row
    now = utcnow()
    c.execute("INSERT INTO organizations (name,slug,status,created_at) VALUES ('t','t','active',?)", (now,))
    c.execute("INSERT INTO operators (org_id,email,password_hash,name,role,is_active,created_at) "
              "VALUES (1,'m@t','x','Mona','mlro',1,?)", (now,))
    op_id = c.execute("SELECT id FROM operators").fetchone()[0]
    # A fresh mandatory UAE list so onboarding passes the freshness gate.
    upsert_dataset(c, "ae_local_terrorists", "UAE Local Terrorist List (synthetic)", is_mandatory=True)
    c.execute("UPDATE datasets SET last_refresh=?, entity_count=1", (now,))
    c.commit()
    return c, op_id


def _seed(c, dataset_key, name, ref, programs="[]"):
    now = utcnow()
    ds = upsert_dataset(c, dataset_key, dataset_key + " (synthetic)", is_mandatory=(dataset_key == "ae_local_terrorists"))
    eid = c.execute(
        """INSERT INTO entities (dataset_id, source_id, schema_type, caption, countries,
           birth_date, gender, topics, programs, raw, first_seen, last_seen)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ds, "SYN-" + ref, "Person", name, '["ae"]', None, "male", '["sanction"]', programs, "{}", now, now),
    ).lastrowid
    c.execute("INSERT INTO entity_names (entity_id,name,name_type,canonical_key,script) VALUES (?,?,?,?,?)",
              (eid, name, "primary", canonical_key(name), "latin"))
    for t in blocking_keys(name):
        c.execute("INSERT OR IGNORE INTO name_tokens (token,entity_id) VALUES (?,?)", (t, eid))
    c.execute("UPDATE datasets SET last_refresh=?, entity_count=1 WHERE id=?", (now, ds))
    c.commit()
    return eid


def _confirm(c, op_id, eid, name, ref):
    manager.onboard(c, org_id=1, reference=ref, full_name=name, actor="Mona")
    c.commit()
    alert = c.execute("SELECT id FROM alerts WHERE org_id=1 AND entity_id=?", (eid,)).fetchone()
    assert alert is not None
    propose_disposition(c, alert[0], org_id=1, status="true_positive", reason_code="confirmed_match",
                        operator="Mona", operator_id=op_id, narrative="Synthetic confirmed match")
    c.commit()
    return alert[0]


def _confirmed_match(c, op_id, dataset_key, name, ref, programs="[]"):
    return _confirm(c, op_id, _seed(c, dataset_key, name, ref, programs), name, ref)


def _obligations(c):
    return [dict(r) for r in c.execute("SELECT * FROM freeze_obligations WHERE org_id=1")]


def test_helper_scope():
    assert is_uae_freeze_list("un_consolidated")
    assert is_uae_freeze_list("un_sc_sanctions")
    assert is_uae_freeze_list("ae_local_terrorists")
    assert is_uae_freeze_list("eocn_anything")
    for k in ("ofac_sdn", "us_ofac_sdn", "eu_sanctions", "uk_sanctions", "interpol_red_notices", "", None):
        assert not is_uae_freeze_list(k)


def test_ofac_adapter_not_mandatory():
    from amlkit.ingest.ofac import OFACSDNAdapter
    assert OFACSDNAdapter().is_mandatory is False


@pytest.mark.parametrize("key", ["eu_sanctions", "ofac_sdn", "uk_sanctions"])
def test_non_uae_list_true_positive_raises_no_freeze(env, key):
    c, op_id = env
    alert_id = _confirmed_match(c, op_id, key, "ZORAN SYNTHETIC KOVALENKO", "C-1")
    assert c.execute("SELECT status FROM alerts WHERE id=?", (alert_id,)).fetchone()[0] == "true_positive"
    assert _obligations(c) == []


@pytest.mark.parametrize("key", ["un_consolidated", "ae_local_terrorists"])
def test_uae_list_true_positive_raises_freeze(env, key):
    c, op_id = env
    alert_id = _confirmed_match(c, op_id, key, "BORIS FICTIVE MALAKHOV", "C-2")
    rows = _obligations(c)
    assert len(rows) == 1 and rows[0]["alert_id"] == alert_id
    assert rows[0]["status"] == "pending_execution"
    assert freeze_obligation_in_scope(c, rows[0]["id"], 1)


def test_legacy_out_of_scope_obligation_gets_no_overdue_email(env, monkeypatch):
    """An obligation raised earlier from an EU-only alert: no 24h clock, no email."""
    c, op_id = env
    # Disposition under a UN list so an obligation exists, then point it at an EU alert.
    e_un = _seed(c, "un_consolidated", "IGOR PLACEHOLDER DRAGUNOV", "C-3")
    e_eu = _seed(c, "eu_sanctions", "ANTON SYNTHETIC VOLKOV", "C-4")
    _confirm(c, op_id, e_un, "IGOR PLACEHOLDER DRAGUNOV", "C-3")
    eu_alert = _confirm(c, op_id, e_eu, "ANTON SYNTHETIC VOLKOV", "C-4")
    fo = _obligations(c)[0]
    c.execute("UPDATE freeze_obligations SET alert_id=?, identified_at='2020-01-01T00:00:00+00:00' WHERE id=?",
              (eu_alert, fo["id"]))
    c.commit()
    sent = []
    from amlkit import mail
    monkeypatch.setattr(mail, "send_freeze_obligation_alert", lambda **kw: sent.append(kw) or mail.SENT)
    result = manager.check_unexecuted_freeze_obligations(c, 1)
    assert sent == []
    assert result == []


# --------------------------------------------------------------- resolution controls
def _two_freezes(env):
    c, op_id = env
    e1 = _seed(c, "ae_local_terrorists", "ZORAN SYNTHETIC KOVALENKO", "C-10")
    e2 = _seed(c, "ae_local_terrorists", "BORIS FICTIVE MALAKHOV", "C-11")
    a1 = _confirm(c, op_id, e1, "ZORAN SYNTHETIC KOVALENKO", "C-10")
    a2 = _confirm(c, op_id, e2, "BORIS FICTIVE MALAKHOV", "C-11")
    f = {r["alert_id"]: r["id"] for r in _obligations(c)}
    return c, op_id, (a1, f[a1]), (a2, f[a2])


def _resolve(c, fid, **kw):
    kw.setdefault("authority_ref", "")
    kw.setdefault("notes", "")
    return manager.resolve_freeze_obligation(c, fid, org_id=1, resolved_by="Mona", **kw)


def test_false_positive_requires_notes(env):
    c, op_id, (a1, f1), _ = _two_freezes(env)
    c.execute("UPDATE alerts SET status='false_positive' WHERE id=?", (a1,))  # alert re-dispositioned
    c.commit()
    with pytest.raises(ValueError, match="20 characters"):
        _resolve(c, f1, resolution_reason="false_positive", notes="   too short  ")
    assert c.execute("SELECT status FROM freeze_obligations WHERE id=?", (f1,)).fetchone()[0] == "pending_execution"


def test_authority_clearance_requires_ref(env):
    c, op_id, _, (a2, f2) = _two_freezes(env)
    manager.execute_freeze(c, f2, org_id=1, executed_by="Mona", assets_frozen=[{"type": "account", "ref": "S-1"}])
    c.commit()
    with pytest.raises(ValueError, match="authority"):
        _resolve(c, f2, resolution_reason="authority_clearance", authority_ref="   ")
    _resolve(c, f2, resolution_reason="authority_clearance", authority_ref="  EOCN-2026-001 ")
    r = c.execute("SELECT authority_ref FROM freeze_obligations WHERE id=?", (f2,)).fetchone()
    assert r[0] == "EOCN-2026-001"


def test_false_positive_refused_while_alert_is_true_positive(env):
    c, op_id, (a1, f1), _ = _two_freezes(env)
    with pytest.raises(ValueError, match="Re-disposition the alert"):
        _resolve(c, f1, resolution_reason="false_positive",
                 notes="The customer is a different person with the same name.")
    assert c.execute("SELECT status FROM freeze_obligations WHERE id=?", (f1,)).fetchone()[0] == "pending_execution"


def test_false_positive_allowed_after_alert_redisposition(env):
    c, op_id, (a1, f1), _ = _two_freezes(env)
    c.execute("UPDATE alerts SET status='false_positive' WHERE id=?", (a1,))
    c.commit()
    _resolve(c, f1, resolution_reason="false_positive",
             notes="Alert re-dispositioned: different date of birth and nationality.")
    assert c.execute("SELECT status FROM freeze_obligations WHERE id=?", (f1,)).fetchone()[0] == "resolved"


def test_second_resolve_refused_one_audit_row(env):
    c, op_id, _, (a2, f2) = _two_freezes(env)
    manager.execute_freeze(c, f2, org_id=1, executed_by="Mona", assets_frozen=[{"type": "account", "ref": "S-1"}])
    c.commit()
    _resolve(c, f2, resolution_reason="delisted", authority_ref="UN-DELIST-1")
    with pytest.raises(ValueError, match="already resolved"):
        _resolve(c, f2, resolution_reason="delisted", authority_ref="UN-DELIST-2")
    n = c.execute("SELECT COUNT(*) FROM audit_log WHERE action='freeze.resolved' AND object_id=?",
                  (str(f2),)).fetchone()[0]
    assert n == 1


def test_update_guard_blocks_stale_read(env, monkeypatch):
    """Even if the status SELECT saw 'pending', the guarded UPDATE refuses a resolved row."""
    c, op_id, _, (a2, f2) = _two_freezes(env)
    manager.execute_freeze(c, f2, org_id=1, executed_by="Mona", assets_frozen=[{"type": "account", "ref": "S-1"}])
    c.commit()
    real = c.execute("SELECT 1").connection  # same connection
    # Simulate the concurrent winner: resolve the row after our SELECT but before our UPDATE.
    orig = manager.audit
    state = {"done": False}

    class Proxy:
        def __init__(self, inner):
            self._i = inner

        def execute(self, sql, *a, **k):
            cur = self._i.execute(sql, *a, **k)
            if sql.lstrip().upper().startswith("SELECT F.STATUS") and not state["done"]:
                state["done"] = True
                self._i.execute("UPDATE freeze_obligations SET status='resolved' WHERE id=?", (f2,))
            return cur

        def __enter__(self):
            return self._i.__enter__()

        def __exit__(self, *a):
            return self._i.__exit__(*a)

        def __getattr__(self, n):
            return getattr(self._i, n)

    with pytest.raises(ValueError, match="already resolved"):
        manager.resolve_freeze_obligation(Proxy(c), f2, org_id=1, resolved_by="Mona",
                                          resolution_reason="delisted", authority_ref="X")


# --------------------------------------------------------------- HTTP routes
from test_api import client, _csrf  # noqa: E402,F401


def _seed_route_freeze(dataset_key, alert_status, fstatus="executed_pending_report"):
    from amlkit.db import utcnow as _now
    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    conn.row_factory = sqlite3.Row
    org_id = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()["id"]
    now = _now()
    ds = conn.execute("INSERT INTO datasets (key, title) VALUES (?, ?)", (dataset_key, dataset_key)).lastrowid
    eid = conn.execute(
        "INSERT INTO entities (dataset_id, source_id, schema_type, caption, topics, programs, first_seen, last_seen)"
        " VALUES (?, 'S1', 'Person', 'SYN PERSON', '[\"sanction\"]', '[]', ?, ?)", (ds, now, now)).lastrowid
    cid = conn.execute(
        "INSERT INTO customers (org_id, reference, full_name, customer_type, canonical_key, status,"
        " onboarded_at, created_at, updated_at) VALUES (?, 'C-RT', 'Syn Person', 'natural', 'syn person',"
        " 'active', ?, ?, ?)", (org_id, now, now, now)).lastrowid
    sid = conn.execute(
        "INSERT INTO screenings (org_id, customer_id, query_name, trigger, algorithm, threshold, run_at)"
        " VALUES (?, ?, 'Syn Person', 'onboarding', 'x', 0.8, ?)", (org_id, cid, now)).lastrowid
    aid = conn.execute(
        "INSERT INTO alerts (org_id, screening_id, entity_id, score, score_detail, matched_name, status, created_at)"
        " VALUES (?, ?, ?, 1.0, '{}', 'SYN PERSON', ?, ?)", (org_id, sid, eid, alert_status, now)).lastrowid
    fid = conn.execute(
        "INSERT INTO freeze_obligations (org_id, customer_id, alert_id, obligation_type, risk_category, status,"
        " identified_at, identified_by, executed_at, executed_by) VALUES (?, ?, ?, 'sanctions', 'high', ?, ?, 'a', ?, 'a')",
        (org_id, cid, aid, fstatus, now, now)).lastrowid
    conn.commit()
    conn.close()
    return fid


def test_cnmr_route_refuses_eu_only_obligation(client):
    fid = _seed_route_freeze("eu_sanctions", "true_positive")
    r = client.post(f"/freeze-obligations/{fid}/file-ffr",
                    data={"csrf_token": _csrf(client), "reporter_name": "M", "reporter_email": "m@t.test"},
                    follow_redirects=False)
    assert r.status_code == 303 and "/reports/" not in r.headers["location"]
    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    assert conn.execute("SELECT report_id FROM freeze_obligations WHERE id=?", (fid,)).fetchone()[0] is None
    assert conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0] == 0


def test_resolve_route_shows_validation_error(client):
    fid = _seed_route_freeze("un_consolidated", "true_positive", fstatus="pending_execution")
    r = client.post(f"/freeze-obligations/{fid}/resolve",
                    data={"csrf_token": _csrf(client), "resolution_reason": "false_positive",
                          "notes": "x" * 30},
                    follow_redirects=True)
    assert r.status_code == 200
    assert "Re-disposition the alert" in r.text
    r2 = client.post(f"/freeze-obligations/{fid}/resolve",
                     data={"csrf_token": _csrf(client), "resolution_reason": "false_positive", "notes": ""},
                     follow_redirects=True)
    assert "at least 20 characters" in r2.text
