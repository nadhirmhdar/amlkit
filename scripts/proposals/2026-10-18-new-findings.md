# HELD proposal 2026-10-18 (T1 web, T2 web) -- not applied, no application code edited
Extends 2026-10-17 T1/T2 to the web path. In amlkit/cases/operators.py complete_initial_setup (~L111-150):
- Claim the token atomically before inserting: `UPDATE setup_tokens SET used_at=? WHERE id=? AND used_at IS NULL` and require rowcount == 1; do operator INSERT + claim in one BEGIN IMMEDIATE transaction, roll back on failure.
- Catch sqlite3.IntegrityError (duplicate email) and raise ValueError so POST /setup (app.py ~L1115, catches only ValueError) shows a message instead of a 500.
- Apply auth.looks_like_email, auth.validate_password_complexity and a non-blank name check here and in mobile api_setup_submit.
