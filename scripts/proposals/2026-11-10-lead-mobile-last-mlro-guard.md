# L-138 (MA1/MA2): mobile deactivate skips the last-active-MLRO guard — HELD

Status: HELD for human review (touches route logic; lead rule 3). Master `9219e26`.

## Defect
`api/mobile.py:1661-1676` (`api_admin_deactivate_operator`) checks MLRO role and org
membership, then runs `UPDATE operators SET is_active=0`. The web route
`api/routers/admin.py:543-554` first counts other active MLROs and refuses the last one.
Repro: `repro_lead/checks_2026_11_10.py` (exit 0 = reproduces):

```
MA1w  web deactivate of sole MLRO: status=200 refused=True active_mlros_after=1
MA1   mobile deactivate of sole MLRO: status=200 body={'ok': True} active_mlros before=1 after=0
```

Consequence: the org has no active MLRO. Reactivation (`admin.py:563`, web only — mobile has
no reactivate route) itself requires an MLRO session, so nobody in the tenant can recover.
Only an out-of-band `/system/create-operator` provisioning (vendor secret) restores an MLRO.
Until then no STR/SAR finalise, freeze execute/resolve, alert confirm, password reset or unlock.

## Proposed diff (minimal: one shared helper, both call sites)

```diff
--- a/amlkit/cases/manager.py   (or amlkit/auth.py — wherever operator writes live)
+def is_last_active_mlro(conn, org_id: int, operator_id: int) -> bool:
+    """True when operator_id is an active MLRO and no other active MLRO exists in org_id."""
+    row = conn.execute(
+        "SELECT role, is_active FROM operators WHERE id=? AND org_id=?", (operator_id, org_id)
+    ).fetchone()
+    if row is None or row["role"] != "mlro" or not row["is_active"]:
+        return False
+    others = conn.execute(
+        "SELECT COUNT(*) FROM operators WHERE org_id=? AND role='mlro' AND is_active=1 AND id != ?",
+        (org_id, operator_id),
+    ).fetchone()[0]
+    return others == 0
```

```diff
--- a/amlkit/api/mobile.py
@@ def api_admin_deactivate_operator(operator_id: int, db: DB, session: Session):
     if row is None:
         raise HTTPException(status_code=404, detail="Operator not found.")
+    from ..cases.manager import is_last_active_mlro
+    if is_last_active_mlro(db, session.org_id, operator_id):
+        raise HTTPException(
+            status_code=409,
+            detail="Cannot deactivate the last active MLRO. Promote another operator to MLRO first.",
+        )
     db.execute("UPDATE operators SET is_active=0 WHERE id=?", (operator_id,))
```

```diff
--- a/amlkit/api/routers/admin.py
-    if row["role"] == "mlro" and row["is_active"]:
-        other_active_mlros = db.execute(...).fetchone()["c"]
-        if other_active_mlros == 0:
-            return back("/admin", err="Cannot deactivate the last active MLRO. ...")
+    if is_last_active_mlro(db, session.org_id, operator_id):
+        return back("/admin", err="Cannot deactivate the last active MLRO. Promote another "
+                                  "operator to MLRO first.")
```

Also tighten the mobile UPDATE to `WHERE id=? AND org_id=?` (defence in depth; the
preceding SELECT already scopes it, so this is not a live tenant bug).

## Test to add with the fix (fails on master today, so not committed)

```python
def test_mobile_cannot_deactivate_last_mlro(api):
    client, headers = api
    me = client.get("/api/v1/auth/me", headers=headers).json()["operator"]["operator_id"]
    r = client.post(f"/api/v1/admin/operators/{me}/deactivate", headers=headers)
    assert r.status_code == 409
    assert client.get("/api/v1/dashboard", headers=headers).status_code == 200
```
(Uses the `api` fixture in `tests/test_mobile_api.py`; `/auth/me` returns
`{"operator": {"operator_id": ...}}` per `mobile.py:153-160, 249-251`.)

## MA2 (self-deactivation without confirmation)
Covered by the guard when the caller is the last MLRO. Self-deactivation by one of several
MLROs is legitimate; a confirmation is a client (app) concern. No server change proposed.

## Optional (skeptic point 2), not proposed now
A DB trigger enforcing "at least one active MLRO per org" would hold for any future entry
point but would also block legitimate test/fixture SQL and org closure. Recommend the shared
helper first; revisit a trigger only if a third write path appears.
