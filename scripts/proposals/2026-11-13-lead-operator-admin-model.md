# HELD: operator administration has no model of required roles (L-145 to L-148)

Status: **HELD for human review** (route and business logic; the lead may not apply it).
Master: `9219e2623b3a3ba7e73a20e44c703ab80df7e900`. Raised by mlro-user (SO1, RL1-RL3) and skeptic 2026-11-13; RL2d added by the lead.
Repro: `repro_lead/checks_2026_11_13.py` (exit 0 = at least one reproduces; 5/5 today).
Related HELD item: L-138 / MA1 (`scripts/proposals/2026-11-10-lead-mobile-last-mlro-guard.md`). Land it in the same wave.

## Findings (all CONFIRMED on 9219e26)
| id | What | Where |
|---|---|---|
| L-145 SO1 | Any one MLRO can turn single-operator mode on with three active operators; four-eyes is then off for every sanctions/PF dismissal | `api/routers/admin.py:341-367` checks role + CSRF only; `cases/review.py:96-121` honours the org setting first |
| L-146 RL1 | No role-change route on web or mobile (no `SET role` anywhere in `amlkit/`), yet the last-MLRO guard says "Promote another operator to MLRO first" | `api/routers/admin.py:552` |
| L-147 RL2 | Reactivation restores the old password | `api/routers/admin.py:563-591` only sets `is_active=1`; deactivation (`:523-561`) revokes sessions but keeps the hash |
| L-147 RL2d | Deactivation does not revoke trusted-device tokens, so a reactivated MLRO's old device still skips MFA | `revoke_sessions_for` (`auth.py:412`) does not touch `trusted_devices`; only `set_password` (`auth.py:685`) calls `revoke_trusted_devices_for` |
| L-148 RL3 | Reactivating an already active operator reports success and writes another `operator.reactivate` audit row | `api/routers/admin.py:578-591` (no `is_active` check) |

## Target rules (one spec, as the skeptic suggested)
1. Always at least one active MLRO (web already; mobile = L-138).
2. Single-operator mode `on` is allowed only while the org has exactly one active operator. Creating or reactivating a second operator while it is on either refuses or flips the org setting back to `default` with an audit row. (Alternative if Nadhir prefers: a second MLRO must confirm. Needs his decision.)
3. Role change exists (MLRO-only, audited, cannot demote the last active MLRO), or the guard text stops promising it.
4. Deactivation also revokes trusted devices; reactivation forces a password reset (simplest: reactivation sets a random hash and tells the MLRO to use "Reset password").
5. Reactivating an active operator is a no-op with a neutral message and no audit row.

## Proposed diff (sketch, not applied)
```diff
--- a/amlkit/api/routers/admin.py  (admin_set_single_operator)
     if mode not in choices:
         return back("/admin", err="Choose on, off, or default.")
+    if choices[mode] is True:
+        n_active = db.execute(
+            "SELECT COUNT(*) FROM operators WHERE org_id=? AND is_active=1",
+            (session.org_id,)).fetchone()[0]
+        if n_active > 1:
+            return back("/admin", err="Single-operator mode is only for firms with "
+                        "one active operator. Deactivate the others first.")
     set_org_single_operator_mode(db, session.org_id, choices[mode])

--- a/amlkit/api/routers/admin.py  (admin_deactivate_operator)
     db.execute("UPDATE operators SET is_active=0 WHERE id=?", (operator_id,))
     auth.revoke_sessions_for(db, operator_id)
+    auth.revoke_trusted_devices_for(db, operator_id)

--- a/amlkit/api/routers/admin.py  (admin_reactivate_operator)
-    row = db.execute(
-        "SELECT id FROM operators WHERE id=? AND org_id=?", (operator_id, session.org_id)
-    ).fetchone()
+    row = db.execute(
+        "SELECT id, is_active FROM operators WHERE id=? AND org_id=?",
+        (operator_id, session.org_id)).fetchone()
     if row is None:
         return back("/admin", err="Operator not found.")
+    if row["is_active"]:
+        return back("/admin", msg="Operator is already active.")
     ...
-    db.execute("UPDATE operators SET is_active=1 WHERE id=? AND org_id=?", (operator_id, session.org_id))
+    db.execute("UPDATE operators SET is_active=1, password_hash=? WHERE id=? AND org_id=?",
+               (auth.hash_password(secrets.token_urlsafe(32)), operator_id, session.org_id))
+    # message: "Operator reactivated. Use Reset password to give them a new password."
```
The same deactivate change applies to mobile `api/mobile.py:1661` (with the L-138 guard). The single-operator count must also be enforced where operators are created/reactivated (web `admin.py:467`, `:563`; mobile `mobile.py:1619`) if rule 2's "flip back" variant is chosen. Role change (rule 3) is new UI + route; not sketched until Nadhir picks rule 3's option.

## Tests to add with the fix
Convert each `checks_2026_11_13.py` block into a test asserting the fixed behaviour (SO1 refused with 3 operators and allowed with 1; reactivated officer cannot sign in with the old password; trusted device invalid after deactivation; second reactivate writes no audit row). Existing tests that switch single-operator mode on in multi-operator orgs will need updating; grep `single-operator` in `tests/`.
