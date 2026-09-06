# Compliance Traceability — Law 10/2025 & Cabinet Resolution 134/2025

Maps each obligation to the feature that implements it and the test that proves
it. Written so a supervisor's question ("show me how you meet Article X") has a
file and a test name as its answer, not a paragraph of assurance.

**Status legend:** ✅ implemented · ◐ partial · ⬚ not built · ⚠ gap requiring action

> Built from published legal sources. **Not legal advice.** A UAE-qualified
> adviser must sign off the risk model and STR workflow before this touches
> real client files.

---

## 1. Customer Due Diligence

| Obligation | Status | Implementation | Test |
|---|---|---|---|
| Identify and verify the customer | ◐ | `cases/manager.py::onboard` captures identity, ID type/number, nationality, DOB | `test_cases.py::TestOnboarding` |
| Verify identity from **independent source documents** | ⚠ ⬚ | Documents can be stored (`documents` table) but nothing verifies them | — |
| Understand purpose and intended nature of the relationship | ⬚ | No field captured | — |
| Ongoing monitoring of the relationship | ◐ | `rescreen_all` covers name screening; no transaction monitoring | `test_matching.py` |
| CDD before establishing the relationship | ✅ | `onboard` screens before the record is usable | `test_listed_customer_is_blocked` |

**Gap ⚠:** there is no identity-document verification. This is the single
largest functional gap against the law. No credible free ID/biometric provider
exists; the honest options are self-hosted OCR/MRZ extraction or a paid
per-verification vendor. Until then the tool supports record-keeping of
documents, not verification of them, and should be described that way.

## 2. Beneficial Ownership

| Obligation | Status | Implementation | Test |
|---|---|---|---|
| Identify BOs at the **25% threshold** | ✅ | `UBO_THRESHOLD_PCT = 25.0` in `cases/manager.py` | `test_threshold_is_twenty_five` |
| Fallback to **senior managing official** where no BO meets the test | ✅ | `control_type="senior_official"` sets `is_ubo` regardless of percentage | `test_senior_official_fallback_counts` |
| Screen beneficial owners, not only the contracting party | ✅ | `onboard` screens every UBO; a listed UBO blocks a clean company | `test_listed_ubo_blocks_clean_company` |
| Maintain and update BO register | ◐ | `ubo_links` stores it; no update-workflow enforcement | `TestOwnershipState` |
| Update BO data within **15 working days** of a change | ⚠ ⬚ | No deadline tracking or overdue alerting | — |

**Design note:** a legal person with no identified UBO is scored
`ubo_undisclosed` (45 risk points), not treated as transparent. Defaulting the
other way would understate risk precisely where the regulation is most
concerned.

## 3. Targeted Financial Sanctions

| Obligation | Status | Implementation | Test |
|---|---|---|---|
| Screen against **UNSC Consolidated List** | ◐ | Adapter exists (`un_sanctions()`); not yet loaded by default | — |
| Screen against **UAE Local Terrorist List** | ✅ | `uae_local_terrorists()` — 335 screenable entities, daily refresh | real-data verification |
| Screen against **counter-proliferation lists** | ✅ | `screening/pf.py` classifies designations by sanctions programme. Of 1,340 loaded entities: **273 proliferation, 809 terrorism, 258 neither** | `test_pf.py` |
| Implement list updates **within 24 hours** | ◐ | `staleness_report` detects breach; refresh is manual, no scheduler yet | — |
| Screen at onboarding | ✅ | `trigger="onboarding"` | `test_screening_is_persisted_with_evidence` |
| Screen on list update | ✅ | `rescreen_all(trigger="list_update")` | — |
| Screen at periodic review | ✅ | `due_for_review` + `trigger="periodic"` | `test_review_interval_shortens_with_risk` |
| Screen before transactions | ◐ | `trigger="transaction"` accepted; no transaction module to call it | — |
| Freeze **without delay, without tipping off** | ◐ | `blocked` flag and explicit instruction text; no freeze workflow | `test_listed_ubo_blocks_clean_company` |
| Report matches to supervisor and FIU | ⬚ | M4 | — |

**Resolved.** PF was elevated to a standalone offence with its own chapter, and
folding it into generic sanctions screening understated it. There is no
separate PF list to load — PF designations sit inside the UN and OFAC lists and
are distinguishable only by the **designating programme** (UNSCR 1718 DPRK,
1737/2231 Iran, OFAC NPWMD), so the fix was classification rather than
ingestion. Alerts now state the specific obligation, since the operator acting
on one may not know which regime a designation falls under. The PF-specific
*reporting route* still depends on M4.

## 4. Risk-Based Approach

