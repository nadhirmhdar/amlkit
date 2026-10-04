# Skeptic / falsification review, 2026-10-04 (cited code identical at `fc80e9f` and `05e612d`)

## Headline: AMBER
Most top findings survive, but two are inflated (the four-eyes "RED" and FATF "High"), one is not a defect (wires not aggregating), and the code-reviewer report never arrived.

## Instructions I ran under (stated at dreamon's request)
**(a) Role before dreamon's first message** (Nadhir's standing profile, verbatim in substance): "Independent Audit Skeptic & Devil's Advocate (Agent 7). Devil's advocate and falsification reviewer. Sole mission: stress-test and attempt to DISPROVE proposed findings. You do not review work packages; you review proposed FINDINGS before adjudication. For every finding ask: (1) bug or intentional design? (2) does the statute say what is claimed? (3) is it based on stale comments rather than runtime? (4) is severity inflated, can it be downgraded or closed? (5) does the repro test real business logic or a strawman? A finding that survives is genuine; a flaw in the reasoning means recommend REJECTION."
Session harness rules: develop on `claude/gallant-gates-036krv`, never push to another branch without explicit permission, open a draft PR after pushing, no model identifiers in pushed artifacts.

**(b) Powers:** read the repo and other branches, run code locally in a scratch venv, edit/commit/push on my designated branch, GitHub tools scoped to `nadhirmhdar/amlkit`. Nothing about production, `/system/*` or secrets; none used.

**(c) What dreamon's messages changed:** adopted its report format and the 30-minute wait for the other roles' branches. Did NOT push to `routine/2026-10-04-skeptic` when only dreamon asked; Nadhir then told me directly to push there, so it is pushed there now. Kept its additive-only rule (new files only, no existing code edited). Master moved from `fc80e9f` to `05e612d` (login-page files only); I verified on `05e612d`, and every file cited below is unchanged between the two.

**Assumptions:** "refute" = re-read cited lines and re-run repros on a venv without `passporteye`/`pdfminer` (as QA did); the code-reviewer branch was polled from 19:20 to 19:48 UTC and not found, so it is MISSING.

## Inputs
| Role | Branch | State |
|---|---|---|
| qa-regression | `routine/2026-10-04-qa-regression` | read |
| red-team | `routine/2026-10-04-red-team` | read |
| compliance-specialist | `routine/2026-10-04-compliance-specialist` | read |
| mlro-user | `routine/2026-10-04-mlro-user` | read |
| code-reviewer | `routine/2026-10-04-code-reviewer` | **MISSING** (absent at 19:48:30 UTC) |

## Verdicts
Scripts: `repro_skeptic/*.py` (exit 0 only when the defect reproduces). Red-team probes were re-run from their branch against master code.

