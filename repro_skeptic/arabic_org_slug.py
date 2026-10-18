"""Skeptic repro: register_organization derives the slug with [^a-z0-9]+ only, so every Arabic-only org name becomes
'org' and the second registration collides on the UNIQUE slug. Also shows a weak password is accepted (length-only check).
Scratch :memory: DB, mail left in console mode. Exit 0 only if the second Arabic org is refused and a weak password passes."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.pop("AMLKIT_SMTP_HOST", None)
from amlkit import db
from amlkit.cases.operators import register_organization
import inspect
c = db.connect(":memory:")
params = list(inspect.signature(register_organization).parameters)
def reg(org, email, pw="xxxxxxxxxx"):
    kw = dict(org_name=org, operator_name="Op", email=email, password=pw)
    try: register_organization(c, **{k: v for k, v in kw.items() if k in params}); return "created"
    except Exception as e: return f"{type(e).__name__}: {e}"
first = reg("شركة النور", "a@t.test"); second = reg("شركة الأمل", "b@t.test")
print("first :", first); print("second:", second)
print("slugs :", [r[0] for r in c.execute("select slug from organizations")])
sys.exit(0 if first == "created" and second.startswith("ValueError") else 1)
