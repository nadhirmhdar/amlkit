# Lead consolidated report: 2026-11-10

## 1. Headline: AMBER (code unchanged; one new MEDIUM finding)
The mobile API lets an MLRO deactivate the organisation's last active MLRO, a call the web screen refuses. Afterwards nobody in the firm can file reports, run freezes or reactivate anyone (L-138, MEDIUM, CONFIRMED by the lead).

Master is `9219e2623b3a3ba7e73a20e44c703ab80df7e900`, the same SHA as the 2026-11-08 and 2026-11-09 lead reports. `git log 9219e26..origin/master` is empty and the newest PR is still #462. Run date 2026-11-10 UTC. All six role branches were present at the first fetch. The no-change shortcut does not apply because mlro-user raised MA1 and MA2.

## 2. Per role
| Role | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer | done | GREEN, no change. CR-41 and CR-42 carried | ls-remote SHA, PR ref | High |
| qa-regression | done | GREEN, no change. Suite not re-run | ls-remote, empty `git log` | High |
| red-team | done | GREEN. Full suite on `9219e26`: 2945 passed, 2 skipped, 0 failed (14m55s). JSON-LD and CSP probe clean on 12 public pages | evidence files on branch | High. **Still lists N3b and H1 as open (eighth reminder; both refuted 11-08)** |
| compliance-specialist | done | AMBER, no change. CS-13, CS-14, 3.1 stand; legal corpus still BLOCKED | ls-remote, PR list | High |
| mlro-user | done | AMBER. MA1: mobile deactivates the last MLRO. MA2: self-deactivation in one call. Mobile admin role gate, password, role and name rules match the web (clean) | driver + JSON evidence | High (I reproduced MA1) |
| skeptic | done | AMBER. Confirms MA1 by code (Medium-High→Medium), MA2 Low (folded). Flags the recurring "mobile skips what web checks" pattern and the cadence question | file:line | High. Still carries N3b |

## 3. Consolidated findings
CONFIRMED (lead) = reproduced today on `9219e26` (output in §5).

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-138** (new) MA1: `api/mobile.py:1661-1676` deactivates any in-org operator with no last-active-MLRO check; web `api/routers/admin.py:543-554` refuses it | **MEDIUM** | mlro-user | CONFIRMED, Med-High→Med | **CONFIRMED**: mobile `200 {'ok': True}`, active MLROs 1→0; web control refused, stays 1 | HELD `scripts/proposals/2026-11-10-lead-mobile-last-mlro-guard.md` (shared helper used by both routes, 409 on mobile, plus a test) |
| L-139 (new) MA2: self-deactivation in one call, no confirmation | LOW | mlro-user | Low, folded | CONFIRMED by code (same handler) | Covered by the L-138 guard for the last MLRO; otherwise a client/UX matter. No separate fix |
| L-134 SS5 visitor text in verification mail | LOW (pre-Stripe gate) | carried | Low/Med | CONFIRMED again (`checks_09`) | HELD 11-09 proposal §1 |
| L-135 RT1 no DPMSR/REAR | MEDIUM | carried | Med | CONFIRMED again | Needs Nadhir's decision (11-09 §3) |
| L-136 RT2 builder renders unsupported types | LOW | carried | Low | CONFIRMED again | HELD 11-09 §2 |
| L-130 SS3b, L-129 SS1b/CR-41 | LOW | carried | CONFIRMED | CONFIRMED again (`checks_08`) | HELD 11-08 §1-2 |
| L-131 sandbox UAE PASS looks real; L-132 scheduler continue-on-error | MED / LOW | carried | Med / Low | CONFIRMED again (`checks_08`) | HELD 11-08 §3-4 |
| L-124/125/126 MU-CR1/2/3; L-127 BL1 | MED / LOW-MED / LOW / LOW | carried | CONFIRMED | CONFIRMED again (`checks_07` 4/4) | HELD 11-07 |
| L-112 UBO1b, L-113 N8b | LOW | carried | Low | CONFIRMED again (`checks_03` 2/2) | HELD / Nadhir |
| L-137, L-133 INFO-8, SS4, K2, SU1, CR-43, L-128 BL2, L-116 SS2b, CS-13, CS-14, 3.1, L-117, CR-39, F2b, CR-34, CR-35, I1, L-114, A1 residual, L-111, CR-4, CR-13, CR-18, CR-28, CR-29, PR5, K1, CS-4, FATF CS-1/6/7, E2-E5, F4, TA2/TA3, LN1, SE2, D1, CS-26 | as 11-09 | various | as stated | No code change | Carry |
| N3b, H1 | — | red-team, skeptic still list | | REFUTED 11-08, no code change | Closed |
| FIXED on master since 11-09 | — | | | None (master unchanged) | — |

**Severity adjudication**
- L-138: mlro-user Medium-High, skeptic Medium. **MEDIUM.** It needs an authenticated, MFA-verified MLRO token, it is audited (`operator.deactivate`), and the effect is loss of availability, not data exposure. But I checked what the skeptic left open: the only reactivate route (`admin.py:563-591`, web only; mobile has none) itself requires an MLRO session, so after L-138 nothing in-tenant can recover. Recovery needs the vendor's out-of-band `/system/create-operator`. It is the cheapest MEDIUM on the list (about 10 lines) and should land first.
- Pattern: the skeptic's point 1 is right. This is the fourth "mobile skips what web checks" defect. The proposal puts the rule in one shared helper rather than copying it. A one-off audit of every web/mobile write-route pair is worth assigning to code-reviewer (§7).
- Duplicates: MA2 is part of L-138. No contradictions between roles today.

