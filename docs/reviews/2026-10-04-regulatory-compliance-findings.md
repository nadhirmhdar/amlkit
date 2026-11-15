# Regulatory compliance findings — statutory mandatory rules (2026-10-04)

Review of the `amlkit` codebase against six mandatory rules of the UAE AML/CFT
framework: Federal Decree-Law No. 10 of 2025 ("Law 10/2025"), Cabinet
Resolution No. 134 of 2025 ("Res 134/2025"), Cabinet Decision No. 109 of 2023
("Dec 109/2023", UBO) and Cabinet Resolution No. 74 of 2020 ("Res 74/2020",
TFS).

**Citation basis.** The review brief requires every finding to cite an exact
Article from `corpus/` and to match `citation_register.json`. Neither file
exists in this repository (`find` over the tree, excluding `.venv`, returns
nothing). The Article numbers below are therefore the ones stated in the
review brief's own register, marked **[register]**. Where the code or UI
cites a different Article, that is flagged as a mismatch to be resolved
against the corpus once it is checked in. No Article below has been verified
against primary text in this session.

**Not legal advice.** A UAE-qualified adviser signs off before any of this
changes a filing.

Severity: **H** = statutory exposure in production behaviour or user-facing
copy · **M** = control exists but is incomplete or unwired · **L** = citation
or documentation only.

---

## Rule 1 — Standalone proliferation financing (Law 10/2025 Art 21 [register])

| # | Sev | Finding | Evidence |
|---|-----|---------|----------|
| 1.1 | L | PF is classified and surfaced as a standalone offence, but no code path or template cites **Art 21**. The module docstring and the alert text cite only "Federal Decree-Law No. 10 of 2025". | `amlkit/screening/pf.py:1-18`, `:93-99` |
| 1.2 | M | There is no PF-specific reporting route. `SUPPORTED_REPORT_TYPES = {"STR", "SAR", "FFR"}`; a confirmed PF match files the same CNMR/FFR as a terrorism match, differentiated only by the `obligation_type` string in the narrative. The traceability doc already notes "the PF-specific *reporting route* still depends on M4". | `amlkit/reporting/goaml.py:44`, `:180-192`; `research/compliance-traceability.md` §3 |
| 1.3 | L | `research/compliance-traceability.md` contradicts itself: §3 marks PF screening **Resolved**, §7 and the prioritised gap list still mark "Proliferation financing as standalone offence ⚠ ⬚ Highest-priority gap". | `research/compliance-traceability.md` §3, §7, gap list item 1 |

What is in place: `classify_programs()` maps UNSCR 1718 / 1737 / 2231 and OFAC
NPWMD to `proliferation`; `create_freeze_obligation` accepts
`obligation_type="proliferation"` and forces `risk_category="critical"`
(`amlkit/cases/review.py:189-196`); `tests/test_pf.py` covers the classifier.

## Rule 2 — 24-hour TFS asset freeze (Law 10/2025 Art 17; Res 74/2020 Art 15; Res 134/2025 Art 32 [register])

| # | Sev | Finding | Evidence |
|---|-----|---------|----------|
| 2.1 | **H** | **The 24-hour clock starts at the wrong event.** `identified_at` is set when an operator records a `true_positive` disposition, and under four-eyes review that is after a second operator approves. The statutory window runs from designation/listing, not from internal confirmation. A match that sits in `pending_review` for two days is created as a freeze obligation with `hours_pending = 0` and shows as on time. The `alerts` row already carries `created_at` (indexed), so the elapsed time from detection is available and unused. | `amlkit/cases/review.py:132-215`; `amlkit/cases/manager.py:1716-1760`, `:1970-1988`; `amlkit/queries.py:1197`; `amlkit/db.py:1571` |
| 2.2 | **H** | **The overdue check is not wired to anything in the deployed app.** `check_unexecuted_freeze_obligations()` is called only from `scripts/check_freeze_obligations.py`, whose docstring says to run it via Windows Task Scheduler. Nothing in `Dockerfile`, `.github/workflows`, or `amlkit/cases/scheduler.py` runs it, so the MLRO overdue email never fires on Cloud Run. The list page does compute the `OVERDUE` badge at render time, so the signal exists only for an operator who opens that page. | `scripts/check_freeze_obligations.py:1-15`; `amlkit/cases/scheduler.py` (no job); `amlkit/web/templates/freeze_obligations.html:58-70` |
| 2.3 | M | No stored deadline. The freeze row has `identified_at` but no `deadline_at`; the 24 h is re-derived in two places with a strict `> 1.0` day / `> 24` h comparison, so an obligation at exactly 24 h is not yet overdue, and the two derivations can drift. A stored, audited deadline is what an inspector asks for. | `amlkit/db.py:712-735`; `amlkit/cases/manager.py:1983`; `amlkit/web/templates/freeze_obligations.html:58` |
| 2.4 | L | Citation mismatch. UI and code attribute the freeze duty to "Cabinet Resolution 134/2025" with no Article; the public blog attributes it to "Article 21 of Cabinet Decision No. 74 of 2020". The register names **Res 74/2020 Art 15** and **Res 134/2025 Art 32**. One of these is wrong; resolve against the corpus. | `amlkit/web/templates/freeze_obligations.html:14`; `amlkit/cases/manager.py:1966`; `amlkit/web/templates/blog/uae-sanctions-screening-24-hour-rule.html:50`, `:59` |

