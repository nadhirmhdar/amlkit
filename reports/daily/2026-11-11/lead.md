# Lead consolidated report: 2026-11-11

## 1. Headline: AMBER (code unchanged; one new MEDIUM, worse than reported)
A goAML STR/SAR can be finalised, and so locked, with impossible or invalid values, and the exporter silently writes any gender other than `"male"` as `F`. That includes `"M"`, the value `save_report`'s own docstring tells callers to send (L-140 and L-141, both MEDIUM, CONFIRMED by the lead).

Master is `9219e2623b3a3ba7e73a20e44c703ab80df7e900`, the same SHA as the 11-08, 11-09 and 11-10 lead reports. `git log 9219e26..origin/master` is empty and the newest PR is still #462. Run date 2026-11-11 UTC. All six role branches were present at the first fetch. The no-change shortcut does not apply because mlro-user raised RP1-RP3.

## 2. Per role
| Role | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer | done | GREEN, no change. CR-41/CR-42 carried | ls-remote SHA, PR ref | High |
| qa-regression | done | GREEN, no change. Suite not re-run | ls-remote, empty `git log` | High |
| red-team | done | GREEN. First full tenant sweep since 10-04 on current routes: 65 path-param routes, 73 list routes, new-route checks. `HITS: []`, 0 org-A markers; controls have power | evidence files on branch | High. **Still lists N3b and H1 as open (ninth reminder; refuted 11-08)** |
| compliance-specialist | done | AMBER, no change. CS-13, CS-14, 3.1 stand; legal corpus BLOCKED | ls-remote, PR list | High |
| mlro-user | done | AMBER. RP1: finalise accepts garbage dates/country/gender/IBAN/email. RP2: export of an unfinalisable draft returns a non-XML 400. RP3: empty entity ref (info). Officer finalise refused (clean) | driver + JSON evidence | High (I reproduced RP1) |
| skeptic | done | AMBER. Confirms RP1 by code; found the gender rewrite (`goaml.py:325`). Flags "validator exists but not called" pattern | file:line | High. Still carries N3b |

