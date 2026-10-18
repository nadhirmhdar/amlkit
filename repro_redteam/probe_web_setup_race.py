"""Red-team 2026-10-18: web /setup path (cases.operators.complete_initial_setup, the function POST /setup calls) -- double-claim race on one
setup token, existing-email handling, email-format check. LOCAL ONLY (needs fixtures/ from PR #412 make_seed)."""
import json, os, shutil, sqlite3, sys, tempfile, threading
from hashlib import sha256
from datetime import datetime, timezone, timedelta
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
ids = json.loads((ROOT/"fixtures"/"seed_ids.json").read_text()); B = ids["B"]
db = Path(tempfile.mkdtemp())/"s.db"; os.environ["AMLKIT_DB"] = str(db); shutil.copy(ROOT/"fixtures"/"seed.db", db)
import logging; logging.disable(logging.CRITICAL)
from amlkit.db import connect, _reset_init_cache
from amlkit.cases.operators import complete_initial_setup
_reset_init_cache(); connect(db).close()
def q(sql, *a):
    c = sqlite3.connect(db); r = c.execute(sql, a).fetchall(); c.commit(); c.close(); return r
def mk(raw):
    exp = (datetime.now(timezone.utc)+timedelta(days=1)).isoformat(timespec="seconds")
    q("insert into setup_tokens (org_id, token_hash, created_at, expires_at) values (?,?,?,?)", B["org_id"], sha256(raw.encode()).hexdigest(), exp, exp)
PW = "Str0ng!Passw0rd"
print("== 1. race: 20 threads, one token, own connection each ==")
mk("web-race"); out = []
def go(i):
    c = connect(db)
    try: complete_initial_setup(c, "web-race", f"W{i}", f"webrace{i}@x.ae", PW); out.append("ok")
    except Exception as e: out.append(type(e).__name__)
    finally: c.close()
th = [threading.Thread(target=go, args=(i,)) for i in range(20)]; [t.start() for t in th]; [t.join() for t in th]
print(" outcomes:", {k: out.count(k) for k in set(out)}, "| operators created from one token:", q("select count(*) from operators where email like 'webrace%@x.ae'")[0][0])
print("== 2. edge cases ==")
existing = q("select email from operators where org_id=?", B["org_id"])[0][0]
mk("web-dup")
try: _c=connect(db); complete_initial_setup(_c, "web-dup", "X", existing, PW); print(" existing email -> accepted?!")
except Exception as e: _c.rollback(); _c.close(); print(" existing email ->", type(e).__name__, "(route catches only ValueError)" if type(e).__name__ != "ValueError" else "")
if False:
  pass
mk("web-bad")
try: complete_initial_setup(connect(db), "web-bad", " ", "not-an-email", "alllowercase12"); print(" invalid email + blank name + weak pw -> accepted; operator exists:", bool(q("select 1 from operators where email='not-an-email'")))
except Exception as e: print(" invalid email ->", type(e).__name__, e)
