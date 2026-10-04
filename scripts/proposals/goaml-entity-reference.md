# goAML entity reference: wiped on org-profile save, ignored by the STR builder (HELD)

Status: HELD (route logic). Raised by mlro-user F3, extended by skeptic; lead CONFIRMED
on master `05e612d` with `repro_lead/goaml_entity_ref_wipe.py` (exit 0 = reproduces):

```
after first save: TEST-ORG-0001
/admin input value: ''
after second save (phone-only edit): None
```

## Mechanism
- `amlkit/api/app.py:3182-3186` — the `/admin` org SELECT omits `goaml_entity_reference`,
  so `admin.html:53` renders `value=""`.
- `amlkit/api/app.py:3253-3267` — `admin_save_org_profile` writes every field, so any
  later save of the form (e.g. a phone edit) writes NULL over the saved reference.
- `amlkit/web/templates/str_builder.html:33` pre-fills `entity_reference` with the literal
  `GROVISOR-LIC-2026` when the payload has none (`app.py:4044` starts new reports with
  `payload = {}`). Because the payload then carries a value,
  `reporting/goaml.py:96-102` never falls back to the org's own reference.
- Correction to skeptic: the saved value *is* read by reporting code
  (`reporting/goaml.py:78-102`), but only for payloads without a reference, which the
  builder never produces.

Effect: a tenant other than Grovisor files STRs carrying Grovisor's placeholder reference
unless the operator notices and overwrites it; goAML is likely to reject the upload, which
delays a time-bound filing.

## Proposed diff
```diff
--- a/amlkit/api/app.py  (admin view)
-        SELECT name, slug, org_address, reporting_person_name,
-               reporting_person_title, reporting_person_phone
+        SELECT name, slug, org_address, reporting_person_name,
+               reporting_person_title, reporting_person_phone,
+               goaml_entity_reference
--- a/amlkit/api/app.py  (report_build_view)
-    payload = {}
+    payload = {}
+    org_ref = db.execute("SELECT goaml_entity_reference FROM organizations WHERE id=?",
+                         (session.org_id,)).fetchone()
+    if org_ref and org_ref[0]:
+        payload["entity_reference"] = org_ref[0]
--- a/amlkit/web/templates/str_builder.html
-value="{{ payload.entity_reference or 'GROVISOR-LIC-2026' }}" required
+value="{{ payload.entity_reference or '' }}" required
```
Also add `require_csrf` to `admin_save_org_profile` (red-team F5; red-team's
`scripts/proposals/org-profile-csrf.md` on `routine/2026-10-04-red-team`).
