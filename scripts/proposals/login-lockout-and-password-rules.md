# HELD: login lockout persistence (L-46), password rule gaps (L-47), cross-tenant refresh actor (L-48)

Status: **HELD for human review** (lead 2026-10-11). Each fix changes auth or route logic, which the routine may not edit.
Repro: `repro_lead/checks_2026_10_11.py` (branch `routine/2026-10-11-lead`), which exits 0 while all of the defects below reproduce on `0129848`.

## 1. L-46: the account stays locked for as long as an attacker wants (HIGH)

**Defect.** `auth.login()` (`amlkit/auth.py:376-404`) lets a login through once `locked_until` has passed, but it never resets `failed_login_count`. The counter is cleared only by a successful login (`:419-421`) or by `set_password` (`:485`). After the first lock, the counter sits at 8 or more, so a single wrong password re-locks the account for 15 minutes (`failed >= MAX_FAILED_LOGINS`). The lock message also gives the expiry time (`:381-382`), which tells an attacker when to send that next attempt.

**Evidence** (lead run, `0129848`):
```
A1   expired=(8, '...03:45:11+00:00') after ONE wrong=(9, '...04:00:12+00:00') correct pw -> 'Account locked after repeated failed attempts. Try again aft' -> reproduces=True
```

**Impact.** Anyone who knows an MLRO's email can keep that MLRO locked out by sending one request every 15 minutes, which stays under every rate limit. Freeze execution and CNMR filing are MLRO-only (`app.py:1518`, `:1552`) and run against a 24-hour clock. The only unlock in the app is another MLRO resetting the password, and a firm with one MLRO has no second MLRO.

Mitigation found today: `resolve_uaepass_operator` (`auth.py:883+`) does not check `locked_until`, so an operator already linked to UAE PASS can still sign in by SSO (`SSO ... True` in the repro). That only helps once real UAE PASS credentials exist. Production runs on the staging sandbox.

**Proposed diff** (`amlkit/auth.py`, in `login()`):
```diff
     if row["locked_until"]:
         locked_until = datetime.fromisoformat(row["locked_until"])
         if locked_until > datetime.now(timezone.utc):
             _log_auth_event(conn, "login_failure", email, {"reason": "locked"}, ip=ip)
-            raise AuthError(
-                f"Account locked after repeated failed attempts. Try again after "
-                f"{locked_until.strftime('%H:%M UTC')}, or ask an admin to reset it."
-            )
+            raise AuthError(
+                "Account temporarily locked after repeated failed attempts. "
+                "Try again later, or ask an admin to reset it."
+            )
+        # Lock has expired: start a fresh window so one wrong password
+        # cannot re-lock the account immediately.
+        conn.execute("UPDATE operators SET failed_login_count=0, locked_until=NULL WHERE id=?", (row["id"],))
+        conn.commit()
+        row = {**dict(row), "failed_login_count": 0, "locked_until": None}
```
Optional hardening, a separate decision for Nadhir: make the lockout escalate (15 min, then 1 h), or send the operator an email when their account locks. A new test is needed: lock the account, expire the lock, make one wrong attempt, and assert the correct password still logs in.

**Wording caveat.** On `0129848`, `grep -rn "Try again after" tests/` returns nothing, so no existing test asserts the old wording.

## 2. L-47: the password rule has three entry points with three behaviours (LOW, single fix)

- Self-change (`app.py:824-825`, `:4566-4567`): the full rule runs, and a failure returns a readable message.
- Admin reset (`app.py:3475-3478`): only the length is checked before calling `auth.set_password`, and `set_password` raises `PasswordComplexityError`, which gives HTTP 500 (**OP1**, also red-team F11 from 10-04).
- Admin create (`app.py:3533`, `:3552`): only the length is checked, and the password is hashed directly. `aaaaaaaaaa` is accepted (**OP2**).

```
OP2  admin create with 'aaaaaaaaaa': status=200 account_created=True -> reproduces=True
OP1  admin reset to '1234567890': status=500 -> reproduces=True
```

**Proposed diff** (`amlkit/api/app.py`):
```diff
 # admin_reset_password
-    if len(new_password) < 10:
-        return back("/admin", err="Password must be at least 10 characters.")
-
-    auth.set_password(db, operator_id, new_password)
+    try:
+        auth.set_password(db, operator_id, new_password)
+    except auth.PasswordComplexityError as exc:
+        return back("/admin", err=str(exc))

 # admin_create_operator
-    if len(password) < 10:
-        return back("/admin", err="Password must be at least 10 characters.")
+    try:
+        auth.validate_password_complexity(password)
+    except auth.PasswordComplexityError as exc:
+        return back("/admin", err=str(exc))
```
`validate_password_complexity` (`auth.py:109-123`) already rejects short passwords, with the message "...at least 10 characters long". **Test impact:** existing tests that create operators through `/admin/operators` with lowercase-only passwords will start failing. The `_register` default `a-strong-password-1` has no uppercase letter, so grep `tests/` for `/admin/operators` posts and update their passwords in the same PR. Then add two route tests, one for each weak password.

## 3. L-48: one firm's MLRO name appears in another firm's audit trail (LOW)

`/admin/refresh` (`app.py:3632-3648`) lets **any** org's MLRO run `run_sanctions_refresh`. That function re-screens every active org (`cases/scheduler.py:96-100`) and passes the clicking MLRO's name as `actor`. Org B's `screening.run` audit rows then name an operator from Org A, and the `dataset.refresh` rows (with `org_id=NULL`, which every org sees through `queries.audit_trail`) do the same.

```
GR   Org A MLRO /admin/refresh -> Org B screening.run actors=['Alice Lead', 'Bob Other'] -> reproduces=True
```

A global refresh is by design, because the lists are shared. The defects are (a) another firm's staff member's name disclosed across tenants, and (b) an audit trail an examiner would read as "a person outside this firm screened our customers".

**Proposed diff** (`amlkit/cases/scheduler.py`):
```diff
-            outcome = rescreen_all(conn, org["id"], actor=actor)
+            outcome = rescreen_all(conn, org["id"], actor="system (sanctions refresh)")
```
In `loader.load` / `dataset.refresh`, apply the same treatment to the `org_id=None` rows: log `actor="system"`, and record the requesting operator and org only in a row scoped to that org. Rate-limiting or role-gating the global refresh to `super_admin` is a separate product decision.
