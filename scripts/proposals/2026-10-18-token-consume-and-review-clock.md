# HELD proposal, 2026-10-18 (lead): one-time token consumers + periodic-review clock

Status: **HELD for human review.** Auth and business logic; not applied. Master `0129848`.
Repro: `repro_lead/checks_2026_10_18.py` (exits 0 while the defects reproduce).

## 1. L-76 / L-77: email-verify token and UAE PASS state consumed more than once

Same check-then-act shape as L-66 (setup token, `cases/operators.py:116-143`) and
L-69 (backup code, `auth.py:839-859`):

- `auth.consume_email_verify_token` (`auth.py:558-583`): `valid_email_verify_token` SELECTs
  and checks `used_at` in Python (`:546-554`), then `UPDATE email_verify_tokens SET used_at=? WHERE id=?` (`:569`).
- `auth.consume_uaepass_state` (`auth.py:985-1017`): SELECT + Python checks (`:1001-1014`),
  then `UPDATE uaepass_states SET consumed_at=? WHERE id=?` (`:1015`).

Observed: 5 concurrent redeems of one value, 5/5 succeed, 5 rounds, 3 runs.

Impact is Low/Info: the email token's holder is its legitimate owner (extra
auto-login sessions only), and the UAE PASS state is also bound to the
`amlkit_uaepass_state` cookie, so a replay needs the victim's own browser.
Fix it because it is the same one-line idiom as L-66/L-69 and all four should land together.

Proposed diff (pattern; apply to all four consumers):

```diff
-    conn.execute("UPDATE email_verify_tokens SET used_at=? WHERE id=?", (now, row["id"]))
+    cur = conn.execute(
+        "UPDATE email_verify_tokens SET used_at=? WHERE id=? AND used_at IS NULL",
+        (now, row["id"]),
+    )
+    if cur.rowcount != 1:
+        conn.rollback()
+        return None
```

```diff
-    conn.execute("UPDATE uaepass_states SET consumed_at=? WHERE id=?", (utcnow(), row["id"]))
+    cur = conn.execute(
+        "UPDATE uaepass_states SET consumed_at=? WHERE id=? AND consumed_at IS NULL",
+        (utcnow(), row["id"]),
+    )
+    if cur.rowcount != 1:
+        conn.rollback()
+        return None
     conn.commit()
```

For the setup token the guarded UPDATE must run *before* the operator INSERT
(same transaction), so a losing claimant inserts nothing.

Test to add with the fix: the threaded block of `checks_2026_10_18.py` as a
pytest asserting exactly one success.

## 2. L-73: an unrelated re-assessment clears an overdue periodic review

`risk/model.py:196` sets `next_review = now + review_months[rating]` on every
`assess()`. `due_for_review` (`cases/manager.py:705-723`) reads the latest
`risk_assessments.next_review`. So any re-assessment pushes the date out:
`record_transaction` -> `reassess_transaction_risk` (`manager.py:817-818`, `1365-1430`),
and `disposition_adverse_media_finding` -> `reassess_adverse_media` (`manager.py:1337`, `1433-1487`; by code, not run).

Observed: customer overdue since 2026-01-01; one AED 60,000 cash transaction
raises an alert; customer leaves the due list with `next_review=2029-10-02`
and no review recorded.

Proposed rule (needs Nadhir's decision, see lead report §6): event-driven
re-assessments carry the prior `next_review` forward, or shorten it if the new
rating's interval is shorter, but never extend it. Only a completed periodic
review (L-70 proposal, `2026-10-17-backup-code-and-periodic-review.md` §2) sets a new date.

```diff
 def reassess_transaction_risk(...):
     ...
     assessment = assess(profile)
+    assessment = _keep_review_clock(conn, customer_id, org_id, assessment)
     save_risk(conn, customer_id, assessment, org_id=org_id, actor=actor)

+def _keep_review_clock(conn, customer_id, org_id, assessment):
+    """Event re-ratings may bring the periodic review forward, never push it back."""
+    prior = conn.execute(
+        "SELECT next_review FROM risk_assessments WHERE customer_id=? AND org_id=?"
+        " ORDER BY id DESC LIMIT 1", (customer_id, org_id)).fetchone()
+    if prior and prior["next_review"] and prior["next_review"] < assessment.next_review:
+        return dataclasses.replace(assessment, next_review=prior["next_review"])
+    return assessment
```

Same call in `reassess_adverse_media`. `reassess_risk` (mobile manual
re-assess) is the de facto review today and is left alone until L-70 lands.
