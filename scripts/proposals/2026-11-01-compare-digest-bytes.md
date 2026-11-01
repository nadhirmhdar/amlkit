# HELD: compare secrets as bytes at every call site (L-100 = CR-24, CR-25, CR-26)

Status: HELD for human review (changes `amlkit/auth.py` and `amlkit/billing/stripe_client.py`).
Raised by: code-reviewer (CR-24/25/26), skeptic (linked to its 10-04 `stdlib_behaviour.py` finding). Lead verdict: CONFIRMED on `11a3527` by `repro_lead/checks_2026_11_01.py` (CR25, CR26, CR24 all `TypeError`).

## Problem
`hmac.compare_digest` / `secrets.compare_digest` raise `TypeError` when given a `str` that contains non-ASCII characters. #439 fixed this for `deps.bearer_ok` only. Three sites remain:

| Site | Reached from | Effect today |
|---|---|---|
| `amlkit/auth.py:815` `mfa_verify` | `POST /mfa/verify` -> `mfa_check_code` (auth.py:862), no digit filter | An MLRO who types Arabic-Indic digits gets HTTP 500, not "Invalid code". Regression from #433 (L-40): before it, the same input returned False. The miss is not counted, so no lockout bypass. |
| `amlkit/auth.py:744` `csrf_valid` | `deps.require_csrf` on every form POST; UAE PASS state check (app.py:772, :2180) | Non-ASCII `csrf_token` -> 500 instead of 403. Attacker-only input, no state change. |
| `amlkit/billing/stripe_client.py:195` | `POST /billing/webhook` (only when Stripe is configured) | Non-ASCII `v1=` -> 500 instead of 400. Unauthenticated, no state change. |

## Proposed diff (one helper, three call sites)
```diff
--- a/amlkit/auth.py
+++ b/amlkit/auth.py
@@
+def safe_equals(a: str | bytes | None, b: str | bytes | None) -> bool:
+    """Constant-time equality that never raises on non-ASCII input."""
+    if a is None or b is None:
+        return False
+    if isinstance(a, str):
+        a = a.encode("utf-8")
+    if isinstance(b, str):
+        b = b.encode("utf-8")
+    return hmac.compare_digest(a, b)
@@ def csrf_valid(cookie_value, form_value):
-    return secrets.compare_digest(cookie_value, form_value)
+    return safe_equals(cookie_value, form_value)
@@ def mfa_verify(...):
-        if hmac.compare_digest(totp.generate_otp(step), code):
+        if safe_equals(totp.generate_otp(step), code):
--- a/amlkit/billing/stripe_client.py
+++ b/amlkit/billing/stripe_client.py
@@
-    if not any(hmac.compare_digest(expected, c) for c in candidates):
+    if not any(hmac.compare_digest(expected.encode(), c.encode("utf-8", "replace")) for c in candidates):
```
Optional UX follow-up (product choice): in `mfa_check_code`, map Unicode decimal digits to ASCII (`"".join(str(int(ch)) if ch.isdecimal() else ch for ch in code)`) so an Arabic-keyboard code is accepted rather than merely refused with a message.

`deps.bearer_ok` could then call `auth.safe_equals` too, so there is one helper.

## Tests to add with the fix
- `auth.mfa_verify(conn, op, "١٢٣٤٥٦", confirmed_only=True) is False`; `POST /mfa/verify` with that code -> 303 back with "Invalid verification code".
- `auth.csrf_valid("abc", "abé") is False`; a form POST with that token -> 403/redirect, not 500.
- `verify_webhook_signature(b"{}", "t=100,v1=é", "whsec_x", now=100)` raises `SignatureError`; webhook route -> 400.
- A grep-style test that `compare_digest(` appears only inside the helper(s).

Not applied by the lead: rule 3 (no edits to existing auth/business logic). Tests not committed: they fail on master (rule 5).
