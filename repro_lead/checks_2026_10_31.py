"""Lead 2026-10-31 checks. Temp-file SQLite DB and synthetic list entries only; no network.

Exit 0 when ALL THREE defects reproduce:
  FZ1  - a freeze obligation raised by a confirmed (true_positive) UAE-list match
         can be resolved as 'false_positive' with empty authority_ref and empty
         notes, never executed, by one MLRO. The alert stays true_positive.
         (cases/manager.py:1927-1933 allows it; no second approver.)
  FZ2  - 'authority_clearance' on an executed obligation is accepted with an
         empty authority_ref.
  FZR  - resolve_freeze_obligation is check-then-act: the status SELECT
         (manager.py:1917) and the UPDATE (manager.py:1944-1953, no
         "AND status != 'resolved'" guard) are separate, so two concurrent
         resolves both succeed and write two freeze.resolved audit rows.
         The race window is forced deterministically with a barrier after the
         SELECT; this shows the absence of a guard, not a timing claim.
Exit 1 when any is fixed (re-read the printed lines).
"""
import os, sys, tempfile, threading, sqlite3
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["AMLKIT_SINGLE_OPERATOR_MODE"] = "1"  # apply the disposition directly

from amlkit.db import connect, upsert_dataset, utcnow
from amlkit.names.arabic import blocking_keys, canonical_key
from amlkit.cases import manager
from amlkit.cases.review import propose_disposition

tmp = tempfile.mkdtemp()
DB = os.path.join(tmp, "fz.db")
c = connect(DB)
now = utcnow()
c.execute("INSERT INTO organizations (name,slug,status,created_at) VALUES ('t','t','active',?)", (now,))
c.execute("INSERT INTO operators (org_id,email,password_hash,name,role,is_active,created_at) "
          "VALUES (1,'m@t','x','Mona','mlro',1,?)", (now,))
op_id = c.execute("SELECT id FROM operators").fetchone()[0]
ds = upsert_dataset(c, "ae_local_terrorists", "UAE Local Terrorist List (synthetic)", is_mandatory=True)


