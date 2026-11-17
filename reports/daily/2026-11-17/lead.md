# Lead consolidated report: 2026-11-17

## 1. Headline: AMBER (code unchanged ten days; one new MEDIUM: the web alert queue and both alert CSV exports silently stop at 200)
Master is `9219e2623b3a3ba7e73a20e44c703ab80df7e900` (`git ls-remote` today), same SHA as every lead report since 11-08; newest PR still #462 (code-reviewer, QA, compliance agree; compliance notes draft #411, docs only, updated today). Run date 2026-11-17 UTC. All six role branches present at first fetch. New today: L-156 (QU1, reframed by the skeptic and widened by the lead to the mobile CSV). Owed items from 11-16 done: red-team's Arabic probe re-run in full (11/86 misses, matches), TD2 moved to CONFIRMED. All 26 carried checks still reproduce.

## 2. Per role
| Role | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer | done | GREEN, no change; CR-41/CR-42 carried | ls-remote SHA, PR ref | High |
| qa-regression | done | GREEN, no change; suite not re-run (2945 passed, 2 skipped on `9219e26`) | ls-remote, empty `git log` | High |
| red-team | done | GREEN for area: UBO diagram at 200 rows / depth 10 with 10 hostile names renders in 0.43 s, no script/external href | probe + evidence file (not re-run by lead) | Medium-high (generator output only, not browser) |
| compliance-specialist | done | AMBER, no change; CS-13, CS-14 stand; corpus BLOCKED | ls-remote, PR list | High |
| mlro-user | done | AMBER: QU1 (no paging/search), QU2 (bad filters silent), QU3 (dup of CR2) | driver + JSON log | Medium: tested 120 alerts (< cap) so missed the real defect; QU2 "no message" contradicted by code and by lead run |
| skeptic | done | AMBER: QU1 is a silent 200 cap (Medium); QU2 partly refuted; QU3 = CR2 | file:line + existing query-level script | High; missed the mobile CSV caller (`mobile.py:1492`) |

## 3. Consolidated findings
CONFIRMED (lead) = reproduced today on `9219e26` (output in §5).

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-156 QU1** (new): `/alerts` (`routers/alerts.py:147`, grouped `:138`), `/alerts.csv` (`:281`) and mobile `/api/v1/alerts.csv` (`mobile.py:1492`) call `alert_queue` (`queries.py:480`, `limit=200`) with no limit/offset and no notice; dashboard shows the true count | **MED** | mlro-user (as "no paging"), skeptic (as cap) | CONFIRMED (reframed), Med | **CONFIRMED** (205 open: page 200 rows, no notice, dashboard "205 waiting"; web CSV 200; mobile CSV 200) | HELD `scripts/proposals/2026-11-17-lead-alert-queue-cap.md` |
| L-157 QU2 (new): unknown `status/sort/category/group_by` silently defaulted | INFO | mlro-user | PARTLY REFUTED, Info | **REFUTED** as stated: `?status=bogus` renders "Unknown filter ignored." (`alerts.html:18`, lead run True). `?page`/`?q` are not parameters, so ignored with no message (part of L-156 UX) | Close; prominence is UX |
| QU3 (new): identical name+DOB onboarded without warning | (as L-125) | mlro-user | dup CR2 | **Duplicate of L-125 CR2** (`checks_07` CR2 reproduces) | Merge into L-125 |
| UBO diagram hostile names / load | none | red-team | AGREE clean | Accepted (not re-run) | Closes red-team's 10-04 "unbounded diagram" item |
| L-155 TD2: free text uncapped, NUL/RTL stored | LOW | red-team (11-14), skeptic | CONFIRMED, Low | **CONFIRMED** (owed item: 1 MB case note with NUL + U+202E stored unchanged) | Carry; same class as CR-29; fold into input-normalisation proposal (11-16 §2-4) |
| L-154 N3c Urdu heh etc. | MED (Urdu heh) | red-team, skeptic | CONFIRMED | **CONFIRMED**; full probe 11/86 below 0.85 (Urdu heh 0.60 and 0.35; `teh marbuta->teh`, `tah->teh` on Fatima are misspellings, not script variants) | HELD 11-16 §4 |
| L-149 CL1 / L-150 CL2 / L-151 TD1 / L-152 TX1 / L-153 TX2 | MED / LOW / MED / LOW-MED / LOW | carried | CONFIRMED | CONFIRMED (`checks_16` 6/6) | HELD 11-16 |
| L-145..L-148 SO1, RL1, RL2/RL2d, RL3 | MED / LOW-MED / LOW-MED / LOW | carried | | CONFIRMED (`checks_13` 5/5) | HELD 11-13 |
| L-138 MA1 | MED | carried | | CONFIRMED (`checks_10`) | HELD 11-10 |
| L-140 RP1, L-141 gender rewrite | MED / MED | carried | | CONFIRMED (`checks_11` 2/2) | HELD 11-11 |
| L-134 SS5; L-135 RT1; L-136 RT2 | LOW / MED / LOW | carried | | CONFIRMED (`checks_09` 3/3) | HELD 11-09 |
| L-129/130 SS1b/SS3b; L-131 CS24; L-132 CS5d | LOW / LOW / MED / LOW | carried | | CONFIRMED (`checks_08` 4/4) | HELD 11-08 |
| L-124/125/126 CR1-3; L-127 BL1 | MED / LOW-MED / LOW / LOW | carried | | CONFIRMED (`checks_07` 4/4) | HELD 11-07 |
| L-112 UBO1b, L-113 N8b | LOW | carried | | CONFIRMED (`checks_03` 2/2) | HELD |
| L-143, L-144, L-142 RP2, L-139 MA2, L-137, L-133, SS4, K2, SU1, CR-41, CR-42, CR-43, L-128, L-116, CS-13, CS-14, rest of 11-13 carry list | as 11-13 | various | as stated | No code change | Carry |
| N3b, H1 | — | red-team, skeptic still list | | REFUTED 11-08 | Closed (roles still carry them) |
| FIXED on master since 11-16 | — | | | None (master unchanged) | — |

