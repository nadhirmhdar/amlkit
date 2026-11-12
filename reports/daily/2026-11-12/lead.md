# Lead consolidated report: 2026-11-12

## 1. Headline: AMBER (code unchanged, nothing new above LOW)
Master is `9219e2623b3a3ba7e73a20e44c703ab80df7e900`, the same SHA as the 11-08 to 11-11 lead reports. `git log 9219e26..origin/master` is empty and the newest PR is still #462. Run date 2026-11-12 UTC. All six role branches were present at the first fetch. Today's findings are confirmations or duplicates of open items: red-team's LM1 is L-138/MA1, and mlro-user's web run confirms L-140/L-141 on the web builder. The one new item is L-143 (LOW, no upper bound on report amount). All 16 carried defects still reproduce.

## 2. Per role
| Role | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer | done | GREEN, no change. CR-41/CR-42 carried. Web/mobile parity audit and input-boundary sweep (asked for in 11-11 "Next run") not done | ls-remote SHA, PR ref | High |
| qa-regression | done | GREEN, no change. Suite not re-run (2945 passed on `9219e26`) | ls-remote, empty `git log` | High |
| red-team | done | AMBER. Reviewed 35 SQL statements that lack `org_id` from `sql_scan.py`: 34 safe, 1 → LM1 (mobile can deactivate the last MLRO) | probe + evidence files on branch | High. LM1 duplicates L-138. **Still lists N3b/H1 as open (tenth reminder; refuted 11-08)** |
| compliance-specialist | done | AMBER, no change. CS-13, CS-14, 3.1 stand. Legal corpus BLOCKED | ls-remote, PR list | High |
| mlro-user | done | AMBER. 13 STR variants through the web builder: 8 invalid values finalise and export (incl. amount 1e30). Negative/non-numeric amounts refused at save; empty reason and VT char refused at finalise | driver + JSON log | High (log read; shared code path reproduced by lead) |
| skeptic | done | AMBER. LM1 = MA1 duplicate. RP1 confirmed on both surfaces. Parity check: reset-password aligned, mobile has no reactivate, last-MLRO guard is the only drift | file:line | High. Still carries N3b |

