# Lead consolidated report: 2026-11-09

## 1. Headline: AMBER (unchanged code, two new product findings)
Master has not moved since yesterday and nothing regressed. The roles raised two new findings. First, the open sign-up form lets an anonymous visitor put their own text and URL into groAML's verification mail (L-134, LOW, but it must be fixed before Stripe goes live). Second, groAML cannot create the DPMSR and REAR reports that its target sectors (real estate, precious metals) file (L-135, MEDIUM, a product decision).

Master is `9219e2623b3a3ba7e73a20e44c703ab80df7e900`, the same SHA as the 2026-11-08 lead report. `git log 9219e26..origin/master` is empty and the newest PR is still #462. Run date 2026-11-09 UTC. All six role branches were present at the first fetch. The no-change shortcut does not apply because red-team (SS5) and mlro-user (RT1 to RT3) raised new findings.

## 2. Per role
| Role | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer | done | GREEN, no change. CR-41 and CR-42 carried | ls-remote SHA, PR ref | High |
| qa-regression | done | GREEN, no change. Suite not re-run; last result on this SHA was 2945 passed, 2 skipped | ls-remote and an empty `git log` | High |
| red-team | done | AMBER. A real local SMTP sink confirms SS3b (4 notices in 4 attempts) and adds SS5 (the visitor's name, with markup and a URL, is in the mail greeting). Header injection is clean | probe script plus sink evidence file | High (I reproduced SS5). **Still lists N3b and H1 as open (seventh reminder; both refuted)** |
| compliance-specialist | done | AMBER, no change. CS-13, CS-14 and 3.1 stand. The legal corpus is still BLOCKED | ls-remote, PR list | High |
| mlro-user | done | AMBER. RT1: no DPMSR or REAR. RT2: the builder renders unsupported types. RT3 (Info): HRCT, HRCA and PNMR are also missing | driver plus JSON evidence | High (I reproduced RT1 and RT2) |
| skeptic | done | AMBER. Confirms RT1 (lowers it from High to Medium), RT2, RT3, SS3b and SS5 (Low/Medium). Links RT1 to 3.1, and SS3b with SS5 to the phishing channel | file:line | High. Still carries N3b |

## 3. Consolidated findings
CONFIRMED (lead) means I reproduced it today on `9219e26` with `repro_lead/checks_2026_11_09.py` or the carried lead scripts (§5).

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-134** (new) SS5: the visitor's display name is written verbatim into the verification mail (`mail.py:138`). Name validation (`auth.py:214-239`) refuses only control characters, length and reserved names | **LOW** (gate for Stripe go-live) | red-team | CONFIRMED Low/Med | **CONFIRMED**: greeting `'Hi Mallory <b>bold</b> https://evil.test/pay,'` | HELD `scripts/proposals/2026-11-09-lead-signup-name-and-report-types.md` §1 (one-line diff plus test). Land with L-129 and L-130 |
| **L-135** (new) RT1: DPMSR and REAR cannot be created. `SUPPORTED_REPORT_TYPES={"STR","SAR","FFR"}` (`reporting/goaml.py:98`), but the landing page sells to brokers and precious-metals dealers (`landing.html:16`) and the KYT rule names AED 55,000 as "the cash-reporting trigger" (`screening/kyt.py:42`) | **MEDIUM** | mlro-user | CONFIRMED, High→Med | **CONFIRMED** (code). Whether these reports are mandatory is PLAUSIBLE: there is no corpus and no XSD | **Needs Nadhir's decision**; options in the proposal, §3 |
| **L-136** (new) RT2: `/reports/build` renders any `report_type` (`api/routers/reports.py:92-131`); the refusal comes only on save | LOW | mlro-user | CONFIRMED Low | **CONFIRMED**: DPMSR, REAR and HRCT return 200 with no warning | HELD same file, §2 (guard on `SUPPORTED_REPORT_TYPES` so FFR draft edits via `report_detail.html:17` still work) |
| L-137 (new) RT3: HRCT, HRCA and PNMR are listed but not creatable | INFO | mlro-user | Info | CONFIRMED (`goaml.py:1-15`) | Folded into L-135; PNMR is CS-14 |
| L-130 SS3b no per-address cooldown | LOW | red-team, code-reviewer | CONFIRMED | CONFIRMED again (`checks_08`) and now through real SMTP (red-team sink: 4 of 4) | HELD 11-08 proposal §2 |
| L-129 SS1b = CR-41 sign-up timing oracle | LOW | carried | CONFIRMED | CONFIRMED again (`SS1b reproduces=True`) | HELD 11-08 proposal §1 |
| L-131 sandbox UAE PASS verifications look real | MEDIUM | carried | Med | CONFIRMED again (`CS24 reproduces=True`) | HELD 11-08 proposal §3 |
| L-132 the scheduler step is continue-on-error and nothing reads the schedule back | LOW (ops) | carried | Low | CONFIRMED again (`CS5d reproduces=True`) | HELD 11-08 §4; Nadhir to run the production check |
| L-124 / L-125 / L-126 MU-CR1 / CR2 / CR3 | MED / LOW-MED / LOW | carried | CONFIRMED | CONFIRMED again (`checks_07` 4/4) | HELD 11-07 proposal |
| L-127 BL1 unknown tier fails open | LOW | carried | Low | CONFIRMED again (`plan='enterprise-free'; 4th operator -> allowed`) | HELD 11-07 §1 |
| L-112 UBO1b, L-113 N8b | LOW | carried | Low | CONFIRMED again (`checks_03` 2/2) | HELD / Nadhir |
| L-133 INFO-8, SS4, K2, SU1, CR-43, L-128 BL2, L-116 SS2b | INFO/LOW | carried | as 11-08 | Unchanged (no code change) | Carry |
| CS-13, CS-14, 3.1 | MEDIUM (legal-dependent) | compliance | High/Med | Code CONFIRMED; legal PLAUSIBLE | Carry; need `corpus/` |
| L-117, CR-39, F2b, CR-34/SMTP, CR-35, I1, L-114, A1 residual, L-111, CR-4, CR-13, CR-18, CR-28, CR-29, PR5, K1, CS-4, FATF CS-1/6/7, E2-E5, F4, TA2/TA3, LN1, SE2, D1, CS-26 | as on 11-07 | various | as stated | No code change | Carry |
| N3b, H1 | — | red-team and skeptic still list them | | REFUTED (11-08 output, no code change since) | Closed |
| FIXED on master since 11-08 | — | | | None. Master is unchanged | — |

**Severity adjudication**
- L-134: red-team says Low, the skeptic says Low/Medium. **LOW**. Open sign-up exists only when `STRIPE_SECRET_KEY` is set. Without it, the invite code gates registration, so the channel is closed until Stripe goes live. Once Stripe is live, it combines with L-130 into a branded phishing route at 5/min/IP, as the skeptic says. That is why it joins L-129 and L-130 as a pre-Stripe blocker rather than being rated MEDIUM now.
- L-135: mlro-user says High, the skeptic says Medium. **MEDIUM**. Nothing is wrongly filed or recorded. The firm files these reports on goAML by hand. The real defect is the gap between what the product claims and what it does for two of its six named sectors. It would rise to HIGH if the legal reading confirms these reports are mandatory and the marketing names them.
- Duplicates: L-137 PNMR = CS-14. SS3b today = L-130 (new evidence, not a new item). L-135 and compliance item 3.1 are one design decision (the skeptic's point 1; I agree).
- Minor discrepancy: mlro-user quotes "Supported types: STR, SAR." while `serialize_goaml_xml` says "FFR, SAR, STR". Both are true. The web save path validates against `CREATABLE_REPORT_TYPES` (`goaml.py:114`, which excludes freeze-only FFR) before the serialiser runs.

## 4. Combined assessment
1. No code change and no regression. All 10 carried lead checks and the 3 new ones reproduce on `9219e26` (§5).
2. The open sign-up form now has three LOW defects (L-129 timing, L-130 cooldown, L-134 payload). Together they are the remaining Stripe go-live blocker, and each fix is a few lines.
3. L-135 is the most important new item. groAML raises the AED 55,000 cash alert for real-estate and precious-metals firms but cannot produce the sector report that follows.
4. The MEDIUMs are product or legal decisions (L-124, L-131, L-135, CS-13/14/3.1), not regressions.
5. Two unknowns remain that no session can check: the live refresh schedule (L-132) and whether DPMSR/REAR are mandatory (no corpus or XSD).

## 5. Corrections I made
- **Owed from 11-08 "Next run":** I re-ran `checks_2026_11_08.py`, `_07` and `_03` (copied from their lead branches, run, then deleted; not re-committed). I retired `_04` and `_05` as instructed. Scratch venv, Python 3.11.18, `requirements.txt` + `requirements-dev.txt`, `PYTHONPATH=.`:
  ```
  === checks_2026_11_08  exit=0
  SS1b reproduces=True / SS3b reproduces=True / CS24 reproduces=True / CS5d reproduces=True / 4/4 reproduce
  === checks_2026_11_07  exit=0
  BL1 ... plan='enterprise-free'; 4th operator -> allowed / BL1 CR1 CR2 CR3 reproduces=True / 4/4 reproduce
  === checks_2026_11_03  exit=0
  UBO1b reproduces=True (3 suffix variants accepted); N8b ... reproduces=True / 2/2 reproduce
  ```
- **Created `repro_lead/checks_2026_11_09.py`.** It uses a temp DB, invite mode, and a fake SMTP class patched into `amlkit.mail`. No network. Output on `9219e26` (`checks_09 exit=0`):
  ```
  SS5   name accepted by check_operator_identity='Mallory <b>bold</b> https://evil.test/pay'; send outcome=sent
  SS5   mail greeting line: 'Hi Mallory <b>bold</b> https://evil.test/pay,'
  SS5   reproduces=True
  RT1   SUPPORTED_REPORT_TYPES=['FFR', 'SAR', 'STR']
  RT1   DPMSR: Report type 'DPMSR' is not supported. Supported types: FFR, SAR, STR
  RT1   REAR: Report type 'REAR' is not supported. Supported types: FFR, SAR, STR
  RT1   reproduces=True
  RT2   GET /reports/build (status, page warns type unsupported): {'STR': (200, False), 'DPMSR': (200, False), 'REAR': (200, False), 'HRCT': (200, False)}
  RT2   reproduces=True
  3/3 reproduce
  ```
- **Created `scripts/proposals/2026-11-09-lead-signup-name-and-report-types.md`** (HELD). It contains the L-134 mail diff plus a test, the L-136 route guard plus a test, and the L-135 options. My first draft of the L-136 guard used `CREATABLE_REPORT_TYPES`. That would have broken the FFR "Edit draft" link (`report_detail.html:17`), so I changed it to `SUPPORTED_REPORT_TYPES` before committing. Not applied, because both fixes touch a route or business logic (rule 3).
- I added no tests to `tests/`, because each would fail on master. I edited no existing file. The secret scan of the new files is clean. The commit SHA is in the final reply.
- Not re-run: the full suite (no code change; the last result on this SHA is 2945 passed, 2 skipped, from three roles on 11-08), the mlro-user driver, and red-team's SMTP-sink probe (I reproduced the same defect in-process instead). OCR tests were not touched.

## 6. Decisions needed from Nadhir
1. **L-135 (new):** for DPMSR and REAR, choose (a) build them (needs the goAML schema and a legal reading) or (b) for now, say in the product and on the public pages that groAML files STR/SAR/CNMR and that DPMSR/REAR go to goAML directly. I recommend (b) plus L-136 now. Decide this together with 3.1 (the configurable AED 55,000 threshold).
2. **Before Stripe go-live:** approve L-129, L-130 and L-134 as one sign-up change.
3. Carried from 11-08: the production scheduler check (`gcloud scheduler jobs describe amlkit-sanctions-refresh` should show `0 */4 * * *`) and the L-132 read-back step; the L-131 UAE PASS environment badge; SU1 (invite door); L-116 (unpaid `/screen`); MU-CR1 design; MU-CR2/CR3; BL1; L-113 backfill; L-112; CS-13/CS-14/3.1 (need `corpus/`); F2b; production SMTP; L-111; CR-29; PR5; K1; CR-4/#417; FATF snapshot; the `github-advanced-security` 402 quota.
4. **New, optional:** commit the FIU goAML XSD (or a note that the FIU does not publish one). Every goAML claim currently rests on code reading.

## 7. Next run: carried over
- From the repo root with `PYTHONPATH=.`, re-run `repro_lead/checks_2026_11_09.py` (this branch), plus `checks_2026_11_08.py`, `_07` and `_03` from their lead branches. Exit 1 means every item in that script is fixed.
- Owed by the lead: none.
- For the roles: red-team and skeptic, drop N3b/H1 (seventh reminder). mlro-user or the skeptic, check the public pages and `/pricing` against L-135 ("goAML reporting": which types). Compliance, whether DPMSR/REAR are mandatory and at what threshold, once `corpus/` exists. Code-reviewer or QA, CR-43 load measurement.
- Landing order: L-129 + L-130 + L-134 (before Stripe), L-136, L-132 + the production check, L-131, L-135 decision, L-124 MU-CR1, L-127 BL1, L-125/L-126, L-113, L-116, L-112, CS-13, L-117, L-111, F2b, INFO-8.
