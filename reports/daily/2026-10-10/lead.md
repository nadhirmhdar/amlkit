# Lead consolidated report: 2026-10-10

## 1. Headline: AMBER
Master has had no commits for four days. Every Medium from 10-07 is still open and re-reproduced today. Two new areas were probed: document upload has one Medium integrity defect (L-43, a same-name upload overwrites earlier evidence), and the compliance-deadline API has several Low gaps (L-44).

Master is `01298484a7bfed106e9b2bd3a6238f98a4d2514b` (#426), the same SHA the 2026-10-07 lead report covered. The GitHub PR list (sorted by update) shows nothing opened or merged since #426 on 2026-10-06; the only activity is draft #411 (docs, a code-reviewer push). There were no lead runs on 10-08 or 10-09: all six roles say their 10-08/09/10 triggers arrived together on 10-10. Run date: 2026-10-10 UTC.

## 2. Per role
| Role (branch head) | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer (`e7daf0e`) | done (no-change) | AMBER unchanged; no new finding. CR-12, CR-4, CR-1b, CR-13, CR-14 and CR-18 open | `ls-remote`, `rev-list` count; suite count quoted from 10-07 | High |
| qa-regression (`323ab79`) | done (no-change) | GREEN; did not re-run the suite. The 10-07 result (2170 passed / 3 skipped) stands | `ls-remote` and PR list | High (nothing changed to test) |
| red-team (`c7ae071`) | done | AMBER: new area document upload. U1 same-name overwrite (Med), U2 `..`/`.`/300-char name gives 500 (Low), U3 odd extensions, no size cap, unvalidated `doc_type` (Low, contained) | Probe script plus evidence file; HELD proposal | High |
| compliance-specialist (`eca7519`) | done (no-change) | AMBER unchanged; CS-2 and CS-13 remain the most serious. Primary legal text still BLOCKED | `ls-remote`, SHA | High |
| mlro-user (`61daa20`) | done | AMBER: exports, evidence pack and cross-org isolation are sound. E1: the calendar cannot create a deadline. E2: the deadline API accepts nonsense. E3: a newline in a name drops the UBO diagram. E4 (no BOM) and E5 (officer exports) are PLAUSIBLE | HTTP driver, JSON logs, CSVs | High |
| skeptic (`1af5f85`) | done | AMBER: U1 to U3 and E1 to E3 CONFIRMED. E5 downgraded to Info (by design). Found that deadline PATCH ignores `due_date` and that update/delete are unaudited and have no role gate | `upload_overwrite.py`, file:line | High |

## 3. Consolidated findings
**CONFIRMED** means I re-ran a repro or read the cited lines on `0129848` today.

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-43** same-name upload overwrites the earlier document blob (`storage.py:66-67`, `:101-106`; only caller `mobile.py:1117`). U2 crashes share the root cause | **MEDIUM** | red-team U1/U2 | CONFIRMED, Med | CONFIRMED (re-ran `upload_overwrite.py`: `same stored_path: True \| ... matches stored bytes: False`, `'..' IsADirectoryError`, exit 0) | HELD in `scripts/proposals/upload-overwrite-and-deadlines.md` §1. Needs Nadhir to check GCS bucket versioning |
| **L-44** deadline API: PATCH ignores `due_date`/`recurrence`/`description`; update and delete unaudited; no role gate; free-text date breaks `is_overdue` (`app.py:4452`); no UI to create (E1) | LOW | mlro E1/E2, skeptic | CONFIRMED, Low | CONFIRMED (`checks_2026_10_10.py`: PATCH 200 with `due_date` unchanged; audit only `['compliance.deadline_created']`). The role gate was confirmed by reading `app.py:4479-4527`. No reminder code reads the table, so E2's reminder risk has no consumer | HELD, same file §2 |
| L-45 newline in a customer name drops the UBO diagram silently | LOW | mlro E3 | CONFIRMED, Low | CONFIRMED (role and skeptic). Needs a crafted request | Carry |
| U3 / E4 / E5 (upload extension and size, CSV BOM, officer CSV export) | LOW / LOW / INFO | red-team, mlro | contained / PLAUSIBLE / design | Accept the skeptic: E5 is Info (officers see the same data in the UI, and exports are audited) | Carry U3 size cap with L-43 |
| L-38 freeze obligation and CNMR on non-UAE-list hits (`review.py:163`) | MEDIUM-HIGH | compliance CS-2 | CONFIRMED, Med | CONFIRMED (re-ran `checks_2026_10_07.py`: `freeze_obligations=[{... 'sanctions','critical','pending_execution'}]`, exit 0). **New:** option (a) is viable. A UN+OFAC dual-listed person raises one alert per dataset (`DUAL hits=['un_sc_sanctions','us_ofac_sdn']`), so a UN-only freeze rule still sees the UN hit | HELD (`freeze-list-scope-and-totp-replay.md` §1). **Needs Nadhir** |
| L-28 `unscreenable` not persisted or acted on | MEDIUM-HIGH | CR-12, red-team N4 | Med | CONFIRMED (`engine.py` unchanged) | HELD, carried |
| L-29 invisible characters beyond Cf give a MISS | MEDIUM | red-team N3 | Med | CONFIRMED (unchanged) | HELD, carried |
| L-30 "Re-screening failed: 'customers'" banner | MEDIUM | mlro G9 | Med | CONFIRMED (re-ran `checks_2026_10_06.py`, exit 0). **Third report**; one-line fix | HELD `rescreen-banner-and-realert.md` §1 |
| L-9 rescreen re-alerts pending and dismissed matches | MEDIUM | mlro G10, CS-3 | Med | CONFIRMED (same run: `new open alerts [3, 4], reproduces=True`) | HELD, same file §2 |
| L-27 four-eyes legacy NULL-id or omitted-id residual | LOW | CR-1b, N8, CS-18 | Low | CONFIRMED (re-ran `four_eyes_ids.py`: live `refused`, legacy `ACCEPTED`, omitted `ACCEPTED`) | HELD, carried |
| L-40 TOTP replay | LOW | red-team M2 | Low | CONFIRMED (`first=True second=True`). `/mfa/verify` has a `5/minute` per-IP limit (`app.py:881-882`) on top of the per-operator lockout, which bounds abuse | HELD, carried |
| L-21 huge `page` OverflowError on `/audit` and feedback | LOW | skeptic | open | CONFIRMED (re-ran `offset_overflow.py`: `audit_trail OverflowError`, `feedback_list OverflowError`) | HELD, carried |
| L-39, L-41, L-42, L-34/35/36, L-37, L-31/32/33, L-5/L-20, L-14, H7/T1, L-23 (#417), L-3, L-6, L-10 to L-13, L-15, L-22, L-26, G3 to G8, F2b, CR-3, CR-14, CR-17 | as 10-07 | various | as 10-07 | Unchanged: no commit since 10-06 | Carry |
| Cross-tenant isolation (exports, evidence pack, PDF, alert panel); upload tenant check; path traversal | – | mlro, red-team | agree | No defect | – |

**Severity adjudication**
- **L-43 is MEDIUM.** Red-team and the skeptic agree, and so do I. These documents are CDD evidence held under the 10-year retention policy, and a phone re-sending `scan.pdf` is an ordinary accident. It is not higher because the sha256 audit row makes the loss detectable, and because GCS versioning (unknown) may make it recoverable.
- **L-44 is LOW** despite the missing audit rows: a deadline is a reminder aid, not a regulatory record. The unaudited delete is the part worth fixing first.

**Duplicates:** U2 is the same root cause as U1 (filename used as the storage key), and the fix in §1 closes both. E1, E2 and the skeptic's "missed #1" are merged as L-44.

**Nothing FIXED on master** this period: no commits.

## 4. Combined assessment
1. Four days without a commit; every Medium (L-38, L-28, L-29, L-30, L-9) still reproduces today. The team is re-confirming, not retiring.
2. The one new Medium (L-43) is an evidence-integrity defect in mobile uploads. Its fix is small and also removes U2's 500s.
3. The owed L-38 question is answered: dual-listed persons raise a separate UN alert, so "freeze only on UAE/UN-list hits" (option a) would not miss them.
4. Exports, the evidence pack and tenant isolation held under new probing.
5. The suite was not re-run on this SHA today; the 10-07 result (2170 passed) applies because no code changed.

## 5. Corrections I made
- C-1 Created `repro_lead/checks_2026_10_10.py`. Output on `0129848`, scratch venv (`requirements.txt` without passporteye/pdfminer; OCR not exercised):
  ```
  DUAL hits=['un_sc_sanctions', 'us_ofac_sdn'] alerts_by_dataset=['un_sc_sanctions', 'us_ofac_sdn']
  DL   PATCH due_date->2027-03-31: status=200 stored due_date=2026-12-31T00:00:00 -> reproduces=True
  DLA  delete status=204; deadline audit actions=['compliance.deadline_created'] -> reproduces=True
  exit 0
  ```
- C-2 Created `scripts/proposals/upload-overwrite-and-deadlines.md` (HELD). It contains diffs for L-43 and L-44, which change storage and route logic, so neither is applied.
- C-3 Owed item: re-ran `repro_lead/checks_2026_10_07.py` (CS-2 `reproduces=True`, M2 `first=True second=True`, exit 0) and `repro_lead/checks_2026_10_06.py` (G9 and L-9 reproduce, 4E id path refused, legacy row completed, exit 0). Nothing fixed.
- C-4 Owed item, "does a UN+OFAC listing raise a UN alert": answered by C-1 `DUAL` (yes, one alert per dataset; `engine.py:122-176` never merges across datasets).
- C-5 Owed item, the `/mfa/verify` rate limit: `app.py:881-882` reads `@limiter.limit("5/minute")  # per IP`. Done by reading the code. The limiter is disabled locally, so it was not exercised.
- C-6 Re-ran the skeptic's `upload_overwrite.py`, `four_eyes_ids.py` and `offset_overflow.py` (outputs quoted in §3).
- No tests added: each would fail on master (rule 5). No existing file edited. Commit SHA is in the final reply.

## 6. Decisions needed from Nadhir
1. **L-38 / L-39:** freeze scope, options (a), (b) or (c). Option (a) is now shown to be safe for dual-listed persons.
2. **L-43:** approve the unique-key fix. Run `gsutil versioning get` on the production documents bucket to learn whether past overwrites can be recovered.
3. L-30: the one-line banner fix plus a test (third request).
4. L-28 / L-29, L-9, L-27: as on 10-07.
5. L-44: approve the deadline API hardening (audit on update and delete, MLRO gate, honour `due_date`), or drop the calendar feature.
6. Carried: L-40, L-42, L-31/32/33 adviser confirmation, FATF snapshot, #417 (L-23) before merge, and the `github-advanced-security` 402 quota.

## 7. Next run: carried over
- Re-run `repro_lead/checks_2026_10_10.py` (this branch), `checks_2026_10_07.py` (10-07 lead) and `checks_2026_10_06.py` (10-06 lead; run it from inside the repo with `PYTHONPATH=.:tests`). Exit 1 means something was fixed; read the lines.
- Track landing of L-43, L-44, L-38, L-28, L-29, L-30, L-9, L-27, L-40, L-42, L-21, L-34, L-35, L-36.
- Not yet checked by anyone: the 10-04 sub-agent leads (any-MLRO global refresh, NULL-org audit rows visible across orgs, email enumeration), and the CSV BOM in Excel (E4).
