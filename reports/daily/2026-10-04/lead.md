# Lead consolidated report: 2026-10-04

## 1. Headline: AMBER
There is no cross-tenant leak and no production incident, but two confirmed defects need a decision:
- **Four-eyes bypass by renaming an operator (from #409).** An MLRO can rename the proposer and then confirm their own sanctions dismissal. The record then states that an independent review took place.
- **Silent Arabic-name screening miss.** A name pasted as Arabic presentation-form characters screens as "clear".

Both are HELD for Nadhir; neither is fixable within the additive-only rule.

- Master: `05e612d2d69841e0c18d9abe92f1d0126da14c41` (#406, login page only; roles scoped to `fc80e9f`; the files they cite are unchanged between the two, checked with `git diff --stat fc80e9f4 05e612d`).
- This is the first lead run. No earlier `routine/*-lead` branch exists, so there is no "no change" baseline.

## 2. Per role
| Role | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer (`caf90ec`) | done (arrived 19:55, after the skeptic's 19:48 cut-off; the skeptic's "MISSING" is superseded) | RED: four-eyes rename bypass (CR-1). Diff review of 8 PRs found no other defect. | Repro output + file:line | High |
| qa-regression (`ee7ad43`) | done | 1897 passed / 19 failed. All 19 failures are a missing `passporteye`, so they are environmental. The earlier isolation failures did not reproduce (30/30). | Commands + counts | High (OCR area unverified) |
| red-team (`08798e8`) | done | 14 findings (F1–F14), all reproduced locally. PR #412 tenant sweeps are clean. | 9 probe scripts + evidence files | High for repro; severities inflated in places |
| compliance-specialist (`ca6d485`) | done | AMBER: the FATF fallback is reported as a fresh load; freeze wording appears on EU-only hits; dismissed false positives re-alert. | file:line; no legal corpus in repo, so the Article citations are PLAUSIBLE | Medium |
| mlro-user (`1bb42ee`) | done | RED: four-eyes bypass over HTTP; a finalised STR that cannot be exported; the goAML entity reference is not used. | HTTP driver + JSON log | High |
| skeptic (`7313225`) | done | AMBER: confirmed most findings and downgraded four-eyes and FATF. Refuted F9 (wires). Added 4 missed items. | 3 repro scripts | High; one factual error (see C-4) |

## 3. Consolidated findings
Verdict key: **CONFIRMED** means I reproduced it or read the cited lines on `05e612d` today. **CONFIRMED (role)** means a role reproduced it with pasted output and I did not re-run it. **PLAUSIBLE** means it is unevidenced or depends on production or legal facts.

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| L-1 four-eyes bypass via rename (`review.py` confirm name compare × `operators.py:232-281`) | **HIGH** | code-reviewer CR-1, red-team F4, mlro-user F1 | CONFIRMED, Medium | CONFIRMED (re-ran `four_eyes_rename.py`, exit 0) | HELD in `scripts/proposals/four-eyes-operator-id.md` |
| L-2 Arabic presentation forms / zero-width chars give `canonical_key=''`, a silent clear (`names/arabic.py:59`) | **HIGH** | red-team F1 | CONFIRMED, High | CONFIRMED (re-ran `presentation_forms.py`, exit 0) | HELD (red-team `scripts/proposals/screening-name-matching.md`); needs Nadhir |
| L-3 one extra name token or an attribute mismatch drops an exact name below 0.85 (`scorer.py`) | MEDIUM | red-team F2 | CONFIRMED, High/Medium | CONFIRMED (role) | Needs Nadhir: threshold/calibration is a product decision |
| L-4 goAML entity reference: `/admin` renders it blank, the next save writes NULL, and the STR builder hard-codes `GROVISOR-LIC-2026` | MEDIUM | mlro-user F3, skeptic | CONFIRMED | CONFIRMED (`repro_lead/goaml_entity_ref_wipe.py`, exit 0) | HELD in `scripts/proposals/goaml-entity-reference.md` |
| L-5 FATF fallback (Feb 2025 data) recorded as a fresh load; FATF absent from `heartbeat.py` | MEDIUM | compliance CS-1 | CONFIRMED, Medium | CONFIRMED (`parse(b'')` gives 26 entities; `fatf.py:252-265`; no FATF in `scripts/heartbeat.py`) | Needs Nadhir (snapshot pattern like Wikidata #400) |
| L-6 `rescreen_all` skips owners under 25%, nominees and directors on list updates (`engine.py:420-424`) | MEDIUM | red-team F3 | CONFIRMED, Medium | CONFIRMED (role) | Needs Nadhir |
| L-7 STR can be finalised without the required account, then can never be exported or edited | MEDIUM | mlro-user F2 | not re-run | CONFIRMED (role, HTTP log) | Carry; propose next run |
| L-8 `/admin/org-profile` has no CSRF check | LOW | red-team F5, skeptic | CONFIRMED, Low | CONFIRMED (re-ran `csrf_scan.py`: 5 of 61 routes, 3 of them `/system/*` bearer routes) | HELD (red-team `org-profile-csrf.md`); folded into L-4 proposal |
| L-9 dismissed false positives and `pending_review` alerts re-alert on every refresh (dedupe is `status='open'` only) | LOW-MED | compliance CS-3, skeptic missed-2 | CONFIRMED | CONFIRMED by code (`engine.py:344-351`) | Carry |
| L-10 freeze wording / auto-freeze on EU/UK-only hits | MEDIUM (legal) | compliance CS-2 | PLAUSIBLE | PLAUSIBLE: mechanism is real, legal scope unverifiable | Needs Nadhir / adviser |
| L-11 freeze-clock start, overdue-freeze check unscheduled on Cloud Run, AED 55k threshold configurable to 1M, UBO tiers (PR #410 items) | MEDIUM | compliance | 3.1 CONFIRMED | PLAUSIBLE except 2.2 (code-reviewer spot check) and 3.1 | Needs Nadhir (PR #410) |
| L-12 KYT: out-of-order structuring, `amount_aed` unchecked for AED, `id(conn)` cache, NaN/inf 500s, NaN threshold | LOW | red-team F6–F8, F12, F14 | CONFIRMED, Low | CONFIRMED (role) | HELD (red-team `kyt-hardening.md`, `small-fixes.md`) |
| L-13 weak password on reset gives HTTP 500 (`app.py:3414-3417`) | LOW | red-team F11 | CONFIRMED by code | CONFIRMED by code (length check only, then `auth.set_password`) | HELD (`small-fixes.md`) |
| L-14 rename accepts case-variant / homoglyph duplicates | LOW | mlro-user F4, red-team F10 | CONFIRMED | CONFIRMED (role); duplicates | Included in L-1 proposal |
| L-15 goAML XML layout differs from 5.0 STR | MEDIUM? | mlro-user F5 | PLAUSIBLE | PLAUSIBLE: BLOCKED on the FIU XSD | Needs Nadhir to supply the XSD |
| L-16 wires/cheques never aggregate | none | red-team F9 | REFUTED | REFUTED: documented design (`kyt.py:38-47`) | Close |
| L-17 `sync_replica` in the `finally:` of a failing refresh | LOW | code-reviewer CR-2 | – | PLAUSIBLE | Carry |
| Sub-agent static items (any-MLRO refresh, NULL-org audit rows, email enumeration, upload overwrite) | ? | red-team | UNEVIDENCED | PLAUSIBLE | Carry; verify next run |
| Cross-tenant isolation | – | red-team, qa (PR #412) | not re-run | No defect reported (`HITS: []`) | – |

## 4. Combined assessment
1. Tenant isolation held under two independent sweeps, and the test suite is green apart from the OCR dependency.
2. The day's most important change is a regression from #409: the four-eyes evidence for a sanctions dismissal can now be falsified.
3. Screening has a real silent-miss class (Unicode normalisation), and its recall depends on a precision term (L-3) that deserves a calibration review.
4. Regulatory-output plumbing (goAML reference, unexportable finalised STRs, XML schema) is the weakest area for an inspector.
5. Severity: L-1 is HIGH, not RED as mlro-user and code-reviewer rated it, and not Medium as the skeptic did (reasoning in the proposal: the single-operator mode records honestly, the rename path does not).

## 5. Corrections I made
- C-1 Created `repro_lead/goaml_entity_ref_wipe.py` (exit 0 = reproduces). Output on `05e612d`: `after first save: TEST-ORG-0001` / `/admin input value: ''` / `after second save (phone-only edit): None`, `exit=0`.
- C-2 Created `scripts/proposals/four-eyes-operator-id.md` and `scripts/proposals/goaml-entity-reference.md`. Both are HELD because they change route or business logic, or the schema.
- C-3 Re-ran the skeptic repros on `05e612d` in a scratch venv (no `passporteye`/`pdfminer`, so OCR was skipped): `four_eyes_rename` exit 0, `presentation_forms` exit 0 (`canonical_key(pf)=''`), `csrf_scan` exit 0 (`/logout`, `/admin/org-profile`, 3× `/system/*`).
- C-4 Corrected the skeptic: the claim that the saved goAML reference "is not read by any reporting code" is wrong. `reporting/goaml.py:78-102` reads it, but only as a fallback that the builder's hard-coded prefill always pre-empts.
- C-5 Corrected the skeptic: the code-reviewer report was not missing; it arrived at 19:55 UTC, after the skeptic's poll.
- No tests were added: every candidate regression test fails on master, so rule 5 forbids committing it. No existing file was edited. Commit SHA is in the final reply.

## 6. Decisions needed from Nadhir
1. L-1: approve the interim rename guard now and the `operator_id` migration next. Until then, consider rolling back rename for operators with pending proposals.
2. L-2/L-3: approve NFKC plus format-char stripping in `canonical_key`, and a calibration review of the extra-token penalty.
3. L-4/L-8: approve the goAML reference fix and the org-profile CSRF check.
4. L-5: approve a committed FATF snapshot with max-age refusal and a dashboard "fallback" flag.
5. L-10/L-11: legal view on EU/UK/OFAC freeze scope and the freeze-clock start (PR #410).
6. L-15: supply the goAML 5.0 STR XSD so the export can be validated.
7. Infra: `github-advanced-security` fails on PRs #412/#413 with a Copilot quota error (402). Restore the quota or make the check non-required.

## 7. Next run: carried over
- L-7 (STR finalise-without-account): write a repro and a proposal.
- L-9 (`pending_review` duplicate alert): write a repro.
- L-17, the four sub-agent static items, and red-team F13 (diagram cost): verify.
- OCR suite: still unverified outside CI.
- PR #410 items beyond 2.2/3.1: verify the file:line references.
- Track whether L-1/L-2/L-4 proposals land on master.
