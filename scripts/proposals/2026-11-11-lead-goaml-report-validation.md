# HELD proposal: validate goAML report fields at save, stop the gender rewrite (L-140, L-141)

Status: HELD for human review (touches `cases/reports.py`, `cases/manager.py`, `reporting/goaml.py`; lead rule 3).
Master: `9219e2623b3a3ba7e73a20e44c703ab80df7e900`. Repro: `repro_lead/checks_2026_11_11.py` (exit 0 = reproduces).

## Defects
- **L-140 (RP1, MEDIUM).** `cases/reports.py:26-52` `save_report` takes every report field as a plain string;
  the only checks are the amount (`:105-111`), the report type, and the finalise check
  `cases/manager.py:3189` `report_finalize_error` (presence + XML-illegal characters + exporter `_require`).
  Nothing calls `datamodel.validate_birth_date` / `validate_country_code`, which onboarding already
  calls (`cases/manager.py:387-395`). Lead repro: birth date 2999-01-01 and "not-a-date", transaction date
  2030-01-01, nationality "ZZ", reporter email "not-an-email" and account "12345" all save, finalise and
  export (6/6); onboarding refuses the same birth date (control). Finalising locks the report.
- **L-141 (gender rewrite, MEDIUM).** `reporting/goaml.py:325`:
  `"M" if report_data["gender"] == "male" else "F"`. Lead repro: `"M"`, `"other"`, `"unknown"` and
  `"attack helicopter"` all export as `<gender>F</gender>`. `"M"` is the value `save_report`'s own docstring
  documents (`cases/reports.py:69`: `gender: "M", "F", or empty`) and the mobile model
  (`api/mobile.py:1715`) is a free string, so a mobile client following the docstring files every male
  subject as female, silently. The web builder sends `male`/`female` (`str_builder.html:79-80`) and is
  correct for those two values.

## Proposed diff (sketch)

```diff
--- a/amlkit/reporting/goaml.py
+++ b/amlkit/reporting/goaml.py
@@
+_GENDER_CODES = {"male": "M", "m": "M", "female": "F", "f": "F"}
@@ -324,2 +325,5 @@
-        if report_data.get("gender"):
-            ET.SubElement(person, "gender").text = "M" if report_data["gender"] == "male" else "F"
+        g = (report_data.get("gender") or "").strip().lower()
+        if g:
+            if g not in _GENDER_CODES:
+                raise GoAMLValidationError(f"Unsupported gender {report_data['gender']!r}: use male or female, or leave blank.")
+            ET.SubElement(person, "gender").text = _GENDER_CODES[g]
```

```diff
--- a/amlkit/cases/reports.py
+++ b/amlkit/cases/reports.py
@@ save_report, after the amount check
+    from ..datamodel import validate_birth_date, validate_country_code
+    from ..auth import looks_like_email   # auth.py:118, existing helper
+    try:
+        validate_birth_date(birth_date.strip() or None)
+        validate_country_code(nationality.strip() or None)
+        _validate_not_future("transaction date", transaction_date)   # ISO date, <= today (UTC+4)
+    except ValueError as exc:
+        return ReportResult(success=False, error=str(exc))
+    if reporter_email.strip() and not looks_like_email(reporter_email.strip()):
+        return ReportResult(success=False, error="Reporting officer email is not a valid address.")
+    if gender.strip() and gender.strip().lower() not in ("male", "female", "m", "f"):
+        return ReportResult(success=False, error="Gender must be male, female or blank.")
```

And repeat the same field checks inside `report_finalize_error` (drafts saved before the change must not
finalise with bad values). IBAN/account format is deliberately NOT proposed: goAML accounts are not always
IBANs; leave it for the XSD decision. Fix the `save_report` docstring to say `"male"`, `"female"` or empty.

## Test to add with the fix (fails on master today, so not committed)
```python
@pytest.mark.parametrize("over", [dict(birth_date="2999-01-01"), dict(nationality="ZZ"),
                                  dict(transaction_date="2030-01-01"), dict(reporter_email="x"),
                                  dict(gender="attack helicopter")])
def test_report_save_rejects_invalid_fields(client, over): ...   # save_report(...).success is False

@pytest.mark.parametrize("g,code", [("male", "M"), ("M", "M"), ("female", "F"), ("f", "F")])
def test_gender_mapping(g, code): ...   # serialize_goaml_xml(...) has <gender>code</gender>
```

## Not covered
Correct-and-refile of an already-finalised wrong report (skeptic point 3; same gap as CR1). Needs a design decision.