**Severity adjudication**
- **L-156 QU1: MEDIUM (skeptic) over mlro-user's Low-Medium.** The queue ordering keeps the top-priority 200 visible, which alone would be Low-Medium. The deciding factor is the CSV: its default is `status=all`, so open + closed history counts toward 200, an org reaches it far sooner than 200 *open* alerts, the export is incomplete with no marker, and the audit row records `rows: 200` as if complete. The mlro-user's "multi-megabyte page" scenario is wrong (capped); the skeptic is right on mechanism but missed the third caller (mobile CSV), found by grep and confirmed by run.
- **QU2: REFUTED, not "partly".** The lead run shows the message on `?status=bogus`; mlro-user's driver apparently did not check for it. Adopt the skeptic's checklist point (read the handler before filing "silent").
- Contradiction noted: the proposal's obvious fix (`limit=-1`) would return zero rows because `alert_queue` slices in Python (`queries.py:554`); the proposal uses `limit=None`.

## 4. Combined assessment
1. Tenth day on `9219e26`; no regression; 26/26 carried checks and 4/4 new checks reproduce.
2. New class: silent truncation (a list or export that omits rows with no marker), alongside last week's input-normalisation class.
3. Open MEDIUMs now 13: L-156, L-149, L-151, L-154, L-145, L-138, L-140, L-141, L-135, L-124, L-131, plus L-146/L-152 at LOW-MED. Every one has a HELD proposal.
4. Skeptic and lead both recommend a fix wave; the open list grows about one Medium a day while master is frozen.
5. Still unverifiable here: live refresh schedule, legal corpus (whether an inspector is owed a complete alert export), goAML XSD, production FX policy, real alert volumes per org.

## 5. Corrections I made
Scratch venv (Python 3.11.18, `requirements.txt` + `requirements-dev.txt`), repo root, `PYTHONPATH=.`; OCR not exercised. No existing file edited.
- **Owed 1 (from 11-16): carried checks re-run** (copied from lead branches into `repro_lead/`, not re-committed):
  ```
  checks_2026_11_16 exit=0  6/6 reproduce (CL1, CL2, TD1, TX1, TX2, N3c)
  checks_2026_11_13 exit=0  5/5 reproduce
  checks_2026_11_11 exit=0  2/2 reproduce
  checks_2026_11_10 exit=0  1/1 reproduce
  checks_2026_11_09 exit=0  3/3 reproduce
  checks_2026_11_08 exit=0  4/4 reproduce
  checks_2026_11_07 exit=0  4/4 reproduce
  checks_2026_11_03 exit=0  2/2 reproduce
  ```
