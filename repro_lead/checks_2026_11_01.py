"""Lead 2026-11-01 checks on master 11a3527. :memory: SQLite, synthetic data, no network.

Exit 0 when ALL FIVE still reproduce:
  CR25 - auth.mfa_verify: hmac.compare_digest(str, str) on a user-supplied TOTP
         code (auth.py:815). A non-ASCII code (Arabic-Indic digits) raises
         TypeError -> HTTP 500 on /mfa/verify instead of "Invalid code".
  CR26 - auth.csrf_valid: secrets.compare_digest(str, str) (auth.py:744).
         A non-ASCII csrf_token raises TypeError -> 500 instead of 403.
  CR24 - billing.stripe_client.verify_webhook_signature (stripe_client.py:195)
         raises TypeError, not SignatureError, for a non-ASCII v1 value ->
         500 on /billing/webhook (only when Stripe is configured).
  A1r  - residual lockout DoS: 8 wrong passwords from anyone lock the account
         for 15 minutes and the owner's correct password is refused.
         (#435 fixed the never-resetting counter; this part is by design
         of a per-account lock and needs a product decision.)
  CS19 - operator-facing "freeze" wording for every sanctions hit regardless
         of list (screening/pf.py obligation_note, api/app.py onboarding note),
         while #433 limits freeze obligations to UN / UAE-local lists.
Exit 1 when any is fixed (re-read the printed lines).
"""
import os, sys
from datetime import datetime, timezone
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from amlkit import auth, db as dbm
from amlkit.billing import stripe_client
from amlkit.screening import pf

ok = 0
NONASCII_CODE = "١٢٣٤٥٦"  # Arabic-Indic 123456


def probe(fn):
    try:
        return repr(fn())
    except Exception as e:  # noqa: BLE001
        return type(e).__name__


# CR25
c = dbm.connect(":memory:"); now = dbm.utcnow()
c.execute("INSERT INTO organizations (name,slug,status,created_at) VALUES ('t','t','active',?)", (now,))
c.execute("INSERT INTO operators (org_id,email,password_hash,name,role,is_active,email_verified_at,created_at)"
          " VALUES (1,'mlro@t.test',?,'M','mlro',1,?,?)", (auth.hash_password("Correct#Horse9"), now, now))
c.execute("INSERT INTO mfa_secrets (operator_id,secret,enrolled_at,confirmed_at) VALUES (1,'JBSWY3DPEHPK3PXP',?,?)",
          (now, now))
c.commit()
r = probe(lambda: auth.mfa_verify(c, 1, NONASCII_CODE, confirmed_only=True))
cr25 = r == "TypeError"
print(f"CR25 mfa_verify(code={NONASCII_CODE!r}) -> {r} -> reproduces={cr25}")
ok += cr25

# CR26
r = probe(lambda: auth.csrf_valid("abc123", "abcé"))
cr26 = r == "TypeError"
print(f"CR26 csrf_valid('abc123', 'abc\\u00e9') -> {r} -> reproduces={cr26}")
ok += cr26

# CR24
r = probe(lambda: stripe_client.verify_webhook_signature(b"{}", "t=100,v1=é", "whsec_test", now=100))
cr24 = r == "TypeError"
print(f"CR24 verify_webhook_signature(header 't=100,v1=\\u00e9') -> {r} (SignatureError would be a 400) "
      f"-> reproduces={cr24}")
ok += cr24


# A1r
def attempt(pw):
    try:
        auth.login(c, "mlro@t.test", pw); return "OK"
    except auth.AuthError as e:
        return str(e)[:40]


for _ in range(auth.MAX_FAILED_LOGINS):
    attempt("wrong-guess")
lock = c.execute("SELECT failed_login_count, locked_until FROM operators WHERE id=1").fetchone()
correct = attempt("Correct#Horse9")
a1 = correct != "OK" and lock[1] is not None
print(f"A1r  {auth.MAX_FAILED_LOGINS} unauthenticated wrong guesses -> count={lock[0]} locked_until={lock[1]}; "
      f"owner's correct pw -> {correct!r} -> reproduces={a1}")
ok += a1

# CS19
note = pf.obligation_note({"sanction"})
src = open(os.path.join(ROOT, "amlkit/api/app.py"), encoding="utf-8").read()
banner = "MATCH FOUND - see alerts, freeze without delay" in src
cs19 = "Freeze without delay" in note and banner
print(f"CS19 obligation_note({{'sanction'}}) takes no dataset and says {note[:45]!r}...; "
      f"onboarding banner 'freeze without delay' present={banner} -> reproduces={cs19}")
ok += cs19

print(f"{ok}/5 reproduce")
sys.exit(0 if ok == 5 else 1)