## 4. Combined assessment
1. No code change and no regression. Red-team's full-suite run (2945 passed) is the fourth independent green on `9219e26`. All 14 carried lead checks still reproduce.
2. L-138 is the only new defect. It is real, cheap to fix, and should land ahead of the sign-up batch (L-129/L-130/L-134).
3. The open MEDIUMs are now one fixable route (L-138) plus product/legal decisions (L-124, L-131, L-135, CS-13/14/3.1).
4. Three days on the same SHA. I agree with the skeptic that the loop is running out of cheap defects (§6.3).
5. The unknowns no session can check are unchanged: the live refresh schedule (L-132) and the legal corpus.

## 5. Corrections I made
- **Owed from 11-09 "Next run":** re-ran `checks_2026_11_09.py`, `_08`, `_07`, `_03` (copied from their lead branches, run, deleted; not re-committed). Scratch venv, Python 3.11.18, `requirements.txt` + `requirements-dev.txt`, `PYTHONPATH=.`, OCR not exercised:
  ```
  === checks_2026_11_09  exit=0   SS5 / RT1 / RT2 reproduces=True   3/3 reproduce
  === checks_2026_11_08  exit=0   SS1b / SS3b / CS24 / CS5d reproduces=True   4/4 reproduce
  === checks_2026_11_07  exit=0   BL1 ... plan='enterprise-free'; 4th operator -> allowed; BL1 CR1 CR2 CR3 reproduces=True   4/4 reproduce
  === checks_2026_11_03  exit=0   UBO1b reproduces=True (3 suffix variants accepted); N8b ... reproduces=True   2/2 reproduce
  ```
- **Created `repro_lead/checks_2026_11_10.py`** (temp DB, invite mode, limiter off, real mobile MFA unlock via `conftest.unlock_mobile_mfa`, no network). Output on `9219e26`, `checks_10 exit=0`:
  ```
  MA1w  web deactivate of sole MLRO: status=200 refused=True active_mlros_after=1
  MA1   mobile deactivate of sole MLRO: status=200 body={'ok': True} active_mlros before=1 after=0
  MA1   reproduces=True
  1/1 reproduce
  ```
- **Created `scripts/proposals/2026-11-10-lead-mobile-last-mlro-guard.md`** (HELD): a shared `is_last_active_mlro()` helper, a mobile 409 guard, a web route refactor onto the helper, `org_id` added to the mobile UPDATE, and a test. Not applied because it touches route logic (rule 3). The test is not committed because it fails on master.
- I edited no existing file. The secret scan of the new files is clean. The commit SHA is in the final reply.
- Not re-run: the full suite (red-team ran it today), mlro-user's `mobadm10` driver (reproduced in-process instead), red-team's JSON-LD probe.

## 6. Decisions needed from Nadhir
1. **L-138 (new):** approve the HELD guard. I recommend landing it first, alone.
2. **Before Stripe go-live:** L-129 + L-130 + L-134 as one sign-up change. L-135 DPMSR/REAR: (a) build, or (b) state STR/SAR/CNMR-only now (I recommend (b) + L-136).
3. **Cadence (skeptic point 4):** three no-code-change days in a row. Options: (a) keep daily but give each role a new probe area each run; (b) move to the no-change shortcut on every role except one rotating deep-dive. I recommend (a) for now, with the web/mobile parity audit as the next area.
4. Carried: production scheduler check (`gcloud scheduler jobs describe amlkit-sanctions-refresh` → `0 */4 * * *`) and the L-132 read-back; L-131 UAE PASS badge; SU1; L-116; MU-CR1 design; MU-CR2/CR3; BL1; L-113; L-112; CS-13/14/3.1 (need `corpus/`); F2b; production SMTP; L-111; CR-29; PR5; K1; CR-4/#417; FATF snapshot; the `github-advanced-security` 402 quota; the goAML XSD.
5. **New, ops:** confirm a runbook exists for "tenant has no active MLRO" (vendor `/system/create-operator`). Nobody has checked this (skeptic BLOCKED).

## 7. Next run: carried over
- From the repo root with `PYTHONPATH=.`, re-run `repro_lead/checks_2026_11_10.py` (this branch) plus `checks_2026_11_09.py`, `_08`, `_07`, `_03` from their lead branches. Exit 1 means every item in that script is fixed.
- Owed by the lead: none.
- For the roles: code-reviewer, audit every web/mobile write-route pair (operators create/reset/deactivate/reactivate, threshold, customer close/reactivate, alert disposition, report submit, freeze) for rules present on one side only. mlro-user, check whether a deactivated last MLRO has any self-service recovery. Red-team and skeptic, drop N3b/H1 (eighth reminder). Compliance, MLRO-vacancy obligations once `corpus/` exists.
- Landing order: L-138, then L-129 + L-130 + L-134 (before Stripe), L-136, L-132 + production check, L-131, L-135 decision, L-124, L-127, L-125/L-126, L-113, L-116, L-112, CS-13, L-117, L-111, F2b, INFO-8.
