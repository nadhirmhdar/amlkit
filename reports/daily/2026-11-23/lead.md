# Lead consolidated report: 2026-11-23

## 1. Headline: AMBER (master unchanged; no role has a new defect; the lead's owed DL1 follow-up finds that a delisted UN match leaves the MLRO with no honest way to close its pending freeze)
Master `c42c77ce59179c86b3ed5107b78e65e227326c0d` (`git ls-remote`, today), same as the 11-22 lead report. No PR opened or merged since #467 (roles: highest PR ref 467; compliance notes only draft #411, docs, was updated). Run date 2026-11-23 UTC. All six role branches were present on the first fetch.

Not the "no change" short form: two lead items were owed from 11-22 and both are done below; one of them produced a new, confirmed defect (DL1d).

## 2. Per role
| Role | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer | done (no-change) | GREEN: nothing new to review; CR-50/CR-51 carried | `ls-remote` output | High |
| qa-regression | done (no-change) | GREEN: suite not re-run (no code change); 3010/2 baseline stands; `test_entrypoint` PATH note | `ls-remote`, `git log` empty | High |
| red-team | done (short) | AMBER: PC1b re-run with the real `false_positive` status, 3 stages; corrects its 11-22 `dismissed` artefact | script + evidence on branch | High (matches my `checks_21` PC1b today) |
| compliance-specialist | done (no-change) | AMBER: CS-27 look-back still unconfirmed; law still PLAUSIBLE (corpus BLOCKED) | `ls-remote`, PR list | High |
| mlro-user | done | AMBER: corrects 11-22 EV1 from High to low-medium (unacknowledged operators only); adds EV4 (PDF built from full page chrome) | driver logs, PDFs | High on scope; one claim corrected below |
| skeptic | done (short) | RED carried; EV1 Low/Med, EV4 Low, PC1b Medium | code line refs, no new script | High |