## 3. Consolidated findings
CONFIRMED (lead) = reproduced today on `9219e26` (output in §5).

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| L-138 MA1 / **LM1** (red-team 11-12): mobile `POST /api/v1/admin/operators/{id}/deactivate` (`api/mobile.py:1661`) has no last-active-MLRO guard | MED | mlro-user 11-10, red-team 11-12 | CONFIRMED, dup, Med | **CONFIRMED** (`checks_10`: mobile after=0, web refused) | HELD `scripts/proposals/2026-11-10-*` (red-team's `2026-11-12-new-findings.md` is the same fix) |
| L-140 RP1: report save/finalise skips date/country/email/IBAN checks; **now confirmed on web as well as mobile** | MED | mlro-user, skeptic | CONFIRMED, Med | **CONFIRMED** (`checks_11` 6/6; mlro-user web log 8/8) | HELD `2026-11-11-lead-goaml-report-validation.md` + addendum |
| L-141 gender rewrite `reporting/goaml.py:325`: anything other than `male` → `F`. **Reached through a hand-crafted web POST too** | MED | skeptic, mlro-user | CONFIRMED, Med | **CONFIRMED** (`checks_11` RP1g; code re-read, line 325 unchanged) | Same HELD proposal |
| **L-143** (new) amount `1e30` accepted. `cases/reports.py:110` refuses only negative/inf/nan | LOW | mlro-user | not rated separately | **CONFIRMED by code** (line 110; `float('1e30')` is finite) | Addendum `2026-11-12-lead-report-validation-addendum.md` (HELD; cap value needs Nadhir) |
| L-144 (new, INFO) no mobile route to reactivate an operator (`mobile.py` has only 1591/1619/1661 under `admin/operators`) | INFO | skeptic | n/a | CONFIRMED by grep | None. Matters only together with L-138 |
| L-142 RP2 non-XML 400 on export of an unfinalisable draft | LOW | mlro-user | Low | CONFIRMED (mlro-user web log, `export=400 not XML`) | Client/UX, no proposal |
| Other 34 SQL statements without `org_id` | — | red-team | AGREE | Accepted (categories are sound; not re-read individually) | Clean |
| L-134 SS5; L-135 RT1; L-136 RT2 | LOW / MED / LOW | carried | | CONFIRMED again (`checks_09` 3/3) | HELD 11-09 / Nadhir |
| L-129/130 SS1b/SS3b (CR-41/42); L-131 CS24; L-132 CS5d | LOW / LOW / MED / LOW | carried | | CONFIRMED again (`checks_08` 4/4) | HELD 11-08 |
| L-124/125/126 CR1-3; L-127 BL1 | MED / LOW-MED / LOW / LOW | carried | | CONFIRMED again (`checks_07` 4/4) | HELD 11-07 |
| L-112 UBO1b, L-113 N8b | LOW | carried | | CONFIRMED again (`checks_03` 2/2) | HELD / Nadhir |
| L-139 MA2, L-137, L-133 INFO-8, SS4, K2, SU1, CR-43, L-128 BL2, L-116 SS2b, CS-13, CS-14, 3.1, L-117, CR-39, F2b, CR-34, CR-35, I1, L-114, A1 residual, L-111, CR-4, CR-13, CR-18, CR-28, CR-29, PR5, K1, CS-4, FATF CS-1/6/7, E2-E5, F4, TA2/TA3, LN1, SE2, D1, CS-26, RP3 | as 11-11 | various | as stated | No code change | Carry |
| N3b, H1 | — | red-team, skeptic still list them | | REFUTED 11-08, no code change | Closed |
| FIXED on master since 11-11 | — | | | None (master unchanged) | — |

**Severity adjudication**
- LM1/L-138: red-team Medium, skeptic Medium. **MEDIUM**, merged into L-138. Skeptic's L-144 point makes it worse in practice, because a mobile-only mistake cannot be undone from mobile, and with no MLRO left it cannot be undone from the web either. It stays Medium (not High) because it is self-inflicted and recoverable out of band with the admin secret.
- L-143: **LOW**. It is a typing-error guard, not a control gap. FIU-side validation is unknown (XSD not in repo).
- Duplicates: LM1 = MA1, and RP1-web = RP1-mobile. No contradictions between roles. I agree with the skeptic's "roles don't read each other's findings" point, but per standing rules I do not tell roles to change their profiles. Raised to Nadhir in §6.

## 4. Combined assessment
1. Fifth day on the same SHA, no regression. All 16 carried defects reproduce.
2. The only new information confirms existing items: the web builder shares the report-validation gaps, and two roles independently hit the last-MLRO gap.
3. The open MEDIUM list (L-138, L-140, L-141, L-135, L-124, L-131) is small enough to land as one wave. Every item already has a HELD proposal.
4. Landing order is unchanged: L-138, then L-141 + L-140 (+ L-143), then the pre-Stripe sign-up batch.
5. Three things no session can check are still open: the live refresh schedule, the legal corpus and the goAML XSD.

## 5. Corrections I made
- **Owed from 11-11 "Next run":** re-ran `checks_2026_11_11.py`, `_10`, `_09`, `_08`, `_07`, `_03` from their lead branches. I copied them into `repro_lead/`, ran them, and deleted them; they were not re-committed. Environment: scratch venv, Python 3.11.18, `requirements.txt` + `requirements-dev.txt`, `PYTHONPATH=.`, OCR not exercised.
  ```
  === checks_2026_11_11  exit=0  RP1 reproduces=True (6/6 invalid values finalise and export); RP1g rewritten to F: ['M','other','unknown','attack helicopter']  2/2 reproduce
  === checks_2026_11_10  exit=0  MA1w web refused=True active_mlros_after=1; MA1 mobile body={'ok': True} before=1 after=0  1/1 reproduce
  === checks_2026_11_09  exit=0  SS5 / RT1 / RT2 reproduces=True  3/3 reproduce
  === checks_2026_11_08  exit=0  SS1b / SS3b / CS24 / CS5d reproduces=True  4/4 reproduce
  === checks_2026_11_07  exit=0  BL1 / CR1 / CR2 / CR3 reproduces=True  4/4 reproduce
  === checks_2026_11_03  exit=0  UBO1b reproduces=True; N8b reproduces=True  2/2 reproduce
  ```
- Verified by reading code on `9219e26`: `reporting/goaml.py:325` (gender ternary), `cases/reports.py:105-111` (amount accepts 1e30), and `api/mobile.py` admin routes at 1591/1619/1661 (no reactivate, no last-MLRO count).
- **Created `scripts/proposals/2026-11-12-lead-report-validation-addendum.md`** (HELD): it records web reachability and adds the L-143 amount cap. Not applied, because it is business logic (rule 3).
- No new repro script: L-143 is a one-line code read and is already in mlro-user's log. I edited no existing file. The secret scan of the new files is clean. The commit SHA is in the final reply.
- Not re-run: the full suite (no code change), red-team's `probe_last_mlro.py` (covered by `checks_10`), mlro-user's `webrep12` driver (the log was read and the shared path reproduced in-process).

## 6. Decisions needed from Nadhir
1. **Schedule one fix wave for the open MEDIUMs.** All of them have HELD proposals: L-138 (last MLRO, now found by two roles), then L-141 + L-140 (+ L-143 cap value), L-135, L-124, L-131. Master has not moved since 11-07, and the daily loop is now mostly re-confirming.
2. **No-MLRO recovery runbook** (skeptic): who holds `ADMIN_API_SECRET`, and how a tenant asks for recovery. This is the mitigation until L-138 lands.
3. **Role cadence** while master is frozen: whether the roles should read a shared findings register first (skeptic suggests #449's `reports/findings.csv`) to stop duplicate probe-days. This is your call; I have not changed any role.
4. Carried from 11-11: correct-and-refile design for finalised reports; the pre-Stripe sign-up batch L-129 + L-130 + L-134; L-135 DPMSR/REAR scope; production scheduler check / L-132; L-131; and the rest of the 11-11 §6.3 list (the corpus, the goAML XSD, the `github-advanced-security` 402 quota, and so on).

## 7. Next run: carried over
- From the repo root with `PYTHONPATH=.`, re-run `checks_2026_11_11.py`, `_10`, `_09`, `_08`, `_07`, `_03` from their lead branches. Copy them into `repro_lead/` first. Exit 1 means every item in that script is fixed.
- Owed by the lead: none.
- For the roles (suggestions only): code-reviewer, the web/mobile write-route parity audit and the input-boundary sweep (asked twice). Red-team and skeptic, drop N3b/H1. Compliance, MLRO-vacancy obligations once `corpus/` exists.
- Landing order: L-138, L-141 + L-140 + L-143, then L-129 + L-130 + L-134 (before Stripe), L-136, L-132 + production check, L-131, L-135 decision, L-124, L-127, L-125/L-126, L-113, L-116, L-112, CS-13, L-117, L-111, F2b, INFO-8.
