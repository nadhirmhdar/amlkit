# HELD: freeze scope by source list (CS-2) and TOTP replay (M2)

Lead, 2026-10-07, master `01298484a7bfed106e9b2bd3a6238f98a4d2514b`. Both items change business or auth logic, so per the routine's additive-only rule neither is applied. Repro: `repro_lead/checks_2026_10_07.py` (exit 0 means both reproduce).

## 1. CS-2: freeze obligation created for non-UAE-list hits (needs Nadhir's decision)

**Evidence on `0129848`:**
```
CS-2 EU-only sanction hit, true_positive -> freeze_obligations=[{'id': 1, 'obligation_type': 'sanctions', 'risk_category': 'critical', 'status': 'pending_execution'}] -> reproduces=True
```
`amlkit/cases/review.py:163`: `is_freeze_worthy = bool(categories) or "sanction" in topics`. Nothing reads the entity's dataset. The freeze email (`mail.py:292-296`) then says "Execute asset freeze without delay ... File a CNMR". The CNMR route (`app.py` `freeze_obligation_file_ffr`) is offered for any executed freeze.

**Regulator text (guidance, not the instrument; two roles fetched it independently):** EOCN `uaeiec.gov.ae/en-us/un-page` says Cabinet Decision 74/2020 covers "the UAE Local Terrorist List and UNSC Consolidated List only", and that for OFAC/EU/HMT matches the entity "should not use the CNMR/PNMR reports" but should consult its supervisory authority and may consider an STR/SAR. The product's own blog (`blog/uae-sanctions-screening-24-hour-rule.html:87`) says the same thing, so the code contradicts the published copy.

**Proposed diff (sketch, not applied):**
```diff
--- a/amlkit/cases/review.py
+++ b/amlkit/cases/review.py
@@ def _alert_categories(
-    row = conn.execute(
-        """SELECT e.topics, e.programs FROM alerts a
-           JOIN entities e ON e.id = a.entity_id WHERE a.id=? AND a.org_id=?""",
+    row = conn.execute(
+        """SELECT e.topics, e.programs, d.name AS dataset FROM alerts a
+           JOIN entities e ON e.id = a.entity_id
+           JOIN datasets d ON d.id = e.dataset_id
+           WHERE a.id=? AND a.org_id=?""",
@@ def _auto_create_freeze_if_required(
-    is_freeze_worthy = bool(categories) or "sanction" in topics
+    # Cabinet Decision 74/2020 TFS scope: UAE Local Terrorist List + UNSC list only.
+    UAE_TFS_DATASETS = {"ae_local_terrorists", "un_consolidated"}
+    if dataset not in UAE_TFS_DATASETS:
+        audit(conn, "alert.non_uae_list_confirmed", ..., org_id=org_id)  # EDD + consider STR/SAR
+        return None
+    is_freeze_worthy = bool(categories) or "sanction" in topics
```
Callers of `_alert_categories` would need the extra return value. An entity can appear on several lists as separate `entities` rows, so a UN designee also on OFAC still raises a UN alert and still freezes. Add a note on the alert page for non-UAE confirmed matches ("no UAE freeze duty under Cabinet Decision 74/2020; consult your supervisory authority; consider an STR/SAR").

**Why HELD:** this narrows a freeze control on the strength of guidance, not the instrument, and the EOCN text itself says to consult the supervisor. Nadhir or an adviser must decide. Options: (a) as above; (b) keep the freeze obligation but relabel it "voluntary / business decision" with no 24h clock, no overdue email and no CNMR route; (c) leave as is and change the blog.

Related: CS-19 (`ingest/ofac.py:23 is_mandatory = True`) is the same question for the freshness gate.

## 2. M2: a TOTP code verifies more than once (LOW, hardening)

**Evidence on `0129848`:**
```
M2   same TOTP code: first=True second=True -> reproduces=True
```
`amlkit/auth.py:686-687`: `pyotp.TOTP(row["secret"]).verify(code, valid_window=1)`, no record of the last accepted step. RFC 6238 §5.2 says a verifier should not accept the second attempt of the same OTP. Requires the password plus an observed code within about 90 s.

**Proposed diff (not applied):** additive column `mfa_secrets.last_step INTEGER` in `_MIGRATIONS`, then in `mfa_verify`:
```diff
-    totp = pyotp.TOTP(row["secret"])
-    return totp.verify(code, valid_window=1)
+    totp = pyotp.TOTP(row["secret"])
+    now_step = totp.timecode(datetime.now(timezone.utc))
+    for step in (now_step - 1, now_step, now_step + 1):
+        if step > (row["last_step"] or -1) and hmac.compare_digest(totp.generate_otp(step), code):
+            conn.execute("UPDATE mfa_secrets SET last_step=? WHERE operator_id=?", (step, operator_id))
+            return True
+    return False
```
The `SELECT` must also read `last_step`. Test: the same code twice returns True then False, and the next step's code still works.
