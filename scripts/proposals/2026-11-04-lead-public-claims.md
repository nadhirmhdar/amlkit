# HELD (lead, 2026-11-04): public copy overstates freeze scope and UAE PASS; record UAE PASS environment

Status: HELD for human review. Not applied: it edits existing templates and the schema (lead rule 3).
Findings: L-116 (MK2 / CS-25, freeze scope) and L-117 (MK1 / CS-24, UAE PASS) in `reports/daily/2026-11-04/lead.md`.
Repro: `PYTHONPATH=. python repro_lead/checks_2026_11_04.py` (the MK2 and CS24 lines).

## 1. Freeze scope (copy only, LOW)
`amlkit/sanctions_scope.py:is_uae_freeze_list('us_ofac_sdn')` is False. Only UN Security Council and UAE Local
Terrorist List matches create a `freeze_obligations` row (since #433). The public pages say every confirmed match does.

```diff
--- a/amlkit/web/templates/landing.html
-        <p>Prepare STR/SAR reports from the case file and export goAML 5.0 XML. Confirmed sanctions matches create freeze obligations that are tracked until they are executed.</p>
+        <p>Prepare STR/SAR reports from the case file and export goAML 5.0 XML. Confirmed matches on the UN Security Council and UAE Local Terrorist lists create freeze obligations that are tracked until they are executed.</p>
--- a/amlkit/web/templates/aml_law.html
-...<td>Freeze obligations created from confirmed matches and tracked until executed, with reminders to the MLRO.</td></tr>
+...<td>Freeze obligations created from confirmed UN Security Council and UAE Local Terrorist List matches and tracked until executed, with reminders to the MLRO. Matches on other lists (OFAC, EU, UK) stay alerts for enhanced measures.</td></tr>
```
Test to add (tests/test_public_site.py): the landing and `/aml-law` bodies contain "UN Security Council" next to "freeze obligations", and never the bare phrase "Confirmed sanctions matches create freeze obligations".

## 2. UAE PASS claim (copy, MEDIUM while production runs on the sandbox)
CLAUDE.md: production has used the UAE PASS staging sandbox with POC credentials since #378; real customers cannot
complete a sandbox login. `amlkit/uaepass.py:16` says "Staging only, for now". The public pages present it as a CDD
capability with no qualifier.

Option A (recommended): render the UAE PASS mention only when it is real.
```diff
--- a/amlkit/web/templates/landing.html
-... Verify identity with UAE PASS and capture details from Emirates ID and passport scans.</p>
+... {% if uaepass_live %}Verify identity with UAE PASS and capture{% else %}Capture{% endif %} details from Emirates ID and passport scans.</p>
```
with `uaepass_live = uaepass.enabled() and os.environ.get("UAEPASS_ENV", "staging") == "production"` passed from
`api/routers/public.py` (the same flag for the `aml_law.html` CDD row). Option B: delete the words until onboarding completes.

## 3. Record the environment on each verification (LOW)
`uaepass_verifications` has no environment column (repro prints the column list). `match_status` already flags a
sandbox identity that does not match the file, so this is about the audit trail, not a false pass.
```diff
--- a/amlkit/db.py  (_MIGRATIONS, additive)
+    ("uaepass_verifications", "environment",
+     "ALTER TABLE uaepass_verifications ADD COLUMN environment TEXT"),
```
`cases/manager.py` (the function that inserts the row, near line 1359) writes `uaepass.load_config().env` (or the
`UAEPASS_ENV` value), and the case-file panel shows a "sandbox" badge when it is not `production`.
Tests: a verification made with `UAEPASS_ENV` unset stores `staging` and the case file shows the badge.

## Not covered here
SS1 to SS3 (open sign-up enumeration, free screening while unpaid, verification-mail abuse) are in red-team's HELD
`scripts/proposals/2026-11-04-new-findings.md` on `routine/2026-11-04-red-team`. Lead addition to SS1: the org-name
check (`cases/operators.py:47/53/94`, "An organization with a similar name already exists") leaks firm membership the
same way and needs the same generic answer.