- **Owed 2: red-team `probe_arabic_letter_variants.py` re-run in full** (from `routine/2026-11-16-red-team`; output committed as `reports/daily/2026-11-17/evidence/lead_probe_arabic_letter_variants_on_9219e26.txt`):
  ```
  86 variants scored; below the 0.85 alert threshold: 11
    MISS 0.60  beh->peh / Sindhi kaf / feh->veh / Kurdish reh / Urdu heh / Kurdish lam
    MISS 0.35  Urdu heh (from 'فاطمة الزهراء')
    MISS 0.45  teh marbuta->teh / feh->veh / tah->teh ; 0.35 zain->zheh  (from 'فاطمة الزهراء')
  exit=0
  ```
  Identical to red-team's 11-16 evidence. Urdu heh misses on both names that contain heh.
- **Owed 3: TD2 check** done inside the new script (below). L-155 now CONFIRMED.
- **Created `repro_lead/checks_2026_11_17.py`** (exit 0 while any reproduces):
  ```
  setup open alerts in DB: web org=205 mobile org=205
  QU1w  /alerts distinct alert ids=200 cap-notice=False; dashboard says 205 waiting
  QU1c  web /alerts.csv status=200 data rows=200
  QU1m  mobile /api/v1/alerts.csv status=200 data rows=200
  QU2   ?status=bogus shows 'Unknown filter ignored.'=True; ?page=2 shows it=False (control, not counted)
  TD2   1 MB note with NUL+U+202E stored unchanged=True (len=1048584)
  4/4 reproduce
  exit=0
  ```
- **Created `scripts/proposals/2026-11-17-lead-alert-queue-cap.md`** (HELD, route logic): paged web queue with "showing X-Y of N" notice, uncapped CSV exports via `limit=None`, three tests.
- Code read on `9219e26`: `queries.py:480-560, 592-597`, `routers/alerts.py:114-152, 273-295`, `mobile.py:1331, 1488-1496`, `alerts.html:18`, `dashboard.html:99`.
- Not re-run: full suite (no code change), red-team's UBO diagram probe, mlro-user's `queue17` driver.

## 6. Decisions needed from Nadhir
1. **Alert export completeness (L-156):** uncapped CSV (streamed if large) for web and mobile, and a paged web queue with a count notice? Recommend yes; small change.
2. Carried from 11-16, still open: closure with open TFS work (L-149: hard block vs MLRO override); FX plausibility (L-152); letter folds (L-154: six unambiguous now, `پ ژ ڤ` after a false-positive run).
3. **Fix wave:** master frozen since 11-07, 13 Mediums open. Suggested order: L-151 + L-154 + L-156 (small, low risk), then L-138 + L-145..L-148, then L-149/L-150, then L-141 + L-140 + L-143.
4. Carried: single-operator rule (L-145), role change (L-146), no-MLRO recovery runbook, correct-and-refile, pre-Stripe batch L-129 + L-130 + L-134, L-135 scope, production scheduler check / L-132, L-131, corpus, goAML XSD, `github-advanced-security` 402 quota.

## 7. Next run: carried over
- Re-run `checks_2026_11_17.py`, `_16`, `_13`, `_11`, `_10`, `_09`, `_08`, `_07`, `_03` from their lead branches (copy into `repro_lead/`; `PYTHONPATH=.`). Exit 1 means every item in that script is fixed.
- Owed by the lead: none new. Optional: grep the other capped list helpers (transaction alert queue, adverse media, audit) for the same silent-truncation pattern (skeptic point 2) and add any hit to a checks script.
- For the roles (suggestions only): mlro-user, test lists above their caps and check the handler before filing "silent"; skeptic, caller-count sweep for capped helpers; red-team and skeptic, drop N3b/H1.
- Landing order: L-151 + L-154 + L-156, L-138 + L-145..L-148, L-149/L-150, L-141 + L-140 + L-143, L-152/L-153/L-155, then the 11-13 order (L-129 + L-130 + L-134, L-136, L-132, L-131, L-135, L-124, L-127, L-125/L-126, L-113, L-116, L-112, CS-13, L-117, L-111, F2b, INFO-8).