### Red-team
| Id | Verdict | Severity (theirs -> mine) | Evidence |
|---|---|---|---|
| F1 Unicode screening miss | **CONFIRMED** | High -> High | `repro_skeptic/presentation_forms.py`: `has_arabic_script(pf)=False` (`names/arabic.py:59` range stops at U+06FF/U+077F, omits U+FB50-FDFF, FE70-FEFF), so `canonical_key(pf)=''` while `canonical_key(NFKC(pf))='bilal'`. Empty key = silent clear. Their `probe_e2e` re-run: ZWSP/ZWJ/BOM inside a Latin name -> MISS (the token splits: `'ali bilal f w'`). Realistic trigger: copy-paste from PDFs. |
| F2 Extra token / attribute mismatch | **CONFIRMED**, partly by design | High -> High (extra token), Medium (attribute mismatch) | `scorer.py:35,43,47`: with `FAMILY_NAME_WEIGHT=1.3` one extra token on a 3-token name scores 3.3/4.3 = 0.77 (leading/middle) or 3/4.3 = 0.70 (trailing), below 0.85. Country/gender mismatch is -0.20, so an exact 1.0 becomes 0.80 (`scorer.py:28-31`). The precision term is deliberately calibrated (comment at `scorer.py:111-122`); the calibration evidence cited is `tests/test_matching.py`, which I did not audit for multi-token cases, and the mismatch values come from customer-supplied attributes. |
| F3 `rescreen_all` skips non-UBO links | **CONFIRMED, narrower** | High -> Medium | `engine.py:420-424` filters `is_ubo=1 AND is_nominee=0`; `probe_ubo` re-run: 24.99%/nominee/director -> 0 alerts, 25% -> 1. But every link is screened once at add time (`app.py:2284`), so the gap is only listings that appear after onboarding. The web route also never sets `is_nominee`. |
| F4 Rename defeats four-eyes | **CONFIRMED mechanism, severity inflated** | Medium (red-team) / RED (mlro-user) -> Medium | `repro_skeptic/four_eyes_rename.py` (function level): self-confirm refused, rename, confirm -> `Independent review completed`, alert `false_positive`. `alert_reviews.operator` is a name string (`db.py:406`). **Counter:** an MLRO can already switch four-eyes off for the whole org at `POST /admin/single-operator` (`app.py:3360-3386`), audited. So the rename gives no new privilege. The real harm is evidence integrity: the record asserts independence that did not occur. Fix is cheap (store operator id). RED is not supportable. |
| F5 `/admin/org-profile` no CSRF | **CONFIRMED**, mitigated | Medium -> Low | `repro_skeptic/csrf_scan.py`: 61 state-changing routes, 5 without a CSRF check. Session cookie is `SameSite=Strict` (`app.py:632`), MLRO-only, fields are goAML profile text. Still a deviation from CLAUDE.md ("validated on every POST"). |
| F6 out-of-order structuring | **CONFIRMED** | Medium -> Low | `kyt.py:207-216` looks only backward from the current `occurred_at`; reproduced (`probe_kyt` re-run). Needs back-dated entry. |
| F7 `amount_aed=1` | **CONFIRMED, mostly by design** | Medium -> Low | `manager.py:718-722` documents that `amount_aed` is operator-entered for non-AED. The only real gap: no cross-check when `currency=='AED'`. The "attacker" is the trusted operator. |
| F8 `id(conn)` cache key | **CONFIRMED in repro, production frequency unproven** | Medium -> Low | `probe_cache` re-run: stale 55,000 on 200/200 connections, id reused. Bounded by `_CACHE_TTL_SECONDS=300` (`kyt.py:91`) and needs the threshold changed by another process. |
| F9 wires never aggregate | **REFUTED as a defect** | Medium -> not a bug | `kyt.py:38-47` states the design: AED 55,000 is a cash-reporting trigger; wires/cheques are excluded because summing them alerted on routine payments; large single transfers go to `large_value`. `probe_kyt` shows 5 wires/day for 3 days raised `velocity`. The 7-day window and duplicate-record points are scope limits, not bugs. |
| F10 odd operator names | CONFIRMED | Low | Same family as mlro-user F4 (names unique by exact match). No harm shown beyond audit readability. |
| F11 weak reset password 500 | **CONFIRMED by code**, HTTP 500 not run by me | Low | `app.py:3414-3417` checks length only, then `auth.set_password`, which raises `PasswordComplexityError` (`auth.py:119-129`) uncaught there (it is caught at `app.py:811,4441`, not here). |
| F12 NaN/inf amounts | **CONFIRMED** | Low | `probe_kyt` re-run: `InvalidOperation` / `OverflowError`; the route catches only `PermissionError, ValueError` (`app.py:2338`). |
| F13 diagram 2.0 s | not re-run | Low | UNVERIFIED by me. |
| F14 NaN threshold accepted | **CONFIRMED** | Low | `probe_cache` re-run: "NaN threshold ACCEPTED". Note `save_rule_config` bounds use `<= 0` / `> 1_000_000` comparisons, which are False for NaN (`kyt.py:408-419`). |
| Sub-agent static items (any-MLRO refresh, NULL-org audit rows, email enumeration, upload overwrite) | **UNEVIDENCED** | -- | I did not verify them; treat as PLAUSIBLE leads. |
| Cross-tenant clean (PR #412 sweeps) | not re-run | -- | Sweeps live on PR branches, not master. I make no claim either way. |
| UBO cycles unreachable | **CONFIRMED (agree)** | -- | `probe_ubo` re-run: parent must pre-exist (`parent 9999 -> not found`), no `UPDATE` of `parent_ubo_id`. Matches compliance 5.4. |

### MLRO-user
| Id | Verdict | Note |
|---|---|---|
| F1 RED | CONFIRMED mechanism; **severity REFUTED -> Medium** | See red-team F4. |
| F2 finalise-then-unexportable report | not independently reproduced | Plausible from their log; not re-run. |
| F3 saved goAML entity reference never shown | **CONFIRMED by code** | `/admin` SELECT omits the column (`app.py:3182-3186`); builder prefill is hard-coded (`str_builder.html:33`). **Worse than reported:** the form posts blank, and `admin_save_org_profile` writes `goaml_entity_reference = NULL` on every save (`app.py:3253-3267`). The saved value is also not read by any reporting code I found (grep). |
| F4 case-variant duplicate names | CONFIRMED (docstring: unique `(org_id, name)`, exact match; also red-team F10) | Low. |
| F5 XML not goAML 5.0 | PLAUSIBLE, cannot refute | BLOCKED on the FIU XSD, as they say. |
| F6-F9 | not independently reproduced | Wording/noise items. |

### Compliance specialist
| Id | Verdict | Note |
|---|---|---|
| CS-1 FATF fallback shown as fresh | **CONFIRMED**; severity H -> Medium | `FATFAdapter().parse(b"")` yields 26 fallback entities (my run); `loader.py:222-228` already admits it and keeps FATF out of the screening freshness gate. Affects the jurisdiction risk factor, not sanctions screening. Not hidden by the authors, but still not visible to the MLRO. |
| CS-2 freeze wording on EU-only hits | PLAUSIBLE (agree) | Legal scope unverifiable here. |
| CS-3 dismissed FPs re-alert | **CONFIRMED**; M -> Low/Medium | `engine.py:343-348` dedupes on `status='open'` only. See "missed" item 2. The proposed suppression table is itself a risk (hides a later real match) unless it expires on entity change. |
| CS-4 Interpol 403 | agree REFUTED as statutory gap | |
| CS-5 scheduler unverifiable | PLAUSIBLE (agree) | Needs prod/GCP access I do not have. |
| PR #410 table | only spot-checked | 3.1 CONFIRMED by code (`kyt.py:417-419` allows up to AED 1,000,000); 5.4 CONFIRMED refuted (above). Article numbers: no corpus in repo, so any citation is UNVERIFIED. |

### QA regression
Methodology is sound (venv, exit-0-on-defect, scratch DBs). QA-1/QA-2 correctly not findings. Limits to carry: OCR tests (19) unverified, run was at `fc80e9f`, and I did not repeat the 12-minute suite.

## What the team missed
1. `/logout` has no CSRF check (`repro_skeptic/csrf_scan.py`); red-team's "47 other routes rejected" did not count it. Low.
2. Alerts in `pending_review` are not `open`, so `rescreen_all` raises a duplicate alert for a sanctions match whose dismissal is awaiting second review (`engine.py:343-348`). Reasoned from code, not run. Medium/Low.
3. The single-operator switch (`app.py:3360`) changes the severity of two reports (red-team F4, mlro-user F1) and nobody mentioned it.
4. Org-profile save wipes `goaml_entity_reference` (see MLRO F3).
5. Roles rate the same defect differently (RED vs Medium); the lead should consolidate on my adjudication above.
6. Code-reviewer: no report, so nothing was cross-checked for the diff-level view.

## BLOCKED / not checked
- code-reviewer report: MISSING.
- Not re-run: PR #412 tenant sweeps, QA's full suite, diagram probe, MLRO driver, the sub-agent's static items, goAML XML schema (needs FIU XSD), any production or GCP state.
- No legal text was available; statute-based claims stay PLAUSIBLE at best.

## Files and commit
`reports/daily/2026-10-04/skeptic.md`, `repro_skeptic/four_eyes_rename.py`, `repro_skeptic/presentation_forms.py`, `repro_skeptic/csrf_scan.py`. No existing file edited. Commit SHA is given in the final reply.
