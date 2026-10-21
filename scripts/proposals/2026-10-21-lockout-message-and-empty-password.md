# HELD: lockout message enumeration (LG2) and empty-password 422 (LG3)

Status: HELD for human review. Route/auth logic, so the lead does not apply it.
Master: `01298484a7bfed106e9b2bd3a6238f98a4d2514b`. Repro: `repro_lead/checks_2026_10_21.py`.
Ship together with L-46 (`scripts/proposals/login-lockout-and-password-rules.md`
on `routine/2026-10-11-lead`, §1): the counter reset, the message and the unlock
path interact (skeptic, 10-12 and 10-21).

## LG2: lock message reveals which emails exist

`auth.login()` promises (docstring, `amlkit/auth.py:347-351`) that lockout is
indistinguishable from an unknown email, but only a real row can reach the
"Account locked ... Try again after HH:MM UTC" branch (`auth.py:376-383`).
Repro output: real email -> "Account locked after repeated failed att...",
unknown email -> "Incorrect email or password." after 9 attempts each.

Proposed diff (pick one; (a) keeps the docstring's promise):

```diff
--- a/amlkit/auth.py
+++ b/amlkit/auth.py
@@ def login(...)
     if row["locked_until"]:
         locked_until = datetime.fromisoformat(row["locked_until"])
         if locked_until > datetime.now(timezone.utc):
             _log_auth_event(conn, "login_failure", email, {"reason": "locked"}, ip=ip)
-            raise AuthError(
-                f"Account locked after repeated failed attempts. Try again after "
-                f"{locked_until.strftime('%H:%M UTC')}, or ask an admin to reset it."
-            )
+            raise generic   # (a) same message as unknown email / wrong password
```

(b) alternative: also count failures for unknown emails (keyed on the
lowercased email in a small table) so unknown addresses lock too and both
show a neutral "Too many attempts. Try again later or ask an admin." with no
timestamp. More code; only worth it if Nadhir wants operators told they are
locked.

The `auth_log` row keeps `reason: locked`, so admins still see the cause.
Test to add with the fix: 9 bad attempts on a real and an unknown email give
the same message.

## LG3: empty password -> raw 422 JSON

`login_submit` declares `password: Annotated[str, Form()]` (`app.py:608`);
an empty field is treated as missing and FastAPI answers 422 JSON before
`auth.login()`'s own `if not email or not password: raise generic` runs.

```diff
-    email: Annotated[str, Form()],
-    password: Annotated[str, Form()],
+    email: Annotated[str, Form()] = "",
+    password: Annotated[str, Form()] = "",
```

`auth.login()` already rejects blanks with the generic message. Severity INFO.

## LG4: not a defect

With the limiter on, 12 POST /login from one client gave
`[200 x10, 429, 429]`. The mlro driver sets `app.state.limiter.enabled = False`
(`mlro_user_drive.py:20`), and `tests/test_p23_login_rate_limit_10_per_min.py`
and `tests/test_rate_limiting.py` already assert 429 on /login. Note the
3/min per-account limit slows L-46 but does not stop it: one attempt per 15
minutes is enough to keep an account locked.