def seed(name, src):
    eid = c.execute("""INSERT INTO entities (dataset_id, source_id, schema_type, caption, countries,
        birth_date, gender, topics, programs, raw, first_seen, last_seen)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ds, src, "Person", name, '["ae"]', None, "male", '["sanction"]', "[]", "{}", now, now)).lastrowid
    c.execute("INSERT INTO entity_names (entity_id,name,name_type,canonical_key,script) VALUES (?,?,?,?,?)",
              (eid, name, "primary", canonical_key(name), "latin"))
    for t in blocking_keys(name):
        c.execute("INSERT OR IGNORE INTO name_tokens (token,entity_id) VALUES (?,?)", (t, eid))
    return eid


NAMES = ["ZORAN SYNTHETIC KOVALENKO", "BORIS FICTIVE MALAKHOV", "IGOR PLACEHOLDER DRAGUNOV"]
eids = [seed(n, f"AE-SYN-{i}") for i, n in enumerate(NAMES)]
c.execute("UPDATE datasets SET last_refresh=?, entity_count=?", (now, len(NAMES)))
c.commit()

obligations = []
for i, (n, eid) in enumerate(zip(NAMES, eids)):
    manager.onboard(c, org_id=1, reference=f"C-{i}", full_name=n, actor="Mona")
    c.commit()
    a = c.execute("SELECT id FROM alerts WHERE org_id=1 AND entity_id=?", (eid,)).fetchone()
    if a is None:
        print(f"seed: no alert for {n} (check the seed)"); sys.exit(1)
    propose_disposition(c, a[0], org_id=1, status="true_positive", reason_code="confirmed_match",
                        operator="Mona", operator_id=op_id, narrative="Synthetic confirmed match")
    c.commit()
    fo = c.execute("SELECT id FROM freeze_obligations WHERE org_id=1 AND alert_id=?", (a[0],)).fetchone()
    if fo is None:
        print(f"seed: no freeze obligation for alert {a[0]}"); sys.exit(1)
    obligations.append((a[0], fo[0]))

# FZ1
alert1, fo1 = obligations[0]
manager.resolve_freeze_obligation(c, fo1, org_id=1, resolved_by="Mona",
                                  resolution_reason="false_positive", authority_ref="", notes="")
r = c.execute("SELECT status, executed_at, authority_ref, notes FROM freeze_obligations WHERE id=?", (fo1,)).fetchone()
astat = c.execute("SELECT status FROM alerts WHERE id=?", (alert1,)).fetchone()[0]
fz1 = r["status"] == "resolved" and r["executed_at"] is None and astat == "true_positive"
print(f"FZ1  unexecuted freeze resolved false_positive with empty ref/notes: status={r['status']} "
      f"executed_at={r['executed_at']} authority_ref={r['authority_ref']!r} notes={r['notes']!r}; "
      f"alert status still={astat!r} -> reproduces={fz1}")

# FZ2
alert2, fo2 = obligations[1]
manager.execute_freeze(c, fo2, org_id=1, executed_by="Mona",
                       assets_frozen=[{"type": "account", "ref": "SYN-1"}])
c.commit()
try:
    manager.resolve_freeze_obligation(c, fo2, org_id=1, resolved_by="Mona",
                                      resolution_reason="authority_clearance", authority_ref="", notes="")
    r2 = c.execute("SELECT status, authority_ref FROM freeze_obligations WHERE id=?", (fo2,)).fetchone()
    fz2 = r2["status"] == "resolved" and r2["authority_ref"] == ""
    print(f"FZ2  authority_clearance with empty authority_ref -> status={r2['status']} "
          f"authority_ref={r2['authority_ref']!r} -> reproduces={fz2}")
except ValueError as e:
    fz2 = False
    print(f"FZ2  authority_clearance with empty authority_ref refused: {e} -> reproduces=False")

# FZR: two connections, barrier after the status SELECT.
_, fo3 = obligations[2]
barrier = threading.Barrier(2, timeout=20)


class GatedConn:
    def __init__(self, real):
        self._real = real

    def execute(self, sql, *a, **kw):
        cur = self._real.execute(sql, *a, **kw)
        if sql.lstrip().upper().startswith("SELECT STATUS, EXECUTED_AT FROM FREEZE_OBLIGATIONS"):
            rows = cur.fetchall()
            barrier.wait()  # both threads have read 'pending_execution'

            class _C:
                def fetchone(self_inner):
                    return rows[0] if rows else None
            return _C()
        return cur

    def __enter__(self):
        return self._real.__enter__()

    def __exit__(self, *exc):
        return self._real.__exit__(*exc)

    def __getattr__(self, k):
        return getattr(self._real, k)


results = []


def worker(who):
    conn = connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        manager.resolve_freeze_obligation(GatedConn(conn), fo3, org_id=1, resolved_by=who,
                                          resolution_reason="false_positive", authority_ref=f"REF-{who}",
                                          notes=f"by {who}")
        results.append((who, "ok"))
    except Exception as e:  # noqa: BLE001
        results.append((who, f"{type(e).__name__}: {e}"))
    finally:
        conn.close()


ts = [threading.Thread(target=worker, args=(w,)) for w in ("MonaA", "MonaB")]
for t in ts:
    t.start()
for t in ts:
    t.join()
c2 = connect(DB)
n_audit = c2.execute("SELECT COUNT(*) FROM audit_log WHERE action='freeze.resolved' AND object_id=?",
                     (str(fo3),)).fetchone()[0]
final = c2.execute("SELECT resolved_by, authority_ref FROM freeze_obligations WHERE id=?", (fo3,)).fetchone()
fzr = sum(1 for _, r in results if r == "ok") == 2 and n_audit == 2
print(f"FZR  two concurrent resolves: results={sorted(results)} freeze.resolved audit rows={n_audit} "
      f"final resolved_by={final[0]!r} authority_ref={final[1]!r} -> reproduces={fzr}")

ok = fz1 and fz2 and fzr
print(f"{sum([fz1, fz2, fzr])}/3 reproduce")
sys.exit(0 if ok else 1)
