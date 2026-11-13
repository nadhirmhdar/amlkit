# Lead consolidated report: 2026-11-13

## 1. Headline: AMBER (code unchanged; one new MEDIUM in operator administration)
Master is `9219e2623b3a3ba7e73a20e44c703ab80df7e900`, the same SHA as the 11-08 to 11-12 lead reports (`git log 9219e26..origin/master` empty, newest PR still #462). Run date 2026-11-13 UTC. All six role branches were present at the first fetch. New today: mlro-user's operator-administration walk (SO1, RL1-RL3), all CONFIRMED by the lead in-process, plus one extension (RL2d: deactivation leaves "remember this device" tokens live). All 16 carried defects still reproduce.

## 2. Per role
| Role | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer | done | GREEN, no change. CR-41/CR-42 carried. Parity audit / input sweep (asked 11-11, 11-12) still not done | ls-remote SHA, PR ref | High |
| qa-regression | done | GREEN, no change. Suite not re-run (2945 passed, 2 skipped on `9219e26`) | ls-remote, empty `git log` | High |
| red-team | done | AMBER. Web/mobile parity of admin create/reset and of four-eyes: clean. No new finding | probe script + evidence file (read) | High. Still lists N3b/H1 (refuted 11-08) |
| compliance-specialist | done | AMBER, no change. CS-13, CS-14 stand; legal corpus BLOCKED | ls-remote, PR list | High |
| mlro-user | done | AMBER. SO1 (Med), RL1, RL2 (Low-Med), RL3 (Low) | driver + JSON log (read) | High (all reproduced by lead) |
| skeptic | done | AMBER. SO1/RL1-RL3 CONFIRMED by code; frames them as one design gap; raises untested MFA/trusted-device question | file:line | High. Still carries N3b |

## 3. Consolidated findings
CONFIRMED (lead) = reproduced today on `9219e26` (output in §5).

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-145 SO1** (new): any one MLRO can switch single-operator mode on with 3 active operators; four-eyes off firm-wide. `api/routers/admin.py:341-367` has no operator count | **MED** | mlro-user, skeptic | CONFIRMED, Med | **CONFIRMED** (`checks_13` SO1: active=3, before=False, after=True) | HELD `scripts/proposals/2026-11-13-lead-operator-admin-model.md`; rule choice needs Nadhir |
| **L-146 RL1** (new): no role-change route anywhere, yet guard text at `admin.py:552` says "Promote another operator" | LOW-MED | mlro-user, skeptic | CONFIRMED, Med (with MA1) | **CONFIRMED** (no route, no `SET role` in `amlkit/`) | Same HELD proposal; needs Nadhir (build promote vs change text) |
| **L-147 RL2 + RL2d** (new): reactivation restores the old password (`admin.py:563-591`); **lead extension:** deactivation does not revoke trusted-device tokens (`auth.py:412` vs `:685`), so a reactivated MLRO's old device still skips MFA | LOW-MED | mlro-user, skeptic (RL2d raised untested by skeptic) | CONFIRMED Low/Med | **CONFIRMED** (`checks_13` RL2, RL2d) | Same HELD proposal |
| **L-148 RL3** (new): reactivating an active operator says success, writes a duplicate audit row | LOW | mlro-user, skeptic | CONFIRMED, Low | **CONFIRMED** (audit rows 1 -> 2) | Same HELD proposal |
| Four-eyes + admin create/reset web/mobile parity | — | red-team | AGREE, clean | Accepted (evidence file read: same-officer confirm refused on both surfaces) | Clean |
| L-138 MA1/LM1 mobile last-MLRO deactivate | MED | carried | CONFIRMED | CONFIRMED (`checks_10`) | HELD 11-10; land with L-145..148 |
| L-140 RP1, L-141 gender rewrite, L-143 amount cap | MED / MED / LOW | carried | CONFIRMED | CONFIRMED (`checks_11` 2/2) | HELD 11-11 + 11-12 addendum |
| L-134 SS5; L-135 RT1; L-136 RT2 | LOW / MED / LOW | carried | | CONFIRMED (`checks_09` 3/3) | HELD 11-09 / Nadhir |
| L-129/130 SS1b/SS3b; L-131 CS24; L-132 CS5d | LOW / LOW / MED / LOW | carried | | CONFIRMED (`checks_08` 4/4) | HELD 11-08 |
| L-124/125/126 CR1-3; L-127 BL1 | MED / LOW-MED / LOW / LOW | carried | | CONFIRMED (`checks_07` 4/4) | HELD 11-07 |
| L-112 UBO1b, L-113 N8b | LOW | carried | | CONFIRMED (`checks_03` 2/2) | HELD / Nadhir |
| L-144 (no mobile reactivate), L-142 RP2, L-139 MA2, L-137, L-133 INFO-8, SS4, K2, SU1, CR-43, L-128 BL2, L-116 SS2b, CS-13, CS-14, 3.1, L-117, CR-39, F2b, CR-34, CR-35, I1, L-114, A1 residual, L-111, CR-4, CR-13, CR-18, CR-28, CR-29, PR5, K1, CS-4, FATF CS-1/6/7, E2-E5, F4, TA2/TA3, LN1, SE2, D1, CS-26, RP3 | as 11-12 | various | as stated | No code change | Carry |
| N3b, H1 | — | red-team, skeptic still list | | REFUTED 11-08 | Closed |
| FIXED on master since 11-12 | — | | | None (master unchanged) | — |

**Severity adjudication**
- **SO1: MEDIUM**, agreeing with both roles. It is not new code (skeptic cited the route on 10-04 as the reason four-eyes bypasses were rated Medium not High), but today proves it is unconstrained with three operators present. Mitigations are real: MLRO-only, audited (`org.single_operator_set`), each dismissal flagged `single_operator`. Not HIGH because it needs an MFA-verified MLRO and leaves a trail. Whether four-eyes is a legal requirement or a product choice is unknowable without the corpus; if it is legal, this rises.
- **RL1:** skeptic says Medium (because it blocks reaching two MLROs, which MA1's and SO1's fixes assume); mlro-user says Low-Med. I keep **LOW-MED**: a workaround exists (create a new MLRO account), and the wrong guard text is the concrete defect. It moves with L-138/L-145 regardless.
- **RL2:** **LOW-MED**. RL2d makes it slightly worse (MFA skip survives too) but a password reset clears both (`auth.py:685` revokes trusted devices), so the MLRO has a remedy today.
- Duplicates: none new; SO1/RL1-RL3 were raised once and confirmed by the skeptic. No contradictions. Skeptic's "one design problem" framing adopted: L-138 + L-145..L-148 share one HELD proposal target.

## 4. Combined assessment
1. Sixth day on the same SHA; no regression; all 16 carried defects plus 5 new checks reproduce.
2. The new cluster (L-145..L-148, with L-138) is the operator-administration surface lacking an org-level role model; one spec fixes all five.
3. SO1 also qualifies every earlier four-eyes severity: the control is advisory while one MLRO can switch it off.
4. Open MEDIUMs: L-138, L-145, L-140, L-141, L-135, L-124, L-131. All have HELD proposals.
5. Still unverifiable from here: live refresh schedule, legal corpus, goAML XSD, production `AMLKIT_SINGLE_OPERATOR_MODE`.

## 5. Corrections I made
- **Owed from 11-12 "Next run":** re-ran `checks_2026_11_11`, `_10`, `_09`, `_08`, `_07`, `_03` from their lead branches (copied into `repro_lead/`, run, deleted; not re-committed). Scratch venv, Python 3.11.18, `requirements.txt` + `requirements-dev.txt`, `PYTHONPATH=.`, OCR not exercised.
  ```
  === checks_2026_11_11 exit=0  RP1 reproduces=True (6/6); RP1g reproduces=True (rewritten to F: ['M','other','unknown','attack helicopter'])  2/2 reproduce
  === checks_2026_11_10 exit=0  MA1 reproduces=True  1/1 reproduce
  === checks_2026_11_09 exit=0  SS5 / RT1 / RT2 reproduces=True  3/3 reproduce
  === checks_2026_11_08 exit=0  SS1b / SS3b / CS24 / CS5d reproduces=True  4/4 reproduce
  === checks_2026_11_07 exit=0  BL1 / CR1 / CR2 / CR3 reproduces=True  4/4 reproduce
  === checks_2026_11_03 exit=0  UBO1b reproduces=True (3 suffix variants); N8b reproduces=True  2/2 reproduce
  ```
- **Created `repro_lead/checks_2026_11_13.py`** (exit 0 when any reproduces; exit 1 when all fixed):
  ```
  SO1  active_operators=3 single_operator before=False after=True msg_on_page=True  reproduces=True
  RL1  role-change routes=[] 'SET role' in source=False 'Promote another' message present=True  reproduces=True
  RL2  officer signed in while deactivated=False; after reactivate with OLD password=True  reproduces=True
  RL2d trusted-device token minted before deactivation still valid after reactivation=True  reproduces=True
  RL3  reactivate already-active officer: success msg=True audit rows 1 -> 2  reproduces=True
  5/5 reproduce
  exit=0
  ```
- **Created `scripts/proposals/2026-11-13-lead-operator-admin-model.md`** (HELD: route logic, rule 3). Covers SO1, RL1, RL2/RL2d, RL3 with a diff sketch and target rules; to land with L-138.
- Code read on `9219e26`: `api/routers/admin.py:341-367, 523-591`, `cases/review.py:96-121`, `auth.py:412-424, 428-470, 675-685`. No existing file edited. Secret scan of the new files clean. Commit SHA in the final reply.
- Not re-run: full suite (no code change); mlro-user's `roles13`/`single13` driver (shared paths reproduced in-process); red-team's `probe_four_eyes_parity.py` (evidence file read).

## 6. Decisions needed from Nadhir
1. **Single-operator mode rule (L-145):** allow "on" only with exactly one active operator, or require a second MLRO to confirm? And is four-eyes a regulatory requirement for your clients or a product feature (sets SO1's severity)?
2. **Role change (L-146):** build an MLRO-only promote/demote control, or just change the guard text to "create another MLRO account first"?
3. **Fix wave:** land L-138 + L-145..L-148 together as the operator-admin wave, then L-141 + L-140 + L-143. Master has been frozen since 11-07.
4. Carried: no-MLRO recovery runbook (`ADMIN_API_SECRET` holder); whether roles read a shared findings register; correct-and-refile for finalised reports; pre-Stripe batch L-129 + L-130 + L-134; L-135 scope; production scheduler check / L-132; L-131; corpus, goAML XSD, `github-advanced-security` 402 quota.

## 7. Next run: carried over
- From the repo root with `PYTHONPATH=.`, re-run `checks_2026_11_13.py`, `_11`, `_10`, `_09`, `_08`, `_07`, `_03` from their lead branches (copy into `repro_lead/` first). Exit 1 means every item in that script is fixed.
- Owed by the lead: none.
- For the roles (suggestions only): code-reviewer, the web/mobile parity audit and input sweep (asked three times). Red-team and skeptic, drop N3b/H1. Compliance, four-eyes and MLRO-vacancy obligations once `corpus/` exists.
- Landing order: L-138 + L-145..L-148, then L-141 + L-140 + L-143, then L-129 + L-130 + L-134 (before Stripe), L-136, L-132 + production check, L-131, L-135 decision, L-124, L-127, L-125/L-126, L-113, L-116, L-112, CS-13, L-117, L-111, F2b, INFO-8.