What is in place: auto-creation of the obligation on confirmed match, MLRO-only
execute / file / resolve gates (`amlkit/api/app.py:1503`, `:1537`, `:1578`),
append-only lifecycle timestamps, `tests/test_freeze.py::test_check_unexecuted_freeze_obligations_finds_overdue`.

## Rule 3 — DNFBP cash reporting threshold AED 55,000 (Res 134/2025 Art 21 [register])

| # | Sev | Finding | Evidence |
|---|-----|---------|----------|
| 3.1 | **H** | **The statutory threshold is operator-configurable upward.** `LARGE_CASH_THRESHOLD_AED = 55_000` is only the default; `/admin/rule-config` lets an org set `large_cash_threshold_aed` to any value up to **AED 1,000,000**. An org that sets it to 100,000 silently stops flagging cash between 55,000 and 100,000. A statutory trigger must be a floor the org can tighten, never loosen: cap the upper bound at 55,000, or split a fixed statutory threshold from a separately configurable internal alert threshold. | `amlkit/screening/kyt.py:30`, `:408-419`; `amlkit/api/app.py:3683-3684` |
| 3.2 | M | No cash transaction report type exists. `cases/reports.py` is documented as "STR/SAR/CTR/DTR" and has a `CTR` branch that reads the org threshold, but `CREATABLE_REPORT_TYPES` is `STR`/`SAR` only, so the branch is unreachable and a cash transaction at or above 55,000 has no dedicated goAML export. | `amlkit/cases/reports.py:3`, `:97-103`, `:113-118`; `amlkit/reporting/goaml.py:44`, `:59-63` |
| 3.3 | L | The 55,000 figure is cited in a comment as "the standard UAE DNFBP occasional-transaction CDD trigger" with no Article. | `amlkit/screening/kyt.py:25`, `:41` |

What is in place: `large_cash` and structuring rules in `screening/kyt.py`,
structuring aggregation across `cash`/`crypto`/`other`, tests in
`tests/test_kyt.py` and `tests/test_kyt_structuring_all_methods.py`.

## Rule 4 — 8-year record retention from end of relationship / occasional transaction (Law 10/2025 Art 25; Res 134/2025 Art 24 [register])

| # | Sev | Finding | Evidence |
|---|-----|---------|----------|
| 4.1 | **H** | **The statutory minimum is stated as 5 years throughout, citing Res 134/2025 Art 25(2).** The register puts it at **8 years** under Law 10/2025 Art 25 and Res 134/2025 Art 24. The 10-year firm policy still exceeds 8, so stored `retention_until` dates are not short, but every user-facing statement of the law is wrong on both the figure and the Article, and two tests pin the wrong copy. | `amlkit/cases/manager.py:13-16`, `:88-95` (`STATUTORY_MIN_RETENTION_YEARS = 5`); `amlkit/web/templates/customer.html:55-56`; `amlkit/web/templates/privacy.html:94-95`; blog template lines 29, 157, 203; `research/compliance-traceability.md` §6; `tests/test_retention_policy.py:46`, `:100`; `tests/test_issue_165_retention_copy.py:4` |
| 4.2 | M | **No retention anchor for occasional transactions.** Retention is computed only on the `customers` row, from the exit date (`close_relationship`, correct) or from the onboarding date (placeholder on active rows). Ad-hoc screenings with no `customer_id` and transactions for non-customers have no `retention_until` at all, so nothing records when the 8 years from an occasional transaction ends. | `amlkit/cases/manager.py:273`, `:505-535`; no `retention` reference in `amlkit/screening/kyt.py` or `amlkit/cases/reports.py` |
| 4.3 | L | Active customers display "Records retained until {onboarding + 10y}". That date is a placeholder that is overwritten at closure, so showing it on an open relationship misstates when retention actually starts. | `amlkit/web/templates/customer.html:54-57`; `amlkit/cases/manager.py:273` |

What is in place: `retention_from(exit_date)` on closure, reset on
reactivation, purge gated on `status='closed'` and a frozen-customer guard
(`tests/test_purge_freeze_guard.py`, `tests/test_p0_purge_gate.py`).

## Rule 5 — Cascading UBO hierarchy and cycle prevention (Dec 109/2023 [register])

