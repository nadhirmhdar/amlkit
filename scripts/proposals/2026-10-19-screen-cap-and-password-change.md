# HELD proposal 2026-10-19 (lead): S3, PW1, PW2, SS1, L-75

Not applied. Every item touches route or auth logic, which the lead routine may not edit. Repro: `repro_lead/checks_2026_10_19.py` (exit 0 = all reproduce on `0129848`).

## 1. S3 (L-78): ad-hoc screening has no name-length cap (web + mobile), and mobile has no limiter

Correction to red-team's proposal: the web route already has `@limiter.limit("10/minute")` (`amlkit/api/app.py:1680`); only the mobile route (`amlkit/api/mobile.py:523`) lacks one. Neither caps length; the full query is stored in `screenings` for the retention period.

Reuse the existing customer-path cap rather than a new constant:

```diff
--- a/amlkit/api/mobile.py
+++ b/amlkit/api/mobile.py
@@ class ScreenRequest(BaseModel):
-    name: str
+    name: str = Field(max_length=MAX_NAME_LENGTH)   # from amlkit.datamodel (200)
@@
 @router.post("/screen")
+@limiter.limit("30/minute")
 def api_screen(body: ScreenRequest, db: DB, session: Session):
```
(the mobile router needs `request: Request` in the signature for slowapi, as its login routes already have.)

```diff
--- a/amlkit/api/app.py   (screen_run, after name = name.strip())
+    if len(name) > MAX_NAME_LENGTH:
+        return render(request, "screen.html", {"session": session, "result": None,
+                      "query": name[:MAX_NAME_LENGTH], "err": f"Name exceeds {MAX_NAME_LENGTH} characters."}, db)
```
Test to add with the fix: 201-character name returns 400 (mobile) / error page (web) and writes no `screenings` row.

## 2. PW1 (L-79): success message contradicts behaviour

`auth.set_password` deliberately revokes every session including the current one (`auth.py:478-490`, docstring). Keep the behaviour; fix the copy and the redirect so the user is not bounced from a success banner to `/login`:

```diff
--- a/amlkit/api/app.py:838 and :4577
-    return back("/", msg="Password changed successfully. All other sessions have been signed out.")
+    return back("/login", msg="Password changed. For your security every session, including this one, "
+                              "has been signed out. Sign in with your new password.")
```
(check `back()` keeps the flash cookie across the 303 to `/login`; the login page already renders `msg`.)

## 3. PW2 (L-80): new password may equal the current one

Both handlers (`app.py:795-838`, `:4542-4577`) verify the current password, then never compare it with the new one. Add after the match check:
```python
if auth.verify_password(new_password, op_row["password_hash"]):
    -> err "New password must be different from the current password."
```
Info severity; a policy nicety, but trivial and it belongs in the shared password helper proposed for L-47/L-58/L-67.

## 4. SS1 (L-81): oldest session evicted silently at the session cap

`_enforce_session_limit` (`auth.py:587-602`) revokes the oldest live session when an operator reaches `MAX_CONCURRENT_SESSIONS` (default 3), counting mobile tokens too. The cap is a deliberate control; keep it. Options for Nadhir:
- (a) record a `revoked_reason='session_limit'` on the revoked row and have `/login` show "You were signed out because you signed in on another device"; needs one additive column;
- (b) raise the default to 5 so desktop + laptop + phone + one spare fit;
- (c) both.

## 5. L-75: MFA-locked MLRO opening /admin takes three hops

`admin_view` (`app.py:3212-3220`) sends a locked session to `/` (current_session is not None), `/` sends it to `/login`, and `/login` to `/mfa/verify`. No bypass. If touched, send any `PermissionError` from an MFA-locked session straight to `auth.mfa_challenge_path(...)`, ideally once in `require_session`'s callers via a small helper, not per route. Info.
