# HELD proposal 2026-10-17 (T1-T3) -- not applied, no application code edited
## T1 setup token is not single-use under concurrency (amlkit/api/mobile.py api_setup_submit ~L448; amlkit/cases/operators.py complete_initial_setup ~L111-140)
Check (`_valid_setup_token`) and act (INSERT operator, later UPDATE used_at) are separate statements. Claim first, atomically:
`cur = db.execute("UPDATE setup_tokens SET used_at=? WHERE id=? AND used_at IS NULL", (now, id)); if cur.rowcount != 1: reject`
then insert the operator in the same transaction (BEGIN IMMEDIATE), rolling both back on failure.
## T2 mobile /auth/setup: existing email -> unhandled IntegrityError (500); no looks_like_email, no complexity check, blank name accepted
Catch sqlite3.IntegrityError -> 400; reuse auth.looks_like_email and auth.validate_password_complexity as the web path should.
## T3 add `@limiter.limit("10/minute")` to /auth/verify-email, /auth/resend-verification, GET+POST /auth/setup (tokens are high-entropy, so this is defence in depth).