| # | Sev | Finding | Evidence |
|---|-----|---------|----------|
| 5.1 | **H** | **Tier 2 ("control through other means") is missing.** `is_ubo` is set only for `ownership_pct >= 25` or `control_type == "senior_official"`. The schema allows `control_type = 'other'`, but a person recorded with it and under 25 % is `is_ubo = 0`. The customer form offers only Ownership / Senior managing official / Nominee, so an operator cannot record control-based beneficial ownership at all. | `amlkit/cases/manager.py:86`, `:395-403`; `amlkit/db.py:304`; `amlkit/web/templates/customer.html:112-116`; `customer_new.html:145` |
| 5.2 | M | **Cascade order is not enforced.** `senior_official` can be added while a ≥ 25 % owner already exists, and nothing records that tiers 1 and 2 were exhausted first. The fallback is only lawful when no natural person is found under the earlier tiers; the code cannot show that. | `amlkit/cases/manager.py:376-450` (no check against existing `is_ubo` rows); `tests/test_cases.py:175-182` only tests the positive case |
| 5.3 | M | **Indirect ownership is not resolved through the chain.** `parent_ubo_id` records layered holdings, but `ownership_pct` on an indirect link is never multiplied through its parent, and `ownership_state()` sums direct percentages only. A 60 % holder of a company that owns 30 % of the customer (18 % effective) is flagged `is_ubo = 1` on its raw 60 %. `resolve_ubo_chain()` was removed in #164 as dead code rather than wired in. | `amlkit/cases/manager.py:421-431`, `:455-500`, comment at `:502-505` |
| 5.4 | L | Cycle prevention is structural, not explicit. A parent must already exist for the same customer and `parent_ubo_id` is never updated after insert (no `UPDATE ubo_links` touches it), so a cycle cannot be formed today. The self-parent guard at `manager.py:446` is unreachable (`lastrowid` cannot equal a pre-existing parent id). If a parent-edit route is ever added, an ancestor walk is needed; a test asserting that no such route exists would protect the invariant. | `amlkit/cases/manager.py:411-419`, `:446-448`; `grep "UPDATE ubo_links"` returns nothing |

What is in place: `UBO_THRESHOLD_PCT = 25.0`, direct-ownership 100 % cap,
nominee exclusion, `ubo_undisclosed` scoring for legal persons with no UBO,
every UBO screened at onboarding.

## Rule 6 — Senior management and MLRO personal liability (Law 10/2025 Art 20 [register])

| # | Sev | Finding | Evidence |
|---|-----|---------|----------|
| 6.1 | L | Every liability statement in code and UI attributes it to "Cabinet Resolution 134/2025"; none cites **Law 10/2025 Art 20**. | `amlkit/cases/review.py:146`; `amlkit/cases/manager.py:1280`, `:1713`; `amlkit/web/templates/dashboard.html:154`; `freeze_obligations.html:15`; `scripts/check_freeze_obligations.py:3` |
| 6.2 | M | Liability-bearing decisions are MLRO-gated (execute / file / resolve freeze; report finalisation), but the control that would tell the MLRO they are exposed (finding 2.2, overdue email) does not run in production. Personal liability without a working deadline alert is the combination an inspector will test first. | `amlkit/api/app.py:1503`, `:1537`, `:1578`; see 2.2 |

---

## Cross-cutting

- **No citation register in the repo.** Only two Article citations exist in
  the whole package (`manager.py:16`, `:89`, both "Art. 25(2)", both disputed
  by finding 4.1). Recommend checking in `corpus/` (or a pointer to it) and a
  `citation_register.json` mapping each obligation → instrument → Article →
  implementing symbol → test, and a test that fails when a template or
  docstring cites an Article absent from the register.
- **Traceability doc is stale** (findings 1.3, 4.1): §6 and §7 of
  `research/compliance-traceability.md` need re-baselining against the
  register.

## Suggested order of work

1. **3.1** cap `large_cash_threshold_aed` at 55,000 (one bound change plus a test) — smallest change, largest exposure.
2. **2.1 + 2.3** anchor the freeze clock to `alerts.created_at` (or an explicit designation date) and store `deadline_at`.
3. **2.2** run the overdue check from the existing refresh scheduler path or a Cloud Run job, not a Windows task.
4. **4.1** change `STATUTORY_MIN_RETENTION_YEARS` to 8, fix the Article citation, and update the four templates and two tests that pin the copy.
5. **5.1 + 5.2** add a `control` tier to `control_type`, set `is_ubo` for it, and refuse `senior_official` while a tier-1/2 UBO exists (or record the exhaustion explicitly).
6. **5.3** reinstate chain resolution for indirect percentages.
7. **4.2** retention anchor for occasional transactions / ad-hoc screenings.
8. Citation fixes (1.1, 2.4, 3.3, 6.1) once the corpus is available.