## 3. Consolidated findings
"CONFIRMED (lead)" = reproduced by me today on `c42c77c`; output in `reports/daily/2026-11-23/evidence/lead_checks_2026_11_23_on_c42c77c.txt` (10 carried scripts + 1 new).

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-166 DB1 / CS-28 / CR-48** exact name, same-year different-month DOB → 0.75, no alert | **MEDIUM-HIGH** | 5 roles | CONFIRMED High | **CONFIRMED** (`checks_20` DB1 0.75; `probe_dob_onboard_18`: `1975-12-31 LY NO ALERT`) | HELD 11-20 proposal §1; **Nadhir's decision** |
| **L-163 CS-27 look-back** | HIGH (operational) | compliance, skeptic | PLAUSIBLE | Deploy CONFIRMED 11-22 (CI run #1238, 11-18 14:36 UTC); post-deploy re-screen **unconfirmed** | **Nadhir's decision** |
| **L-174 DL1d (new, lead)**: after delisting, a pending UN freeze cannot be resolved as `delisted` (requires execution) and the "confirmed true positive can't be closed as false positive" guard no longer fires (alert deleted), so the only exit is recording a four-eyes-confirmed match as `false_positive` by one person | **MEDIUM** | lead | — | **CONFIRMED** (`dl1c`: `resolve as 'delisted' refused … obligation not executed`; `false_positive` → `('resolved','false_positive')`) | HELD `scripts/proposals/2026-11-23-lead-delisted-freeze-obligations.md`; **Nadhir's decision** |
| **L-175 DL1c (new, lead, owed item)**: the delisted UN freeze is still counted by the hourly overdue check (→ "execute freeze" email, no delisting notice); a legacy OFAC-linked obligation flips **into** scope when its alert is cascade-deleted (`alert_id NULL` = "manual") | LOW-MEDIUM | lead | — | **CONFIRMED** (`dl1c`: `overdue ids=[1, 2]`; `in_scope … OFAC=True`) | HELD same proposal; legacy-row count in production unknown |
| L-172 DL1b true_positive alert + reviews cascade-deleted on delisting | MEDIUM | lead | — | **CONFIRMED** again (`dl1b`) | HELD 11-22 §2 (root of L-174/L-175) |
| L-171 DL1 (false_positive case) | LOW, merged into L-172 | lead | — | CONFIRMED (`checks_21` DL1: 0 rows) | same |
| L-170 GEN1 gender mismatch silences exact sanctions name | MEDIUM | lead | — | **CONFIRMED** (`checks_21`) | HELD 11-21 §5 |
| L-168 PC1b absorbed same-name PEP never alerts | **MEDIUM** | red-team, lead | CONFIRMED Med | **CONFIRMED** (`checks_21`; red-team v2 3-stage run agrees) | HELD 11-21 §1 |
| L-173 EV1 disclaimer printed over evidence PDF page 1 | **LOW** | mlro-user | CONFIRMED Low/Med | **CONFIRMED, scoped** (`ev1`: True unacked / False acked) | HELD 11-22 §1 |
| EV4 PDF built from full signed-in page chrome | LOW, same fix as EV1 | mlro-user | CONFIRMED Low | CONFIRMED by code (`evidence.html` extends `base.html`; print CSS `app.css:1257-1265` does not hide `dialog`) | Fold into EV1 fix |
| L-169 ED1-ED3 EDD gate | MED / LOW | mlro-user | CONFIRMED | CONFIRMED 11-21 (no code change) | HELD 11-21 §4 |
| CS-30 primary flip re-alerts | LOW | compliance, red-team | noise | **CONFIRMED** (`checks_21`) | HELD 11-21 §2 |
| L-167 CR-49 multi-DOB | MEDIUM | code-reviewer | — | **CONFIRMED** (`checks_20`) | HELD 11-20 §2 |
| PC1 / CR-47 / CS-29 | LOW (root of L-168) | 3 roles | CONFIRMED | **CONFIRMED** (`checks_20`) | HELD 11-20 §3 |
| L-164 rescreen uses `nationality` only | MEDIUM | lead | — | **CONFIRMED** (`probe_dual_nat`: True) | HELD 11-19 |
| L-163a CT1, L-163b CT2 | LOW / INFO | lead | | **CONFIRMED** (`checks_19` 2/3; L158 stays fixed) | HELD 11-19 |
| L-162 caps | MEDIUM | lead | | **CONFIRMED** 4/4 | HELD 11-19 |
| L-159 EX1+EX3, L-161 GV1 | MED / LOW | lead | | **CONFIRMED** (`checks_18` 3/4; DOB1 stays fixed) | HELD 11-18 |
| L-156 QU1, TD2 | MED / LOW | lead | | **CONFIRMED** 4/4 (`checks_17`) | HELD 11-17 |
| CR-50 stale CPU-throttling comments; CR-51 deploy overlap | INFO | code-reviewer | — | CONFIRMED / PLAUSIBLE (11-22) | Doc follow-up / note |
| EV2 goAML XML has no declaration | INFO | mlro-user | PLAUSIBLE | PLAUSIBLE | With goAML XSD item |
| CL1, CL2, TD1, TX1, TX2, N3c; SO1, RL1-RL3; RP1, MA1, SS5, RT1, RT2; SS1b, SS3b, CS24, CS5d; BL1, CR1-CR3; UBO1b, N8b; CS-13, CS-14, 3.1 | as before | | | Not re-run (no app code change since last CONFIRMED) | HELD earlier / carry |
| L-158 DOB1 | — | | | FIXED by #466 (still False today) | Closed |

**Adjudication**
- **mlro-user point 4 is REFUTED for a JS browser.** They say the disclaimer is "open, non-blocking"; that is the server-rendered no-JS state (`base.html:276-290`). With JS, `app.js:637-645` re-opens it with `showDialogModal`, blocks `cancel` and focuses the button, so the page behind is inert. Their driver has no JS. EV1 stays LOW (my 11-22 scoping holds; the skeptic's Low/Med is close and I keep Low because a normal browser user cannot reach the link unacknowledged).
- **DL1d MEDIUM**: it pushes a single operator to record a confirmed UN match as a false positive without four-eyes review, contradicting the guard at `manager.py:2519-2524`. Not higher: it needs an actual UN delisting of a confirmed customer, which is rare, and the audit trail keeps the original confirmation.
- **DL1c LOW-MEDIUM**: the UN half is a wrong/missing notice, not a missed obligation; the OFAC half only affects legacy obligations.
- Duplicates: EV4 = EV1 root cause; red-team PC1b = L-168. Contradictions: only mlro-user point 4 (above). Red-team's and mlro-user's self-corrections are accepted.

## 4. Combined assessment
1. No app change since 11-19; all ten carried lead checks reproduce exactly as on 11-22 (same counts, same exit codes).
2. Role reports today are no-change or self-corrections; evidence quality is good and the corrections tighten EV1 and PC1b.
3. The delisting area is now the clearest gap after DB1: one root cause (hard delete of entities cascading to alerts) produces DL1, DL1b, DL1c and DL1d.
4. EV1 is confined to the single server-side PDF route (`customers.py:495`); there is no other PDF or print export.
5. The constraint is still decisions, not discovery: ≥16 Medium-or-above items HELD, nothing merged app-side for five days.

## 5. Corrections I made
Scratch venv (Python 3.11.18, `requirements.txt` + `requirements-dev.txt`), repo root, `PYTHONPATH=.`, detached at `c42c77c`; WeasyPrint rendered; OCR not exercised. No existing file edited.
- **Owed (11-22): does a delisted entity's pending freeze still count in `/system/check-freeze-obligations`'s query?** Code read (`manager.py:2600-2624`, `sanctions_scope.py:45-63`) plus new `repro_lead/dl1c_delisted_freeze_overdue_2026_11_23.py` calling `manager.check_unexecuted_freeze_obligations` directly (no endpoint, SMTP unset), exit 0:
  ```
  DL1c  before delisting: in_scope UN=True OFAC=False; overdue ids=[1]
  DL1c  after delisting: freeze rows=[(1, None, 'pending_execution'), (2, None, 'pending_execution')]; in_scope UN=True OFAC=True; overdue ids=[1, 2]
  DL1c  delisted UN freeze still overdue/pending=True; legacy OFAC freeze flipped into scope=True
  DL1d  resolve as 'delisted' refused: Cannot resolve freeze obligation 1 with reason 'delisted': obligation not executed. Use 'false_positive' to resolve without execution.
  DL1d  resolve as 'false_positive' on a four-eyes-confirmed (now deleted) true_positive -> ('resolved', 'false_positive')
  DL1d  only exit is mislabelling a confirmed match as false_positive=True
  ```
  Answer: yes, it still counts, and worse (DL1d). Proposal: `scripts/proposals/2026-11-23-lead-delisted-freeze-obligations.md` (HELD).
- **Owed (11-22): do other print views inherit the EV1 overlay?** Code read: the only server-side PDF is `render_pdf` called from `customers.py:529-530` (evidence pack); `grep window.print` finds only the evidence page button (`evidence.html:10`, `app.js:216`) and the blog. The UBO diagram is inline SVG in the case file with no export route; reports export XML only. So no other view inherits it; browser Ctrl+P while unacknowledged would also print the dialog (print CSS hides `button`, not `dialog`), same fix. Closed.
- **Carried checks re-run on `c42c77c`**: `checks_21` 3/3, `checks_20` 3/3, `checks_19` 2/3, `checks_l162_caps_19` 4/4, `probe_dual_nat_19` True, `checks_18` 3/4, `probe_dob_onboard_18` exit 1 by design (`1975-03-12 IN` and `1975-12-31 LY` NO ALERT), `checks_17` 4/4, `dl1b_22` exit 0, `ev1_22` exit 0. Copied in from their lead branches for the run; not recommitted.
- Files created: `repro_lead/dl1c_delisted_freeze_overdue_2026_11_23.py`, `scripts/proposals/2026-11-23-lead-delisted-freeze-obligations.md`, `reports/daily/2026-11-23/evidence/lead_checks_2026_11_23_on_c42c77c.txt`, this report. Commit SHA: in the final reply.

## 6. Decisions needed from Nadhir
1. **CS-27 look-back (urgent):** confirm a refresh + `rescreen_all` ran after 2026-11-18 14:36 UTC, review its alerts (UN first), record the window (from at least 2026-10-04).
2. **Exact-name floor (L-166 + L-170):** Option B recommended, DB2 in the same PR.
3. **Delisting (L-171/L-172/L-174/L-175):** soft-delist (recommended) and whether "delisted before execution" may close a freeze obligation, with or without an authority reference.
4. PEP fold (L-168 + PC1 + CS-30), EDD (L-169), EV1 print fix (bundle EV4).
5. Carried: CR-45, L-156 + L-162 caps, L-159, L-149, L-152, L-154, L-145/L-146, runbook, correct-and-refile, L-135, L-132/L-131, corpus, goAML XSD (+EV2), `github-advanced-security` 402.

## 7. Next run: carried over
- Re-run `checks_2026_11_21.py`, `checks_2026_11_20.py`, `dl1b_…_22`, `ev1_…_22`, `dl1c_…_23`, `checks_19`, `checks_l162_caps_19`, `probe_dual_nat_rescreen_19`, `checks_18`, `checks_17` (copy into `repro_lead/` from their lead branches) if master moves; otherwise only if a role reports a change in their area.
- **Owed by the lead:** none outstanding. Optional: check whether the web freeze-obligations page shows any delisted marker for a `pending_execution` row with `alert_id NULL` (template read only).
- Landing order unchanged: CS-27 follow-ups (L-164 + CT1 + CT2) with L-166/L-170 + DB2, then L-168 + CR-49, then the delisting set (L-171/172/174/175), then L-169, then EV1+EV4 and the rest.
