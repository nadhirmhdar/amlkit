"""Red-team 2026-11-14: transactions accept any `direction` string (found via the web/mobile parity probe: direction='sideways' is stored). Does a non-standard direction
evade the KYT rules (structuring just under AED 55,000, large cash, velocity)? Same three cash amounts with direction 'in', 'out', 'sideways', 'IN', ''. LOCAL ONLY (needs fixtures/ from PR #412)."""
import json, os, shutil, sqlite3, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
ids = json.loads((ROOT/"fixtures"/"seed_ids.json").read_text()); B = ids["B"]
import logging; logging.disable(logging.CRITICAL)
from amlkit.cases import manager as M
from amlkit.db import connect, _reset_init_cache
for d in ["in", "out", "sideways", "IN", " in", "", "in;drop", "x"*500]:
    db = Path(tempfile.mkdtemp())/"s.db"; os.environ["AMLKIT_DB"] = str(db); shutil.copy(ROOT/"fixtures"/"seed.db", db); _reset_init_cache(); c = connect(db)
    res = []
    for amt in (54999, 54999, 54999):
        try: _, trig = M.record_transaction(c, B["customer_id"], B["org_id"], direction=d, method="cash", amount=amt, currency="AED", amount_aed=None, counterparty_name=None, counterparty_country=None, occurred_at=None, actor="probe"); res.append([getattr(t, "rule", t) for t in trig])
        except Exception as e: res.append(f"ERR {type(e).__name__}: {str(e)[:50]}")
    print(f" direction={d[:12]!r:16s} -> triggers per txn: {res}")
    c.close()
print("== evasion: split the same-direction aggregation by spelling the direction differently ==")
for label, dirs in [("control: in,in,in", ["in", "in", "in"]), ("in, IN, ' in'", ["in", "IN", " in"]), ("in, 'in.', 'in2'", ["in", "in.", "in2"]), ("in, '', 'x'", ["in", "", "x"])]:
    db = Path(tempfile.mkdtemp())/"s.db"; os.environ["AMLKIT_DB"] = str(db); shutil.copy(ROOT/"fixtures"/"seed.db", db); _reset_init_cache(); c = connect(db); seen = []
    for d in dirs:
        _, trig = M.record_transaction(c, B["customer_id"], B["org_id"], direction=d, method="cash", amount=54999, currency="AED", amount_aed=None, counterparty_name=None, counterparty_country=None, occurred_at=None, actor="probe"); seen += [t.rule_key for t in trig]
    print(f" {label:22s} -> rules fired over 3 x AED 54,999 cash: {seen or 'NONE'}"); c.close()
