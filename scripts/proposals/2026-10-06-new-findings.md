# HELD: findings from the 2026-10-06 run (not applied; additive-only)
Evidence: reports/daily/2026-10-06/evidence/*_on_b7eeb2f.txt

## N3 residual invisible-character bypasses of `clean_name_text` (names/arabic.py)
`clean_name_text` drops only category Cf. VS16 (U+FE0F, Mn), combining grapheme joiner (U+034F, Mn), C0/DEL controls (Cc), Braille blank (U+2800, So) and private use (U+E000, Co) still split a token via `_PUNCT`, so an exact listed name scores 0 (probe_unicode_bypass).
```diff
-    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
+    return "".join(ch for ch in text
+                   if unicodedata.category(ch) not in {"Cf", "Cc", "Co", "Cs"}
+                   and not (unicodedata.category(ch) == "Mn" and unicodedata.combining(ch) == 0 and not _ARABIC_RANGE.match(ch))
+                   and ch != "⠀")
```
(keep Arabic Mn marks, which `_ARABIC_DIACRITICS` handles). Add the strings in probe_unicode_bypass.py as a parametrised regression test.

## N4 `unscreenable` is not enforced downstream
Only the /screen page and mobile /screen read `ScreeningResult.unscreenable`. `add_ubo` route says "screened clear" (`app.py:2302`, tests `res.hits` only), `onboard()` proceeds, `_persist` stores `hits=0, candidates=0, datasets_used=[]` with no marker, `rescreen_all` counts it as screened. Proposal: persist `unscreenable` (additive column on `screenings`), have onboarding/UBO routes return a manual-review flash, and raise a queue item.

## N5 CRLF in `customers.reference` suppresses the hourly freeze-overdue alert
`mail.send_freeze_obligation_alert` builds `msg["Subject"] = f"... {customer_reference}"` outside its try/except (mail.py:283-284); `EmailMessage` raises ValueError on CR/LF, so `check_unexecuted_freeze_obligations` raises for the whole org: obligations after the bad one are never alerted and the hourly run fails every time (probe_freeze_alert_subject: control alerted 3/3, attack 1/3). `POST /customers` accepts CR/LF in `reference` (probe_reference_crlf_web).
```diff
-    msg["Subject"] = f"[URGENT] TFS Freeze Obligation - {customer_reference}"
+    msg["Subject"] = "[URGENT] TFS Freeze Obligation - " + " ".join(str(customer_reference).split())[:80]
```
Plus reject control characters in `reference` at onboarding, and wrap the per-obligation send in try/except so one bad row cannot block the rest. Same check for the other `msg["Subject"]` sites that interpolate user data (mail.py:430 uses org_name).

## N6 goAML finalise accepts XML-illegal characters
`report_finalize_error` (#424) does not reject U+0000-0008, 000B, 000C, 000E-001F, D800-DFFF, FFFE/FFFF in text fields. A report with `\x0b` (common from Word/PDF paste) is marked `submitted`, and `/reports/{id}/export` returns 200 with non-well-formed XML (probe_goaml_ctrlchars). Proposal: strip or reject those characters in `save_report` and in `serialize_goaml_xml`, and validate again at finalise.

## N7 `/system/*` bearer compare crashes on non-ASCII header (static only, not exercised)
`secrets.compare_digest(auth_header, f"Bearer {secret}")` (app.py `system_refresh`, `system_check_freeze_obligations`) raises TypeError for a non-ASCII Authorization value (shown in isolation), so an unauthenticated request can get a 500 instead of 401. Fix: compare `.encode("utf-8")` bytes.
