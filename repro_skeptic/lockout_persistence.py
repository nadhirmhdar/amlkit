"""Skeptic repro: login lockout never resets failed_login_count when the lock expires, so ONE wrong password
after each expiry re-locks the account (and the lock message tells the attacker the expiry time).
Scratch :memory: DB, calls auth.login directly. Exit 0 only if the persistent lockout reproduces."""
import sys, os
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from amlkit import auth, db
c = db.connect(":memory:"); now = db.utcnow()
c.execute("INSERT INTO organizations (name,slug,status,created_at) VALUES ('t','t','active',?)", (now,))
c.execute("INSERT INTO operators (org_id,email,password_hash,name,role,is_active,email_verified_at,created_at) VALUES (1,'mlro@t.test',?,'M','mlro',1,?,?)",
          (auth.hash_password("Correct#Horse9"), now, now)); c.commit()
def attempt(pw):
    try: auth.login(c, "mlro@t.test", pw); return "OK"
    except auth.AuthError as e: return str(e)[:70]
row = lambda: tuple(c.execute("SELECT failed_login_count, locked_until FROM operators").fetchone())
for _ in range(auth.MAX_FAILED_LOGINS): attempt("wrong")
print("after 8 wrong:", row(), "|", attempt("Correct#Horse9"))          # locked; message names the expiry
c.execute("UPDATE operators SET locked_until=? WHERE id=1", ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(timespec="seconds"),)); c.commit()
print("lock expired:", row())
attempt("wrong")                                                          # attacker: a single wrong attempt at expiry
print("after ONE wrong attempt at expiry:", row(), "|", attempt("Correct#Horse9"))
failed, locked = row()
sys.exit(0 if failed > auth.MAX_FAILED_LOGINS and locked else 1)
