# HELD proposal 2026-10-17 (lead): backup-code reuse race (L-69), periodic review (L-70, L-71)

Not applied. Each change touches auth or route logic, which the routine may not edit. Master `0129848`.
T1/T2/T3 (setup token) are covered by red-team's `scripts/proposals/2026-10-17-new-findings.md`
on `routine/2026-10-17-red-team`; the atomic-claim pattern below is the same and both should land together.

## §1 L-69: one MFA backup code can be consumed twice concurrently (`auth.py:839-859`)

Repro: `repro_lead/checks_2026_10_17.py` line `BC ... results=[True, True] -> reproduces=True` (3/3 runs).
`mfa_verify_backup_code` selects unused rows, runs Argon2 `verify` (slow, so a wide window), then
`UPDATE ... WHERE id=?` without `AND used_at IS NULL`, and returns True without checking the row count.

Proposed diff:

```diff
-        conn.execute(
-            "UPDATE mfa_backup_codes SET used_at=? WHERE id=?",
-            (utcnow(), row["id"])
-        )
-        conn.commit()
-        return True
+        cur = conn.execute(
+            "UPDATE mfa_backup_codes SET used_at=? WHERE id=? AND used_at IS NULL",
+            (utcnow(), row["id"])
+        )
+        conn.commit()
+        return cur.rowcount == 1
```

Test to add with the fix: two threads, two connections, a `threading.Barrier`, same code; exactly one True.
Severity LOW: the attacker already needs the password and a valid backup code; the gain is one extra
session from a code that should have been spent. Same idiom should be checked in `email_verify_tokens`
and `uaepass_states` consumers (not checked today).

## §2 L-70: no web action completes a periodic CDD review

Confirmed by code: web POST routes under `/customers/{customer_id}/` are close, reactivate, ubo, notes,
transactions, adverse-media, signatures (`app.py:2201-2533`); the only explicit re-assessment is mobile
`POST /api/v1/customers/{id}/risk` (`mobile.py:772`, calls `reassess_risk`). The overdue list is
`manager.py:714-721`.

Additionally (PLAUSIBLE, by code only): `risk/model.py:196` always sets a fresh `next_review`, and web paths
reach `reassess_transaction_risk` (`manager.py:818`) and `reassess_adverse_media` (`manager.py:1337`).
So an unrelated transaction or adverse-media disposition can silently reset the review clock with no review done.

Proposed shape (needs Nadhir's decision on the record format):
1. New web route `POST /customers/{customer_id}/review` (CSRF, MLRO/compliance role) calling a new
   `cases.manager.complete_periodic_review(conn, customer_id, org_id, actor, outcome, note)` that runs
   `reassess_risk`, requires a non-empty note, and writes a `customer.periodic_review` audit row with
   reviewer, outcome (`no_change` / `rating_changed` / `escalated_edd` / `exit`), note, previous and new
   rating and next_review.
2. Mobile `/customers/{id}/risk` calls the same service function (one implementation, see skeptic's
   "mobile and web have diverged").
3. Decide whether incidental re-assessments (transactions, adverse media) should move `next_review`.
   Recommendation: no; carry the previous `next_review` forward unless the rating changed upward
   (shorter interval), so the overdue flag clears only through §2.1.

## §3 L-71: case file shows the due date without an overdue marker (`customer.html:142`)

```diff
-        assessed {{ risk.assessed_at[:10] }} · next review {{ risk.next_review }}
+        assessed {{ risk.assessed_at[:10] }} · next review {{ risk.next_review }}
+        {% if risk.next_review and risk.next_review <= today %}<span class="tag tag-warn">overdue</span>{% endif %}
```
(`today` must be passed in the template context; the list page already computes the same flag.)
