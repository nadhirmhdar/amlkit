# AMLKit — Consolidated Todo & Phased Implementation Plan

**Source of truth for this document:** GitHub Issues at `nadhirmhdar/amlkit`.
Every item that already has a GitHub issue is cross-referenced by number.
Items without an issue number are new requirements added in this document.
Resolved/merged issues are noted where relevant.

**Do not implement anything from this document without working on the
designated feature branch for that item.**

---

## How to read this document

| Marker | Meaning |
|---|---|
| `#NNN` | Existing GitHub issue |
| `[NEW]` | Net-new requirement added in this revision |
| `[MERGED]` | Two items consolidated — original issue(s) noted |
| `[DECISION]` | Requires explicit sign-off from Nadhir / V before work starts |
| `[RESEARCH]` | Discovery/analysis task — no code change until research is complete |

---

## Part 1 — All Open Items

### Critical Bugs (must fix before any new feature work)

| ID | Title | Phase |
|---|---|---|
| #144 | Tests workflow failing on master — syntax error blocks whole suite | 1 |
| #140 | Customer retention purge silently cascades and erases statutory TFS freeze obligations | 1 |
| #139 | Arabic name normalization corrupts names with inherent Al prefix (e.g. Ilyas, Ilham) — 0.0 match score | 1 |
| #138 | Cross-tenant MLRO email disclosure via cleartext To header in sanctions staleness alerts | 1 |
| #163 | Dead code `resolve_ubo_chain()` causes corporate UBO double-counting in `ownership_state()` and flattened diagrams | 1 |
| #162 | STR Builder defaults reporting entity to "Grovisor Business Consultants" due to missing `session.org_name` | 1 |
| #142 | goAML XML filings hardcode default reporting entity Grovisor Consultants and Dubai HQ | 1 |
| #141 | Deceptive confirmation message claims report submitted to UAE FIU when no transmission occurred | 1 |
| #161 | POST /reports/{report_id}/submit and mobile endpoint lack MLRO role enforcement | 1 |

### High Bugs

| ID | Title | Phase |
|---|---|---|
| #97 | UBO total ownership >100% accepted without validation — risk scoring compromised | 1 |
| #96 | retention_until is NULL for all customer records — record retention completely broken | 1 |
| #79 | Extend retention_until dates stored under the old 5-year rule | 1 |
| #167 | Four-eyes review disposition bug exposed once #144's syntax error is fixed | 1 |
| #164 | POST /api/ai/draft-narrative lacks CSRF protection and rate limiting on paid LLM endpoint processing PII | 2 |
| #143 | Rate limiter resolves link-local reverse proxy IP, collapsing rate limits globally across all tenants on Cloud Run | 2 |
| #71 | Static check for tenant-isolation conventions (org_id scoping) | 2 |

### Medium Bugs / Security

| ID | Title | Phase |
|---|---|---|
| #99 | POST /admin/* returns HTTP 200 for officer role instead of HTTP 403 | 2 |
| #100 | Alerts page: N duplicate select[name=status] DOM elements — grows unboundedly | 4 |
| #102 | Authorization errors exposed in URL query string — in browser history and server logs | 2 |
| #98 | Negative UBO percentage causes HTTP 500 instead of 422 validation error | 1 |
| #84 | Merge #83 and set AMLKIT_REGISTRATION_INVITE_CODE in Cloud Run | 6 |
| #85 | EU FSF token — EU sanctions refresh failing | 6 |

### Low Bugs / Enhancements

| ID | Title | Phase |
|---|---|---|
| #103 | Password toggle button has no aria-label — screen-reader accessibility failure | 3 |
| #101 | Audit log loads all records at once — no pagination | 4 |
| #82 | CSP: remove 'unsafe-inline' from script-src | 2 |
| #77 | Show organisation name in UI so operators know which org they are in | 5 |
| #73 | Move business logic out of api/app.py (~2,280 lines) | 10 |
| #72 | Warn operators when a sanctions source is stale or failing | 4 |
| #40 | Refresh error | 1 |
| #165 | Customer details page shows stale 5-year retention copy (contradicts Cabinet Resolution 134/2025 and PR #86) | 1 |

