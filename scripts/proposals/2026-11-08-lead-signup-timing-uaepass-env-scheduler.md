# HELD proposal 2026-11-08 (lead): sign-up timing, mail cooldown, UAE PASS environment, scheduler read-back

Status: **HELD for human review.** None of this is applied. Each item edits application logic, schema or the deploy workflow, so the lead routine (additive-only) may not land it.
Master: `9219e2623b3a3ba7e73a20e44c703ab80df7e900`. Repro: `repro_lead/checks_2026_11_08.py` (exit 0 = at least one reproduces).
It complements red-team's `scripts/proposals/2026-11-08-new-findings.md` (prose only) with diffs.

## 1. L-129 SS1b / CR-41: timing oracle on open sign-up (LOW)

`amlkit/cases/operators.py:116-120` returns through `_notify_existing_account` before `auth.hash_password` (`:143`). Measured locally: median 71.6 ms for a new email vs 12.2 ms for an existing one, with identical pages. `auth.login` (`amlkit/auth.py:541-545`) already hashes a dummy value for this reason.

```diff
--- a/amlkit/cases/operators.py
+++ b/amlkit/cases/operators.py
@@ def register_organization(
     org_name = auth.check_org_name(org_name)
+    # Hash before any branch so both sign-up outcomes cost the same (L-129);
+    # the existing-account path otherwise returns ~60 ms sooner.
+    password_hash = auth.hash_password(password)
     if pending_payment:
@@
-            (org_id, clean_name, clean_email, auth.hash_password(password), "mlro", now),
+            (org_id, clean_name, clean_email, password_hash, "mlro", now),
```

The remaining gap is the INSERTs plus the token mint (a few ms). In production both paths send mail synchronously, so SMTP latency differs between the notice and the verification mail. The complete fix moves both sends to a `BackgroundTasks` job in `api/routers/auth.py`. That needs a route change, so it is listed for Nadhir, not diffed here.

Test (add to `tests/test_wp29_launch_blockers.py`):
```python
def test_open_signup_hashes_password_on_existing_email(monkeypatch, stripe_mode_client):
    calls = []
    real = auth.hash_password
    monkeypatch.setattr(auth, "hash_password", lambda p: calls.append(p) or real(p))
    _signup(stripe_mode_client, "Firm A", "x@a.ae")
    calls.clear()
    _signup(stripe_mode_client, "Firm B", "x@a.ae")   # existing email
    assert calls, "existing-email path must do the same hashing work"
```

## 2. L-130 SS3b / CR-42: no per-address cooldown on sign-up mail (LOW)

12 sign-ups for one existing address sent 12 notices (repro). The limit is per IP only (5/min).

```diff
--- a/amlkit/cases/operators.py
+++ b/amlkit/cases/operators.py
@@ def _notify_existing_account(conn, existing, email):
-    delivery = mail.send_existing_account_notice(email, existing["name"])
+    recent = conn.execute(
+        "SELECT 1 FROM audit_log WHERE action='operator.signup_existing_email' "
+        "AND object_id=? AND ts > ? LIMIT 1",
+        (str(existing["id"]),
+         (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat())).fetchone()
+    delivery = "suppressed" if recent else mail.send_existing_account_notice(email, existing["name"])
```
`audit_log` (`db.py:840`) stores `object_id` as TEXT and `ts` as ISO UTC. Compare ISO strings, not `datetime('now')`, whose format differs. The new-email verification mail cannot loop on the same address, because the second attempt hits the existing-account branch. So the notice is the only one that needs a cooldown.

## 3. L-131 CS-24 residual: sandbox UAE PASS verifications are indistinguishable (MEDIUM)

- `uaepass_verifications` (`db.py:959-973`) has no environment column.
- The in-product button is gated on `uaepass_enabled = uaepass.load_config() is not None` (`api/helpers.py:134`), not on production. The public copy uses `_uaepass_live()` (`api/routers/public.py:39-44`).

```diff
--- a/amlkit/db.py   (SCHEMA + _MIGRATIONS, additive)
+    environment    TEXT,               -- 'staging' | 'production' (UAEPASS_ENV at verification time)
+ ("uaepass_verifications", "environment", "TEXT"),
--- a/amlkit/cases/manager.py  (where the verification row is inserted)
-    INSERT INTO uaepass_verifications (..., verified_by) VALUES (..., ?)
+    INSERT INTO uaepass_verifications (..., verified_by, environment) VALUES (..., ?, ?)
+    # pass cfg.environment
```
And on the case-file page show a "SANDBOX: not a CDD verification" badge when `environment != 'production'`. Hiding the button would also block legitimate staging testing. Legacy rows stay NULL, shown as "environment not recorded".

## 4. L-132 CS-5 deploy: a failed scheduler update is silent (LOW, operational)

`source-canary.yml:570` marks the refresh scheduler step `continue-on-error: true`. Its `gcloud scheduler jobs describe` (`:574`) only checks that the job exists (`>/dev/null`). Nothing reads the schedule back. If IAM fails, the 20-hour cron stays and the run is green.

```yaml
      - name: Verify sanctions refresh schedule
        if: always()
        run: |
          S=$(gcloud scheduler jobs describe amlkit-sanctions-refresh \
                --location "${{ vars.GCP_REGION }}" --project "${{ vars.GCP_PROJECT_ID }}" \
                --format='value(schedule)' 2>/dev/null || true)
          echo "schedule=$S"
          if [ "$S" != "0 */4 * * *" ]; then
            echo "::warning::amlkit-sanctions-refresh schedule is '$S', expected '0 */4 * * *'"
          fi
```
(`::warning::` keeps the deploy green but visible. Use `exit 1` if Nadhir prefers a red run.)

## 5. INFO-8 cosmetic leftovers
`scripts/grant_scheduler_iam.sh:36` still says "every 20h". `queries.py:1461,1502` say "> 20h" stale. Change the script text to "every 4h". Leave the 20-hour stale threshold or lower it to about 8 h (two missed runs). That is Nadhir's call.
