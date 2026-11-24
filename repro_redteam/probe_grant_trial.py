"""Red-team 2026-11-24: PR #468 cases.operators.grant_trial (the logic behind POST /system/grant-trial). Called as a function on a scratch DB; the /system/* route itself is NOT called (standing rule). LOCAL ONLY."""
import sys, tempfile, logging, sqlite3, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT)); logging.disable(logging.CRITICAL)
from amlkit.db import connect
from amlkit.cases.operators import grant_trial
conn = connect(str(Path(tempfile.mkdtemp())/"t.db"))
PW = "Str0ng!Passw0rd"
def t(label, **kw):
    a = dict(org_name="Acme Co", operator_name="Ann", email="ann@acme.ae", password=PW, days=14); a.update(kw)
    try:
        r = grant_trial(conn, **a); print(f" OK   {label:42s} org={r['org_id']} ends={r['trial_ends_at']}")
    except Exception as e:
        print(f" ERR  {label:42s} {type(e).__name__}: {str(e)[:90]}")
print("== days"); 
for d in [1, 90, 0, 91, -5, True, False, 14.0, "14", None, 10**12, 2**63]:
    t(f"days={d!r}", days=d, org_name=f"D{abs(hash(repr(d)))}", email=f"d{abs(hash(repr(d)))}@x.ae")
print("== identity / uniqueness")
t("base"); t("same email again", org_name="Other Org")
t("email case variant", org_name="Other Org 2", email="ANN@acme.ae")
t("same org name, new email", email="b@acme.ae")
t("org slug collision 'ACME-co!'", org_name="ACME-co!", email="c@acme.ae")
t("weak password", password="short", org_name="W", email="w@acme.ae")
t("password 1MB", password="Aa1!"*250000, org_name="W2", email="w2@acme.ae")
t("CRLF in name", operator_name="Ann\r\nBcc: x@evil.test", org_name="C1", email="c1@acme.ae")
t("CRLF in email", email="c2@acme.ae\r\nBcc: x@evil.test", org_name="C2")
t("markup org", org_name="<script>alert(1)</script>", email="m@acme.ae")
t("5000-char org", org_name="Z"*5000, email="z@acme.ae")
t("blank org", org_name="  ", email="bl@acme.ae")
t("NUL in org", org_name="a\x00b", email="nul@acme.ae")
print("== resulting rows")
for r in conn.execute("select o.id,o.slug,o.plan,o.plan_status,o.trial_ends_at,(select count(*) from operators p where p.org_id=o.id) ops from organizations o"): print("  ", tuple(r))
print(" orphan orgs:", conn.execute("select count(*) from organizations o where not exists (select 1 from operators p where p.org_id=o.id)").fetchone()[0])
print(" audit actions:", [tuple(r) for r in conn.execute("select action,count(*) from audit_log group by action")])
# does a trial org actually get limits? billing off => check_limit no-op; with billing on => Starter limits
import os
from amlkit.billing import limits
org = conn.execute("select id from organizations limit 1").fetchone()[0]
for sw in ("", "1"):
    os.environ["AMLKIT_BILLING_ENABLED"] = sw; os.environ["STRIPE_SECRET_KEY"] = "sk_test_x" if sw else ""
    try: limits.check_limit(conn, org, "operators"); print(f" billing={sw or 'off'}: check_limit(operators) allowed")
    except Exception as e: print(f" billing={sw or 'off'}: refused {type(e).__name__}: {e}")