| Obligation | Status | Implementation | Test |
|---|---|---|---|
| Risk-based, proportionate controls | ✅ | `risk/ruleset.yaml`, versioned `2025.12.1` | `TestRiskModel` |
| Assess country, sector, channel, ownership, product risk | ✅ | 9 weighted factors | `test_cumulative_factors_reach_high` |
| EDD for high-risk relationships | ✅ | `requires_edd` | `test_sanctions_hit_forces_high` |
| EDD for PEPs, source of wealth, senior approval | ◐ | PEP triggers EDD; no SoW capture or approval workflow | `test_pep_triggers_edd_even_at_low_score` |
| High-risk jurisdictions (FATF lists) | ◐ | Tier accepted as input; **not auto-populated** from FATF lists | `test_blacklist_jurisdiction_forces_high` |
| Documented, reviewable methodology | ✅ | YAML ruleset with version + effective date on every assessment | `test_assessment_records_ruleset_version` |
| Adverse media / negative news as an EDD input | ◐ | `screening/adverse_media.py` — GDELT DOC 2.0, Latin + Arabic, operator-dispositioned before it scores | `tests/test_adverse_media.py` |

**Gap:** FATF grey/black list membership is a manual input. It should be
ingested as a dataset like any other list — it changes three times a year and
manual entry will drift.

**Adverse media, scoped honestly.** The `adverse_media` factor in the ruleset
is now fed by a real check rather than always scoring `none`. It is a
screening aid built on a free news index, not a curated adverse-media
database: GDELT tells you an article exists, it does not assess whether the
allegation is credible or whether the person named is your customer. A human
marks each finding relevant before it touches a rating, and the check is
operator-triggered rather than automatic — the provider is rate-limited to one
request every five seconds, which rules out running it across a whole customer
book on every list refresh. What is still missing against a commercial vendor
is the analyst layer: entity resolution, allegation assessment, and structured
coverage of relatives and close associates.

## 5. Reporting

| Obligation | Status | Implementation |
|---|---|---|
| Register on goAML | n/a | Organisational, not software |
| File STR/SAR on reasonable suspicion, without delay | ⬚ | M4 — `reports` table exists |
| File FFR (funds freeze) / PNMR (partial name match) | ⬚ | M4 |
| No tipping off | ◐ | Warning surfaced; no access controls preventing disclosure |

## 6. Record Keeping & Governance

| Obligation | Status | Implementation | Test |
|---|---|---|---|
| Retain records **5 years** after relationship ends | ✅ | `close_relationship` computes and stores the date | `test_five_year_retention_recorded` |
| Auditable records of decisions | ✅ | Append-only `audit_log`, enforced by DB trigger | `TestAuditImmutability` |
| Evidence that screening occurred, including clear results | ✅ | Every run persisted regardless of outcome | `test_clear_screening_still_recorded` |
| Explainable alert decisions | ✅ | Full per-feature score breakdown stored per alert | `test_alert_stores_score_breakdown` |
| Human disposition of alerts | ✅ | Original score never overwritten | `test_disposition_preserves_original_score` |
| Appoint an MLRO | n/a | Organisational |
| Staff training | ⬚ | Out of scope |
| Independent audit of the AML programme | ⬚ | Out of scope |

**Senior-management liability** under the new law raises the bar on audit
integrity specifically. Trigger-level enforcement was chosen over application
-level convention for exactly this reason: tampering requires bypassing the
database, not calling a different function.

## 7. Scope Extensions in Law 10/2025

| Change | Status | Note |
|---|---|---|
| Proliferation financing as standalone offence | ⚠ ⬚ | Highest-priority gap |
| VASPs explicitly in scope | ◐ | `virtual_assets` sector scores 35 points; no VASP-specific controls |
| Virtual assets / crypto | ◐ | `crypto` identifier type ingested and matched; no wallet screening |
| Digital systems & encryption | n/a | Not a screening obligation |

---

## Prioritised gap list

1. **PF screening path** — standalone offence, currently absent. Highest priority.
2. **Load UN + global sanctions by default** — adapters exist and are untested against live data; only the UAE list is loaded today.
3. **Automate the 24-hour refresh** — the control is detection-only until a scheduler runs it.
4. **Ingest FATF grey/black lists** — remove a manual input that will drift.
5. **BO 15-working-day update tracking** — explicit deadline in the regulation.
6. **STR/SAR generation** — M4.
7. **Purpose/nature of relationship, source of wealth** — small schema additions closing real CDD gaps.
8. **Identity-document verification** — largest gap; needs a build-or-buy decision.
9. **Adverse-media periodic re-run** — the check exists but runs on demand only;
   it should be prompted at each scheduled risk review rather than relying on an
   operator remembering. Rate limits rule out a bulk sweep, so this belongs on
   the review cycle, not the refresh cycle.

Items 2 and 3 are close to free and materially expand real coverage; they
should come before anything else.