## 3. Consolidated findings
CONFIRMED (lead) = reproduced today on `9219e26` (output in §5).

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-140** (new) RP1: report save/finalise (`cases/reports.py:26-111`, `cases/manager.py:3189`) never calls `validate_birth_date`/`validate_country_code` that onboarding uses (`manager.py:387-395`) | **MEDIUM** | mlro-user | CONFIRMED, Med | **CONFIRMED**: 6/6 invalid values finalise and export; onboarding control refuses the same birth date | HELD `scripts/proposals/2026-11-11-lead-goaml-report-validation.md` |
| **L-141** (new) gender rewrite `reporting/goaml.py:325`: any value ≠ `"male"` → `F`, including `"M"` | **MEDIUM** | skeptic (from mlro-user's run) | CONFIRMED, Med | **CONFIRMED**: `M`, `other`, `unknown`, `attack helicopter` → `<gender>F</gender>`. Web builder sends `male`/`female` and is right; mobile model is a free string, and `cases/reports.py:69` documents `"M"`/`"F"` | Same HELD proposal (map M/F/male/female, refuse the rest) |
| L-142 (new) RP2: export of an unfinalisable draft gives a non-XML 400 | LOW | mlro-user | Low | PLAUSIBLE (their run only; not re-run) | Client/UX; no proposal |
| RP3 empty entity reference on mobile | INFO | mlro-user | Info | Accepted (exporter `_require` refuses at export) | None |
| Tenant isolation on current routes | — | red-team | AGREE | Accepted on their evidence (controls show power) | Clean |
| L-138 MA1 mobile deactivates last MLRO; L-139 MA2 | MED / LOW | carried | Med / Low | CONFIRMED again (`checks_10`) | HELD 11-10 proposal |
| L-134 SS5; L-135 RT1; L-136 RT2 | LOW / MED / LOW | carried | | CONFIRMED again (`checks_09` 3/3) | HELD 11-09 / Nadhir |
| L-129/130 SS1b/SS3b (CR-41/42); L-131 CS24; L-132 CS5d | LOW / LOW / MED / LOW | carried | | CONFIRMED again (`checks_08` 4/4) | HELD 11-08 |
| L-124/125/126 CR1-3; L-127 BL1 | MED / LOW-MED / LOW / LOW | carried | | CONFIRMED again (`checks_07` 4/4) | HELD 11-07 |
| L-112 UBO1b, L-113 N8b | LOW | carried | | CONFIRMED again (`checks_03` 2/2) | HELD / Nadhir |
| L-137, L-133 INFO-8, SS4, K2, SU1, CR-43, L-128 BL2, L-116 SS2b, CS-13, CS-14, 3.1, L-117, CR-39, F2b, CR-34, CR-35, I1, L-114, A1 residual, L-111, CR-4, CR-13, CR-18, CR-28, CR-29, PR5, K1, CS-4, FATF CS-1/6/7, E2-E5, F4, TA2/TA3, LN1, SE2, D1, CS-26 | as 11-10 | various | as stated | No code change | Carry |
| N3b, H1 | — | red-team, skeptic still list | | REFUTED 11-08, no code change | Closed |
| FIXED on master since 11-10 | — | | | None (master unchanged) | — |

**Severity adjudication**
- L-140: mlro-user Medium, skeptic Medium. **MEDIUM.** MLRO-only, audited, and the FIU's own validation will reject most of it, but finalising locks the record and the only remedy is a second report.
- L-141: **MEDIUM, kept separate from L-140.** It is a different defect class: a silent change of a personal attribute in a regulatory filing, not a missing check. FIU validation will *not* catch it, because `F` is a valid code. Impact on the web builder today is limited to non-`male`/`female` values, which the `<select>` does not offer, so the live exposure is the mobile API and any hand-crafted POST. I would have rated it HIGH if the web builder sent `M`. It is the cheapest fix on the list (one line plus a mapping).
- Skeptic point 2 (other guessing mappers): I read `goaml.py:316-420`. Gender is the only `if … else` default mapping. `transmode_code`, ID type and nationality pass through verbatim (unchecked, covered by L-140), not rewritten.
- Duplicates: RP3 is covered by `_require`. No contradictions between roles today.

## 4. Combined assessment
1. No code change and no regression. Red-team's fresh tenant sweep on the current route set is clean, which closes the biggest unknown since the router split.
2. L-140/L-141 are real, and L-141 corrupts a filing silently. Both share one HELD proposal, which reuses existing validators.
3. Landing order: L-138 (last MLRO), then L-141/L-140, then the pre-Stripe sign-up batch.
4. The skeptic's pattern holds for the fifth time: a rule exists and one entry point skips it. One "validate per record type, called at save and finalise" step is the structural fix.
5. The unknowns no session can check are unchanged: the live refresh schedule (L-132), the legal corpus and the goAML XSD.

## 5. Corrections I made
- **Owed from 11-10 "Next run":** re-ran `checks_2026_11_10.py`, `_09`, `_08`, `_07`, `_03` from their lead branches. They were copied into `repro_lead/` (they resolve `tests/` relative to their own path), run, and deleted, not re-committed. Scratch venv, Python 3.11.18, `requirements.txt` + `requirements-dev.txt`, `PYTHONPATH=.`, OCR not exercised:
  ```
  === checks_2026_11_10  exit=0  MA1w web refused=True active_mlros_after=1; MA1 mobile body={'ok': True} before=1 after=0  1/1 reproduce
  === checks_2026_11_09  exit=0  SS5 / RT1 / RT2 reproduces=True  3/3 reproduce
  === checks_2026_11_08  exit=0  SS1b / SS3b / CS24 / CS5d reproduces=True  4/4 reproduce
  === checks_2026_11_07  exit=0  BL1 / CR1 / CR2 / CR3 reproduces=True  4/4 reproduce
  === checks_2026_11_03  exit=0  UBO1b reproduces=True (3 suffix variants accepted); N8b reproduces=True  2/2 reproduce
  ```
- **Created `repro_lead/checks_2026_11_11.py`** (temp DB, invite mode, limiter off, no network). It drives the shared code path `save_report` → `report_finalize_error` → `inject_reporting_entity` + `serialize_goaml_xml`. Output on `9219e26`, `exit=0`:
  ```
  RP1   birth_date=2999-01-01            -> finalise-accepted
  RP1   birth_date=not-a-date            -> finalise-accepted
  RP1   transaction_date=2030-01-01      -> finalise-accepted
  RP1   nationality=ZZ                   -> finalise-accepted
  RP1   reporter_email=not-an-email      -> finalise-accepted
  RP1   source_account=12345             -> finalise-accepted
  RP1   reproduces=True (6/6 invalid values finalise and export)
  RP1c  control: onboarding refuses birth_date=2999-01-01 (birth_date cannot be in the future)
  RP1g  gender='male'  -> <gender>='M'   gender='female' -> 'F'
  RP1g  gender='M' / 'other' / 'unknown' / 'attack helicopter' -> <gender>='F'
  RP1g  reproduces=True (rewritten to F: ['M', 'other', 'unknown', 'attack helicopter'])
  2/2 reproduce
  ```
- **Created `scripts/proposals/2026-11-11-lead-goaml-report-validation.md`** (HELD). It covers a gender mapping that refuses unknown values; birth-date, country, future-transaction-date and email checks in `save_report`, repeated in `report_finalize_error` for old drafts; a docstring fix; and a test. IBAN format is deliberately left out (goAML accounts are not always IBANs). Not applied because it touches business logic (rule 3). The test is not committed because it fails on master.
- I edited no existing file. The secret scan of the new files is clean. The commit SHA is in the final reply.
- Not re-run: the full suite (no code change; last run 2945 passed on `9219e26`), mlro-user's `mobrep11` driver (reproduced in-process instead), RP2, red-team's sweep.

## 6. Decisions needed from Nadhir
1. **L-141 + L-140 (new):** approve the HELD proposal. L-141 is a one-line fix that stops silent mis-filing. Land it right after L-138.
2. **Correct-and-refile** for a finalised report (skeptic point 3; same gap as CR1/L-124): design once for customers and reports, or accept "new report supersedes" as the documented remedy.
3. Carried from 11-10: L-138 approval; the pre-Stripe sign-up batch L-129 + L-130 + L-134; L-135 DPMSR/REAR (I recommend stating STR/SAR/CNMR-only, plus L-136); cadence (this run supports option (a): mlro-user's new probe area found two real defects); production scheduler check and the L-132 read-back; L-131; the no-active-MLRO runbook; and the rest of the 11-10 §6.4 list (SU1, L-116, BL1, L-113, L-112, CS-13/14/3.1 corpus, F2b, SMTP, L-111, CR-29, PR5, K1, CR-4/#417, FATF snapshot, the `github-advanced-security` 402 quota, the goAML XSD).

## 7. Next run: carried over
- From the repo root with `PYTHONPATH=.`, re-run `repro_lead/checks_2026_11_11.py` (this branch) plus `checks_2026_11_10.py`, `_09`, `_08`, `_07`, `_03` from their lead branches. Copy them into `repro_lead/` first. Exit 1 means every item in that script is fixed.
- Owed by the lead: none.
- For the roles: mlro-user, run the RP1 variants through the web builder `POST /reports` (shared path, expected same) and an organisation with no entity reference. Code-reviewer, the web/mobile write-route parity audit (assigned 11-10, not yet done), plus an input-boundary sweep against `datamodel` validators (skeptic point 4). Red-team and skeptic, drop N3b/H1 (ninth reminder). Compliance, MLRO-vacancy obligations once `corpus/` exists.
- Landing order: L-138, L-141 + L-140, then L-129 + L-130 + L-134 (before Stripe), L-136, L-132 + production check, L-131, L-135 decision, L-124, L-127, L-125/L-126, L-113, L-116, L-112, CS-13, L-117, L-111, F2b, INFO-8.