### Compliance / Configuration

| ID | Title | Phase |
|---|---|---|
| #78 | Verify legally required record-retention period (8 vs 10 years) before scheduling purge | 0 |
| #145 | CodeQL Advanced failing — code scanning not enabled | 10 |

---

### New Items Added in This Revision

#### UI / UX

| ID | Title | Phase |
|---|---|---|
| [NEW] | Review all buttons on the Homepage — remove unnecessary arrow icons; keep arrows only where they communicate genuine navigation or directionality | 1 |
| [NEW] | Investigate and fix/recreate the non-working top-left corner button | 1 |
| [NEW] | Review overall UI/UX consistency across all pages | 1 |
| [NEW] | Review the bug-reporting/report-issue experience — ensure it matches AMLKit UI/UX | 1 |
| [NEW] | Standardise MLRO terminology throughout the product (related to #77 org-name display) | 1 |
| [NEW] `[DECISION]` | Review whether Admin Settings should become Settings — review existing structure and comparable products before deciding | 5 |

#### Greeting / Timezone

| ID | Title | Phase |
|---|---|---|
| [NEW] `[RESEARCH]` | Review Home/Dashboard greeting logic | 0 |
| [NEW] `[RESEARCH]` | Verify greetings correctly consider the user's time and timezone | 0 |
| [NEW] `[RESEARCH]` | Investigate behaviour when a user travels or their location/timezone changes | 0 |
| [NEW] | Test device timezone changes | 1 |
| [NEW] | Test browser timezone changes | 1 |
| [NEW] | Test users travelling between countries (timezone switch) | 1 |
| [NEW] | Test daylight-saving timezone changes where applicable | 1 |
| [NEW] `[DECISION]` | Determine whether AMLKit should use device/browser timezone, configured user timezone, or organisation timezone as the source of truth | 0 |
| [NEW] | Ensure AMLKit does not unnecessarily collect or store precise physical location just to generate a greeting | 0 |

#### Dashboard / Investor Visibility

| ID | Title | Phase |
|---|---|---|
| [NEW] `[RESEARCH]` | Review Alerts/Dashboard experience — identify what is genuinely useful vs. decorative | 4 |
| [NEW] `[RESEARCH]` | Assess whether meaningful graphs and visualisations should be added — identify metrics derivable from existing AMLKit data only | 4 |
| [NEW] `[DECISION]` | Consider investor-facing visibility of product activity without compromising the dashboard's utility for AML users | 4 |
| [NEW] | Do not create fake, decorative, or unsupported metrics | 4 |

#### Audit

| ID | Title | Phase |
|---|---|---|
| [NEW] | Perform a complete audit-log review — identify missing compliance-critical audit events | 2 |
| [NEW] | Review audit-log access controls | 2 |
| [NEW] | Review tenant isolation in audit logs (related to #71) | 2 |
| [NEW] | Review sensitive information exposed through audit logs | 2 |
| [NEW] | Review audit-log integrity and protection from unauthorised modification/deletion | 2 |

#### APIs

| ID | Title | Phase |
|---|---|---|
| [NEW] `[RESEARCH]` | Identify all APIs required by AMLKit | 6 |
| [NEW] `[RESEARCH]` | Categorise APIs: Mandatory / Recommended / Optional / Future | 6 |
| [NEW] `[RESEARCH]` | Document each API: provider, purpose, data exchanged, authentication, cost, limits, failure handling, security implications | 6 |
| [NEW] `[DECISION]` | Prepare the confirmed Mandatory API list for V — do not classify as mandatory without confirming AMLKit genuinely requires it | 6 |

#### Client Data Protection

| ID | Title | Phase |
|---|---|---|
| [NEW] `[RESEARCH]` | Review what client/customer data AMLKit collects, processes, stores, and transmits | 2 |
| [NEW] `[RESEARCH]` | Identify sensitive AML/KYC/CDD/UBO/screening/risk/compliance data and determine whether additional protection is required | 2 |
| [NEW] | Review encryption, access control, tenant isolation, retention, deletion, masking, backups, and logging for client data | 2 |

#### Comparable Product Research

| ID | Title | Phase |
|---|---|---|
| [NEW] `[RESEARCH]` | Research comparable AML/KYC/compliance SaaS products — review publicly available privacy policies, data policies, retention practices, security practices, data residency, cookie policies, Terms of Use, and subprocessor information | 0 |
| [NEW] | Use research for benchmarking only — do not copy competitor wording | 0 |

#### Accessibility

| ID | Title | Phase |
|---|---|---|
| [NEW] `[RESEARCH]` | Research applicable UAE accessibility requirements and relevant US requirements (ADA, Section 508) | 0 |
| [NEW] | Use current WCAG guidance as a practical benchmark | 3 |
| [NEW] | Review colour contrast across all pages | 3 |
| [NEW] | Review font colours — identify overly light text that should use darker grey | 3 |
| [NEW] | Review keyboard navigation | 3 |
| [NEW] | Review focus states | 3 |
| [NEW] | Review screen-reader compatibility (related to #103) | 3 |
| [NEW] | Review semantic structure (headings, landmarks, regions) | 3 |
| [NEW] | Review accessible labels for icons and buttons | 3 |
| [NEW] | Review forms and error messages for accessibility | 3 |
| [NEW] | Review responsive/mobile accessibility | 3 |

#### Desktop / Local Data

| ID | Title | Phase |
|---|---|---|
| [NEW] `[RESEARCH]` | Review desktop/browser local data storage: LocalStorage, SessionStorage, IndexedDB, cookies, browser cache, cached API responses, downloaded files, offline/local persistence | 2 |
| [NEW] | Test logout and session expiry — verify sensitive data is cleared | 2 |
| [NEW] | Test browser restart — verify sensitive data is not retained | 2 |
| [NEW] | Test switching users on the same device — verify no data leaks between sessions | 2 |
| [NEW] `[DECISION]` | Determine whether sensitive client data remains locally accessible after logout and whether that is acceptable | 2 |

#### Privacy / Cookies / Ads

| ID | Title | Phase |
|---|---|---|
| [NEW] `[RESEARCH]` | Determine whether AMLKit actually displays advertisements | 8 |
| [NEW] `[RESEARCH]` | Determine whether third-party advertising technologies are present | 8 |
| [NEW] `[RESEARCH]` | Determine whether analytics/tracking technologies are present | 8 |
| [NEW] `[RESEARCH]` | Determine whether advertising-related cookies are present | 8 |
| [NEW] `[RESEARCH]` | Determine whether any third parties receive user/device information for advertising or measurement | 8 |
| [NEW] `[DECISION]` | Determine whether consent or cookie-preference controls are required | 8 |
| [NEW] | Review Privacy Policy accuracy — wording must reflect actual implementation, not falsely imply advertising if none exists | 8 |
| [NEW] | Review Terms of Use | 8 |
| [NEW] | Review Cookie Policy | 8 |
| [NEW] | Review Cookie Preferences controls | 8 |
| [NEW] | Review Privacy/cookie notices | 8 |
| [NEW] | Do not add advertising functionality merely because comparable websites have ads | 8 |

#### Stripe / Subscription

| ID | Title | Phase |
|---|---|---|
| [NEW] `[DECISION]` | Assess Stripe integration readiness | 7 |
| [NEW] `[DECISION]` | Plan subscription management | 7 |
| [NEW] `[DECISION]` | Plan pricing tiers | 7 |
| [NEW] `[DECISION]` | Plan trials | 7 |
| [NEW] `[DECISION]` | Plan upgrade/downgrade flow | 7 |
| [NEW] `[DECISION]` | Plan cancellation flow | 7 |
| [NEW] `[DECISION]` | Plan failed-payment handling | 7 |
| [NEW] `[DECISION]` | Plan usage limits and consumption tracking | 7 |
| [NEW] `[DECISION]` | Plan overage handling | 7 |
| [NEW] `[DECISION]` | Plan organisation-level billing | 7 |
| [NEW] | Plan usage/consumption dashboard | 7 |
| [NEW] | Plan cost-management dashboard | 7 |
| [NEW] | Review strict separation between billing data and AML/client data | 7 |

#### Product Roadmap

| ID | Title | Phase |
|---|---|---|
| [NEW] `[DECISION]` | Create AMLKit Product Roadmap diagram — clearly distinguish Current / Near-term / Planned / Future; include AML/CFT, CDD/KYC, UBO, Screening, Risk, Alerts, Cases, Reporting, Audit, Integrations, Mobile, Analytics, Billing, AI | 9 |
| [NEW] | Never present planned functionality as existing functionality in the roadmap or any investor-facing material | 9 |

---

## Part 2 — Items Merged / Refined

| Original | Merged into | Reason |
|---|---|---|
| #77 "Show org name in UI" | [NEW] "Standardise MLRO terminology" | Both address operator-facing identity labelling; #77 remains its own fix but the new item extends the scope to all MLRO/role terminology |
| #71 "Static tenant-isolation check" | [NEW] "Review tenant isolation in audit logs" | Phase 2 audit work directly overlaps the static-check goal; #71 remains in Phase 2 and audit-log review supplements it |
| #101 "Audit log pagination" | [NEW] "Perform complete audit-log review" | Pagination is a sub-task of the broader audit-log review; tracked separately but executed together |
| #103 "Password toggle aria-label" | [NEW] "Review screen-reader compatibility" | #103 is the specific fix; the new item is the systematic review that may surface more like it |
| #72 "Warn on stale sanctions" | [NEW] Dashboard review | Staleness warnings feed into the dashboard experience; both remain separate items |
| CONTINUOUS_IMPROVEMENT entries (goaml, kyt, str_builder, etc.) | Various open issues (#140–#164) | Log entries that were not yet filed as issues have been captured as the issues listed above; no standalone duplication needed |

---

## Part 3 — Complete Phased Implementation Plan

### Phase 0 — Discovery & Verification *(no code changes)*

**Goal:** Research and inspect before any implementation. Gate for all other phases.

| # | Item |
|---|---|
| 0.1 | Research comparable AML/KYC/compliance SaaS products — privacy, data, security, cookies, subprocessors `[RESEARCH]` |
| 0.2 | Review Home/Dashboard greeting logic — understand current implementation `[RESEARCH]` |
| 0.3 | Investigate greeting timezone behaviour — what happens when user travels or changes timezone `[RESEARCH]` |
| 0.4 | `[DECISION]` Determine greeting timezone source of truth (device, browser, configured user, org) |
| 0.5 | Ensure greeting does not collect/store physical location unnecessarily |
| 0.6 | `[DECISION]` Verify legally required record-retention period (#78) — 8 vs 10 years |
| 0.7 | Research UAE accessibility requirements + US ADA/Section 508 requirements `[RESEARCH]` |
| 0.8 | Identify all APIs required by AMLKit and categorise Mandatory / Recommended / Optional / Future `[RESEARCH]` |
| 0.9 | `[DECISION]` Prepare Mandatory API list for V — confirm each one is genuinely required |
| 0.10 | Review what client/customer data AMLKit collects, processes, stores, and transmits `[RESEARCH]` |
| 0.11 | Determine whether advertising technologies, analytics, or tracking technologies are present `[RESEARCH]` |

**Gates Phase 1:** 0.4, 0.5, 0.6 must be decided.

---

### Phase 1 — Critical Bugs & Core UX

**Goal:** All critical/high bugs fixed; core UX issues resolved; test suite green.

| # | Item | GitHub |
|---|---|---|
| 1.1 | Fix tests workflow — syntax error blocking entire suite | #144 |
| 1.2 | Fix four-eyes review disposition bug (unblocked by 1.1) | #167 |
| 1.3 | Fix Arabic name normalisation corrupting "Al-" prefix names (0.0 match score) | #139 |
| 1.4 | Fix cross-tenant MLRO email disclosure via cleartext To header | #138 |
| 1.5 | Fix customer retention purge cascading to TFS freeze obligations | #140 |
| 1.6 | Fix retention_until NULL for all customer records | #96 |
| 1.7 | Extend retention_until dates stored under old 5-year rule (after 0.6 confirmed) | #79 |
| 1.8 | Fix stale 5-year retention copy on customer details page | #165 |
| 1.9 | Fix UBO total ownership >100% accepted without validation | #97 |
| 1.10 | Fix negative UBO percentage returning HTTP 500 instead of 422 | #98 |
| 1.11 | Fix UBO double-counting due to dead `resolve_ubo_chain()` | #163 |
| 1.12 | Fix STR Builder defaulting reporting entity to "Grovisor Business Consultants" | #162 |
| 1.13 | Fix goAML XML hardcoding Grovisor Consultants and Dubai HQ | #142 |
| 1.14 | Fix deceptive "report submitted to UAE FIU" confirmation message | #141 |
| 1.15 | Fix POST /reports lacking MLRO role enforcement | #161 |
| 1.16 | Investigate and fix refresh error | #40 |
| 1.17 | Remove unnecessary arrow icons from Homepage buttons (keep arrows only where directionally meaningful) | [NEW] |
| 1.18 | Investigate and fix/recreate the non-working top-left corner button | [NEW] |
| 1.19 | Review and fix the bug-reporting/report-issue experience — match AMLKit UI/UX | [NEW] |
| 1.20 | Standardise MLRO terminology throughout the product | [NEW] |
| 1.21 | Test and fix greeting timezone logic — device, browser, travel, DST scenarios | [NEW] |
| 1.22 | Review overall UI/UX consistency across all pages | [NEW] |

**Dependencies:** 1.1 must complete before 1.2. 1.6 must complete before 1.7. 0.6 (decision) gates 1.7.

---

### Phase 2 — Security, Audit & Data Protection

**Goal:** All security gaps closed; audit log complete and protected; client data properly controlled; local data tested.

| # | Item | GitHub |
|---|---|---|
| 2.1 | Fix rate limiter IP resolution — link-local proxy IP collapsing limits globally | #143 |
| 2.2 | Fix POST /api/ai/draft-narrative — add CSRF + rate limiting | #164 |
| 2.3 | Fix POST /admin/* returning HTTP 200 for officer role | #99 |
| 2.4 | Remove 'unsafe-inline' from CSP script-src | #82 |
| 2.5 | Fix authorization errors exposed in URL query string | #102 |
| 2.6 | Static check for tenant-isolation (org_id scoping conventions) | #71 |
| 2.7 | Perform complete audit-log review — identify missing compliance-critical audit events | [NEW] |
| 2.8 | Review audit-log access controls | [NEW] |
| 2.9 | Review tenant isolation in audit logs | [NEW] |
| 2.10 | Review sensitive information exposed through audit logs | [NEW] |
| 2.11 | Review audit-log integrity and protection from unauthorised modification/deletion | [NEW] |
| 2.12 | Review client/customer data: encryption, access control, tenant isolation, retention, deletion, masking, backups, logging | [NEW] |
| 2.13 | Review desktop/browser local data storage: LocalStorage, SessionStorage, IndexedDB, cookies, cache | [NEW] |
| 2.14 | Test logout and session expiry — verify sensitive data is cleared | [NEW] |
| 2.15 | Test browser restart — verify sensitive data not retained | [NEW] |
| 2.16 | Test switching users on the same device — verify no data leakage | [NEW] |
| 2.17 | `[DECISION]` Determine whether sensitive client data remaining locally after logout is acceptable | [NEW] |

**Dependencies:** Phase 1 must be complete. 2.4 (CSP) requires prior audit of all inline scripts (see CSP_AUDIT.md). 2.17 decision gates any client-side storage changes.

---

### Phase 3 — Accessibility

**Goal:** AMLKit meets practical accessibility requirements; WCAG baseline established; all screen-reader and keyboard gaps fixed.

| # | Item | GitHub |
|---|---|---|
| 3.1 | Apply UAE + US (ADA/Section 508) accessibility research findings from Phase 0 (0.7) | [NEW] |
| 3.2 | Review and fix colour contrast across all pages | [NEW] |
| 3.3 | Review and fix font colours — identify and darken overly light text | [NEW] |
| 3.4 | Review and fix keyboard navigation | [NEW] |
| 3.5 | Review and fix focus states | [NEW] |
| 3.6 | Fix password toggle button missing aria-label | #103 |
| 3.7 | Review and fix screen-reader compatibility across all interactive elements | [NEW] |
| 3.8 | Review and fix semantic structure (headings, landmarks, regions) | [NEW] |
| 3.9 | Review and fix accessible labels for all icons and buttons | [NEW] |
| 3.10 | Review and fix forms and error messages for accessibility | [NEW] |
| 3.11 | Review and fix responsive/mobile accessibility | [NEW] |

**Dependencies:** Phase 0 (0.7 research) must be complete. Phase 2 security/CSP work should be done first (CSP changes can affect inline event handlers that accessibility fixes must replace).

---

### Phase 4 — Dashboard / Product Experience

**Goal:** Dashboard shows genuinely useful, data-backed information; alerts experience improved; no fake metrics.

| # | Item | GitHub |
|---|---|---|
| 4.1 | Review Alerts/Dashboard experience — identify what is genuinely useful | [NEW] |
| 4.2 | Identify metrics that can be derived from existing AMLKit data | [NEW] |
| 4.3 | `[DECISION]` Determine investor-facing visibility approach — what to show, how to separate from AML workflow | [NEW] |
| 4.4 | Add meaningful graphs/visualisations where data supports them (no decorative/fake metrics) | [NEW] |
| 4.5 | Warn operators when a sanctions source is stale or failing | #72 |
| 4.6 | Fix duplicate select[name=status] DOM elements on alerts page | #100 |
| 4.7 | Add audit log pagination | #101 |
| 4.8 | Implement alerts drawer / compliance notifications sidebar (P33_IMPLEMENTATION.md) | [NEW] |

**Dependencies:** Phases 1–3 complete. 4.3 decision required before 4.4. Do not add investor metrics that misrepresent the product.

---

### Phase 5 — Settings / Administration

**Goal:** Admin Settings structure reviewed and rationalised; org identity and roles clearly presented.

| # | Item | GitHub |
|---|---|---|
| 5.1 | Show organisation name in UI so operators know which org they are in | #77 |
| 5.2 | `[DECISION]` Review whether Admin Settings should become Settings — review structure and comparable products | [NEW] |
| 5.3 | Implement Settings structure change if decided in 5.2 | [NEW] |
| 5.4 | Review administrative controls and role boundaries | [NEW] |

**Dependencies:** Phase 0 comparable product research (0.1). Decision 5.2 must precede 5.3.

---

### Phase 6 — APIs / External Integrations

**Goal:** All API dependencies identified, categorised, documented, and mandatory ones confirmed for V.

| # | Item | GitHub |
|---|---|---|
| 6.1 | Register EU FSF token and set AMLKIT_EU_FSF_TOKEN — EU sanctions refresh failing | #85 |
| 6.2 | Merge #83 and set AMLKIT_REGISTRATION_INVITE_CODE in Cloud Run | #84 |
| 6.3 | Document all required APIs with: provider, purpose, data exchanged, auth, cost, limits, failure handling, security implications | [NEW] |
| 6.4 | `[DECISION]` Present Mandatory API list to V for sign-off | [NEW] |
| 6.5 | Review and integrate any mandatory APIs confirmed by V | [NEW] |
| 6.6 | Plan integration architecture for Recommended and Optional APIs | [NEW] |

**Dependencies:** Phase 0 (0.8, 0.9) API research complete. Decision 6.4 must be signed off before 6.5.

---

### Phase 7 — Billing / Stripe

**Goal:** Subscription model designed and implemented; billing data strictly separated from AML data.

| # | Item | GitHub |
|---|---|---|
| 7.1 | `[DECISION]` Assess Stripe integration readiness | [NEW] |
| 7.2 | `[DECISION]` Finalise pricing tiers | [NEW] |
| 7.3 | `[DECISION]` Finalise trial model | [NEW] |
| 7.4 | Implement subscription management (upgrade/downgrade/cancel) | [NEW] |
| 7.5 | Implement failed-payment handling | [NEW] |
| 7.6 | Implement usage limits and consumption tracking | [NEW] |
| 7.7 | Implement overage handling | [NEW] |
| 7.8 | Implement organisation-level billing | [NEW] |
| 7.9 | Build usage/consumption dashboard | [NEW] |
| 7.10 | Build cost-management dashboard | [NEW] |
| 7.11 | Verify strict separation between billing data and AML/client data | [NEW] |

**Dependencies:** Phase 5 (Settings/Admin) should be complete as billing controls live in admin. Decisions 7.1–7.3 must precede 7.4–7.11.

---

### Phase 8 — Privacy / Cookies / Ads

**Goal:** All legal documents accurately reflect actual implementation; no false advertising implications; consent controls in place if required.

| # | Item | GitHub |
|---|---|---|
| 8.1 | Determine whether AMLKit displays advertisements (confirm: does it or does it not?) | [NEW] |
| 8.2 | Determine whether third-party advertising technologies are present | [NEW] |
| 8.3 | Determine whether analytics/tracking technologies are present | [NEW] |
| 8.4 | Determine whether advertising-related cookies are present | [NEW] |
| 8.5 | Determine whether any third parties receive user/device data for advertising or measurement | [NEW] |
| 8.6 | `[DECISION]` Determine whether consent/cookie-preference controls are required | [NEW] |
| 8.7 | Review Privacy Policy — ensure wording reflects actual implementation; remove any false advertising implications | [NEW] |
| 8.8 | Review Terms of Use | [NEW] |
| 8.9 | Review Cookie Policy | [NEW] |
| 8.10 | Review Cookie Preferences controls | [NEW] |
| 8.11 | Review Privacy/cookie notices | [NEW] |
| 8.12 | Use comparable product research (from Phase 0) for benchmarking only — do not copy wording | [NEW] |

**Dependencies:** Phase 0 (0.1 research, 0.11 analytics/tracking research) complete. Decision 8.6 gates 8.10.

---

### Phase 9 — Product Roadmap / Commercial Presentation

**Goal:** Clear, honest product roadmap created; investor-facing presentation prepared; current vs. planned capabilities unambiguous.

| # | Item | GitHub |
|---|---|---|
| 9.1 | `[DECISION]` Agree scope and format of AMLKit Product Roadmap with V | [NEW] |
| 9.2 | Create AMLKit Product Roadmap diagram — Current / Near-term / Planned / Future across: AML/CFT, CDD/KYC, UBO, Screening, Risk, Alerts, Cases, Reporting, Audit, Integrations, Mobile, Analytics, Billing, AI | [NEW] |
| 9.3 | Never present planned functionality as existing functionality | [NEW] |
| 9.4 | Prepare investor-facing product activity view (from Phase 4 dashboard decisions) | [NEW] |

**Dependencies:** Phase 4 dashboard decisions (4.3). Decision 9.1 must precede 9.2.

---

### Phase 10 — Final QA & Hardening

**Goal:** Full regression across all previous phases; no regressions; codebase clean.

| # | Item | GitHub |
|---|---|---|
| 10.1 | Continue api/app.py refactor — reduce below 1,500 lines | #73 |
| 10.2 | Enable CodeQL Advanced code scanning | #145 |
| 10.3 | Full regression test suite (admin, MLRO, officer roles) | [NEW] |
| 10.4 | Accessibility re-test (post Phase 3 changes) | [NEW] |
| 10.5 | Security re-test (post Phase 2 changes) | [NEW] |
| 10.6 | Privacy/local-data re-test (post Phase 8 changes) | [NEW] |
| 10.7 | Billing integration testing (post Phase 7 changes) | [NEW] |
| 10.8 | API integration testing (post Phase 6 changes) | [NEW] |
| 10.9 | Mobile (Android app) regression test | [NEW] |
| 10.10 | Cross-tenant IDOR test coverage for all mobile API routes (alerts/reports/UBO) | [NEW] |

**Dependencies:** All Phases 1–9 complete.

---

## Part 4 — Phase Dependencies Summary

```
Phase 0 (Discovery)
  │
  ├─► Phase 1 (Critical Bugs & Core UX)  ← Decision 0.4, 0.6 required
  │     │
  │     ├─► Phase 2 (Security, Audit, Data Protection)
  │     │     │
  │     │     └─► Phase 3 (Accessibility)
  │     │           │
  │     │           └─► Phase 4 (Dashboard / Product Experience)  ← Decision 4.3
  │     │                 │
  │     │                 └─► Phase 5 (Settings / Administration)  ← Decision 5.2
  │     │                       │
  │     │                       └─► Phase 6 (APIs / Integrations)  ← Decision 6.4
  │     │                             │
  │     │                             ├─► Phase 7 (Billing / Stripe)  ← Decisions 7.1–7.3
  │     │                             │
  │     │                             └─► Phase 8 (Privacy / Cookies / Ads)  ← Decision 8.6
  │     │                                   │
  │     │                                   └─► Phase 9 (Roadmap / Commercial)  ← Decision 9.1
  │     │                                         │
  │     │                                         └─► Phase 10 (Final QA)
  │
  └─► Phase 0 research outputs feed: Phase 3, Phase 5, Phase 6, Phase 8
```

---

## Part 5 — Items Requiring Nadhir / V Decision (Consolidated)

These items are blocked until an explicit decision is made. No code should be written.

| Decision | Context | Blocking |
|---|---|---|
| **Greeting timezone source of truth** | Device/browser timezone, configured user timezone, or org timezone? | Phase 1 greeting implementation |
| **Record retention period** (#78) | 8 vs 10 years — Cabinet Resolution 134/2025 — must be confirmed by legal | Phase 1 retention fixes |
| **Admin Settings → Settings** | Is a rename/restructure appropriate given existing structure? | Phase 5 |
| **Investor-facing dashboard** | What activity to show investors without compromising AML operator experience? | Phase 4 visualisations |
| **Mandatory API list** | Confirm which APIs are genuinely mandatory before V commits to them | Phase 6 |
| **Stripe model** | Pricing tiers, trial length, overage policy, org-level vs user-level billing | Phase 7 |
| **Cookie/consent controls** | Are consent controls legally required given the actual technology stack? | Phase 8 |
| **Product Roadmap format** | Scope, format, audience, distribution | Phase 9 |
| **Local data after logout** | Is it acceptable that sensitive data may persist locally post-logout? | Phase 2 |

---

## Part 6 — Recommended Implementation Sequence

1. **Start Phase 0 immediately** — all decisions and research happen in parallel with Phase 1 bug triage.
2. **Phase 1** — fix all critical/high bugs before any new feature work; get CI green (#144 first).
3. **Decisions 0.4, 0.6** — unblock Phase 1 retention and timezone items. Target: before Phase 1 completes.
4. **Phase 2** — security and audit hardening directly after Phase 1; this is a pre-requisite for investor-facing or commercial work.
5. **Phase 3** — accessibility in parallel with Phase 4 preparation.
6. **Phase 4** — dashboard improvements after accessibility; investor view decision must be made.
7. **Phase 5** — settings rationalisation feeds into Phase 6 API and Phase 7 billing placement.
8. **Phase 6** — API work: fix EU token (#85) immediately (it is blocking sanctions coverage); full API inventory before billing.
9. **Phase 7** — billing only after Phases 4–6 are stable; decisions 7.1–7.3 must be signed off before any Stripe code.
10. **Phase 8** — privacy review can run in parallel with Phase 7 but legal documents must not be updated until advertising/tracking research (8.1–8.5) is complete.
11. **Phase 9** — roadmap after Phases 4 and 8 give a clear picture of current vs. planned.
12. **Phase 10** — full QA pass; do not begin until all phases are complete.

---

*Last updated: 2026-09-19. Maintained in `TODO.md` at the repo root. GitHub issues remain the canonical per-item tracker; this file is the phased view across all of them.*
