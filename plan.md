# AMLKit UAE Retrofit: Feasibility Analysis & Implementation Plan

**Date:** 2026-09-12
**Status:** Analysis Complete — Awaiting Approval
**Scope:** Retrofit AMLKit for UAE FDL No. (10) of 2025 & Cabinet Resolution No. (134) of 2025

---

## Executive Summary

The proposed 12-week retrofit plan is **largely feasible** given the existing codebase. AMLKit already carries significant UAE-specific infrastructure — EOCN ingestion, Arabic name handling, PF classification, goAML serialization, UBO tracking at 25%, and AED-denominated transaction monitoring. The plan overstates several gaps (describing capabilities that already exist as new work) and understates a few real structural challenges. This document maps each proposed deliverable to the current codebase, flags true gaps, raises concerns, and proposes an adjusted implementation approach.

---

## Codebase Capability Baseline

Before assessing feasibility, here is what AMLKit already ships:

| Capability | Current State | Key Files |
|---|---|---|
| **EOCN Local Terrorist List** | Direct ingestion from UAEIEC, Excel parser, delisting-aware | `ingest/eocn.py` (700+ lines) |
| **UN/OFAC/EU/UK sanctions** | Bulk-loaded, refresh-on-schedule | `ingest/un.py`, `ingest/ofac.py`, `ingest/eu.py`, `ingest/uk.py` |
| **Arabic name matching** | 453-line module: diacritics, transliteration, Buckwalter, blocking keys | `names/arabic.py` |
| **Fuzzy scoring** | Jaro-Winkler with family-name weighting, OpenSanctions logic-v2 weights | `match/scorer.py` (uses `rapidfuzz`) |
| **PF classification** | Standalone module, UNSCR 1718/1737/2231 vs CT regimes | `screening/pf.py` |
| **goAML XML export** | STR, SAR, PNMR, FFR, HRCT, HRCA, DPMSR, REAR | `reporting/goaml.py` |
| **UBO tracking** | 25% threshold, ownership diagrams (Graphviz SVG) | `cases/manager.py`, `cases/diagram.py` |
| **Transaction monitoring** | AED 55,000 large-cash, structuring detection, velocity, high-risk country | `screening/kyt.py` |
| **Risk scoring** | YAML-driven, versioned, EDD triggers, review cycles | `risk/model.py`, `risk/ruleset.yaml` |
| **Adverse media** | GDELT-based, predicate-crime keyword filtering | `screening/adverse_media.py` |
| **Audit trail** | Append-only by DB trigger, org-scoped, 5-year retention | `db.py` |
| **Tenant isolation** | org_id mandatory on every query, session-scoped | `queries.py`, `api/deps.py` |
| **Emirates ID scanning** | MRZ extraction from passport/EID images | `cases/ocr.py`, `api/mobile.py` |

---

## Phase-by-Phase Feasibility Assessment

### Phase 1: Critical Baseline (Weeks 1–3)

#### 1.1 Cold-Start Hard-Gating — CONCERN: MISDIAGNOSIS

**Plan claim:** "99.8% of real applicants in cold-start scenarios return an 'Unavailable' status" treated as a clean pass.

**Codebase reality:** This is **not how AMLKit works**. The screening engine (`match/engine.py:screen()`) operates against a locally-ingested entity database, not a live HTTP API. When `_candidates()` returns no matches, the result is `ScreeningResult(hits=[], clear=True)` — meaning "screened against all loaded lists, no matches found." This is a genuine clear result, not an "unavailable" artifact of missing data.

The actual risk the plan is trying to address is **stale or empty sanctions data** — if the lists have never been loaded, or a refresh failed, screening against an empty database is meaningless. AMLKit already has a staleness mechanism:

- `ingest/loader.py` computes `staleness_report()` — datasets overdue based on `max_age_hours`
- `datasets.last_refresh` and `datasets.entity_count` track currency
- `datasets.is_mandatory` flags lists that must be present

**Feasibility:** HIGH, but the solution is different from what's proposed.

**What's actually needed:**
- A pre-screening check: if any `is_mandatory` dataset has `entity_count = 0` or `last_refresh` is NULL, block onboarding and return a status indicating data has not been loaded
- An API-level guard in `api/app.py`'s onboarding route
- NOT a 24-hour retry timer — a refresh should be triggered immediately instead
- Estimated effort: **2–3 days** (guard logic + tests), not 3 weeks

#### 1.2 Real-Time TFS & 24h Freeze — PARTIALLY EXISTS

**Plan claim:** Need automated freeze within 24 hours of EOCN/UNSC list update match.

**Codebase reality:**
- `match/engine.py:rescreen_all()` already exists and re-screens the entire customer book after each list refresh
- Onboarding already blocks on sanctions hits (`OnboardingResult.blocked = True`) with explicit obligation text from `screening/pf.py:obligation_note()`
- The `blocked` status flag exists on the customer record
- goAML FFR export already exists in `reporting/goaml.py`

**What's missing:**
- No automated freeze workflow (SLA timer, ledger lock, notification chain)
- No `accounts` or `ledger` table — AMLKit is a screening tool, not a banking system. "Freeze an account" requires an integration point with whatever system holds the funds
- No automated FFR generation triggered by a match — currently manual

**Feasibility:** MEDIUM. The screening-to-alert pipeline exists. What's needed is:
- A `freeze_actions` table tracking freeze obligations with SLA deadlines
- A webhook/notification system to alert the MLRO immediately on a match
- Auto-draft FFR on confirmed match
- Estimated effort: **5–7 days**

**Concern:** The plan describes `POST /v1/accounts/freeze/{acc_id}` as if AMLKit manages financial accounts. It does not. AMLKit manages customer compliance records. A freeze action would be recorded as a compliance event, with an integration hook to notify an external system.

#### 1.3 `POST /v1/screenings/check` Endpoint — ALREADY EXISTS

The plan proposes this as new. AMLKit already has:
- `POST /screen` (web UI route in `api/app.py`)
- `POST /customers/screen/{customer_id}` (mobile API in `api/mobile.py`)
- `match/engine.py:screen()` is the core function

The response format differs from the plan's proposal (which uses REST-style JSON), but the underlying capability is present.

**Feasibility:** HIGH. Wrapping the existing `screen()` function in a new versioned API route is straightforward. **1–2 days.**

---

### Phase 2: Identity & Localization (Weeks 4–6)

#### 2.1 Arabic Transliteration — ALREADY EXISTS

**Plan claim:** "Implement Jaro-Winkler token sorting to allow for inverted name flows and match Arabic scripts."

**Codebase reality:** This is AMLKit's **strongest existing capability**:
- `names/arabic.py` (453 lines): full Arabic script normalization, diacritic removal, hamza unification, Buckwalter transliteration, Latin-to-canonical mapping with 100+ variant entries
- `match/scorer.py`: already uses `rapidfuzz.distance.JaroWinkler` with token sorting
- `blocking_keys()` generates phonetic keys that collapse "Mohammed"/"Muhammad"/"Mohd" onto the same candidate set
- Family-name weighting (`FAMILY_NAME_WEIGHT = 1.3`) addresses the "Mohammed is near-noise" problem

**What's actually missing:** Nothing fundamental. The threshold is configurable per-org via `org_settings.alert_threshold`.

**Feasibility:** ALREADY DONE. The plan's `POST /v2/screening/match_config` for enabling Arabic transliteration is unnecessary — it's the default behavior. A configuration endpoint for threshold tuning would be **1 day** of work.

#### 2.2 Emirates ID Disambiguation ("Rarity Gate") — NEW WORK

**Plan claim:** High-collision names (>25 matches) trigger rejection until a valid EID is provided.

**Codebase reality:**
- Emirates ID scanning exists (`cases/ocr.py`, `api/mobile.py:api_scan_emirates_id()`)
- EID MRZ extraction works
- No collision-count logic exists today

**Feasibility:** MEDIUM-HIGH.
- Collision counting against the customer table (same `canonical_key`) is trivial
- The "Rarity Gate" would be a pre-onboarding check
- EID-based disambiguation means matching `id_number` + `id_type='emirates_id'` against existing records
- Estimated effort: **3–4 days**

**Concern:** The collision threshold of 25 is arbitrary. This needs to be empirically calibrated against real UAE name distributions. A configurable threshold per-org is more appropriate.

#### 2.3 3-Layer Predicate Crime Filter — PARTIALLY EXISTS

**Plan claim:** Replace tone/sentiment gating with predicate crime mapping.

**Codebase reality:** `screening/adverse_media.py` already uses:
- `CRIME_KEYWORDS` — a curated list mapping to EOCN/FATF-aligned terms ("money laundering", "fraud", "terrorist financing", etc.)
- `EXCULPATORY_TERMS` — terms like "acquitted", "cleared", "dismissed" for down-ranking
- GDELT is queried by predicate-crime keywords, not by sentiment

**What the plan describes as missing is already the implemented approach.** The module's docstring explicitly states it is "a screening aid, not a curated adverse-media database."

**What's actually missing:**
- The "discard tone" layer doesn't apply — GDELT returns article metadata, not sentiment scores
- Severity classification exists (`worst_severity()`) but could be refined

**Feasibility:** ALREADY LARGELY DONE. Minor refinements to keyword lists: **1–2 days.**

---

### Phase 3: Corporate Transparency & Transaction Monitoring (Weeks 7–9)

#### 3.1 Recursive UBO Engine — PARTIALLY EXISTS

**Plan claim:** Trace holding structures recursively to natural persons; 15-day countdown on structure changes.

**Codebase reality:**
- `ubo_links` table exists with `ownership_pct`, `control_type`, `is_ubo` fields
- `UBO_THRESHOLD_PCT = 25.0` is hardcoded in `cases/manager.py`
- UBO screening at onboarding screens every declared UBO
- `cases/diagram.py` generates ownership SVG diagrams via Graphviz

**What's missing:**
- No recursive traversal through intermediate holding companies — the current model is flat (customer → UBOs), not a graph
- No automated 15-working-day countdown timer for structure updates
- No DED/Free Zone registry integration (external data source)
- No automatic detection of structure changes — currently manual updates only

**Feasibility:** MEDIUM.
- Recursive UBO traversal requires schema changes: `ubo_links` needs a self-referential `parent_ubo_id` or a separate `corporate_layers` table
- The 15-day timer is a new compliance-deadline system (similar to freeze SLA)
- DED/Free Zone registry integration is a **new external dependency** — availability and API access need investigation
- Estimated effort: **7–10 days** for the recursive engine + timer, separate from external integration

**Concern:** DED/Free Zone registries don't have standardized APIs. This may require manual upload or CSV import rather than automated integration.

#### 3.2 Threshold Rules Engine — PARTIALLY EXISTS

**Plan claim:** Sector-specific thresholds for Real Estate, Precious Metals, Gaming, Wire/VA transfers.

**Codebase reality:**
- `kyt.py` already implements `LARGE_CASH_THRESHOLD_AED = 55_000.0` — matches the Real Estate and Precious Metals thresholds
- Structuring detection exists (rolling window, count-based)
- Velocity monitoring exists
- High-risk country flagging exists
- `transactions` table stores `amount_aed` (normalized) and `method`

**What's missing:**
- **Gaming operator threshold (AED 11,000)** — no gaming-sector concept exists. The `sector` field on customers could drive this, but `kyt.py` currently applies the same threshold to all sectors
- **Sector-aware threshold routing** — the rule engine needs to read the customer's sector and apply the appropriate threshold
- **Currency conversion integration** — transactions store `amount_aed` but the conversion is done by the caller (`record_transaction`). The plan proposes Open Exchange Rates API integration; currently conversion is manual
- **Wire/VA AED 3,500 CDD scrutiny threshold** — not implemented

**Feasibility:** HIGH.
- Sector-aware thresholds: refactor `evaluate_transaction()` to accept sector and look up the appropriate threshold from a config table or YAML
- Gaming sector addition: add to `risk/ruleset.yaml` sector list and `kyt.py` threshold map
- Currency conversion: integrate `httpx` call to Open Exchange Rates in `record_transaction()` path
- Estimated effort: **5–7 days**

---

### Phase 4: Audit & goAML (Weeks 10–12)

#### 4.1 Partitioned Triage & IEMS — PARTIALLY EXISTS

**Plan claim:** 5-year retention; IEMS integration; partitioned triage for Article 29 tipping-off prevention.

**Codebase reality:**
- 5-year retention: `RETENTION_YEARS = 5` in `cases/manager.py`, `retention_until` column exists in the `customers` table
- Audit trail: append-only `audit_log` table with DB triggers preventing UPDATE/DELETE
- Tipping-off: the onboarding and alert UI already carries explicit "freeze without delay and do not tip off" messaging
- Four-eyes review: `cases/review.py` implements dual-approval for sanctions dispositions

**What's missing:**
- **IEMS integration** — the FIU's Integrated Enquiry Management System is a government portal; no API documentation is publicly available. This is an **external dependency with unknown feasibility**
- **Partitioned triage UI** — the current web UI doesn't separate compliance-analyst views from customer-facing views at the permission level. All operators see the same interface
- **5-year retention enforcement** — the column exists but no automated purge job runs

**Feasibility:** MIXED.
- Retention enforcement job: **1–2 days**
- Partitioned triage (role-based UI separation): **5–7 days** — requires adding operator roles beyond the current basic model
- IEMS integration: **UNKNOWN** — depends entirely on FIU providing API access/documentation. Should be treated as a Phase 2 item until API specs are obtained

#### 4.2 goAML B2B Adapter — LARGELY EXISTS

**Plan claim:** Generate XML for STR/SAR, FFR, PNMR, and REAR.

**Codebase reality:** `reporting/goaml.py` already serializes:
- STR (Suspicious Transaction Report)
- SAR (Suspicious Activity Report)
- PNMR (Partial Name Match Report)
- FFR (Fund Freeze Report)
- HRCT (High Risk Country Transaction Report)
- HRCA (High Risk Country Activity Report)
- DPMSR (Dealers in Precious Metals and Stones Report)
- REAR (Real Estate Activity Report)

The web UI has report creation (`report_new.html`) and submission workflows (`report_detail.html`).

**What's missing:**
- **Schema validation against official goAML 5.x XSD** — current output is based on the standard but not validated against the FIU's specific XSD
- **Automated FFR generation** on sanctions match (currently manual)
- **5-business-day SLA tracking** for FFR submission
- **B2B API submission** to goAML portal (currently XML is generated for manual upload)

**Feasibility:** HIGH.
- XSD validation: obtain the official schema from goAML portal and add `lxml` validation step — **2–3 days**
- Auto-draft FFR on match: wire `rescreen_all` hit detection to `serialize_goaml_xml()` — **2–3 days**
- SLA tracking: add `filing_deadlines` table — **1–2 days**
- B2B submission: depends on goAML portal providing an API endpoint; otherwise manual upload remains the workflow

#### 4.3 EWRA Proliferation Financing Module — ALREADY EXISTS

**Plan claim:** Distinct PF risk module screening for dual-use goods and WMD-adjacent trade patterns.

**Codebase reality:** `screening/pf.py` is exactly this:
- `PF_PROGRAM_PREFIXES` — UNSCR 1718 (DPRK), 1737/2231 (Iran)
- `PF_OFAC_CODES` — NPWMD, DPRK variants, IFSR, IRAN-TRA
- `classify_programs()` distinguishes proliferation from terrorism
- `obligation_note()` returns regime-specific legal obligations
- Hit objects carry `.is_proliferation`, `.is_terrorism`, `.categories` properties

**Feasibility:** ALREADY DONE. May need ruleset.yaml additions for EWRA-specific PF risk factors, but the classification engine is complete.

---

## Concerns & Risks

### 1. Architectural Misalignment: AMLKit Is Not a Banking System

The plan repeatedly assumes AMLKit manages financial accounts and ledgers (`POST /v1/accounts/freeze/{acc_id}`, `SLA_TIMER initiates at 23:59:59`). AMLKit is a **compliance screening and case management tool** for DNFBPs (real estate agents, precious metals dealers, corporate service providers). It does not hold funds, manage accounts, or process payments.

**Impact:** The freeze workflow must be reimagined as:
1. AMLKit detects a match and creates a freeze obligation record
2. AMLKit notifies the MLRO (email/webhook)
3. The MLRO instructs the relevant financial institution to freeze via their own systems
4. The freeze action is recorded in AMLKit's audit trail

### 2. "Cold Name Vulnerability" Is Misdiagnosed

The plan's central premise — that 99.8% of applicants return "Unavailable" — describes a different architecture (an API-dependent screening tool that can't screen when the upstream API is down). AMLKit's architecture is local-first: sanctions data is ingested and stored locally. The real vulnerability is **stale or unloaded data**, not API unavailability. The fix is simpler and faster than proposed.

### 3. External Dependencies Are Underspecified

| Dependency | Availability | Risk |
|---|---|---|
| **Sumsub** ($299/mo) | Commercial API, well-documented | LOW — standard integration |
| **Open Exchange Rates** ($12/mo) | REST API, documented | LOW |
| **UAE Pass / EID verification** | Government API, requires licensing | HIGH — access process unclear |
| **DED/Free Zone registries** | No standard API | HIGH — may require manual workflow |
| **FIU IEMS** | Government system, no public API docs | HIGH — cannot plan without specs |
| **goAML B2B submission** | Portal-based, API availability unknown | MEDIUM |
| **OpenCorporates** ($2,850/yr) | REST API, documented | LOW — Phase 2 item |

### 4. The 12-Week Timeline Is Aggressive

Given that ~40% of the proposed work already exists in the codebase, the true new-work scope is approximately 6–8 weeks of development for one senior engineer. However:
- External API integrations (UAE Pass, DED, IEMS) have **unknown lead times** for access
- goAML XSD validation requires obtaining the official schema from the FIU
- Testing against real UAE sanctions data requires a production-representative dataset

### 5. Gaming Operator Scope Is Entirely New

"Commercial gaming operators" is a new DNFBP category under CR 134/2025. AMLKit has no gaming-specific logic:
- No AED 11,000 threshold
- No gaming-sector risk scoring
- No gaming-specific report type
- The `sector` list in `ruleset.yaml` doesn't include gaming

This is genuine net-new work — not a retrofit but an extension.

### 6. Sumsub as Mandatory Aggregator Is Debatable

The plan recommends Sumsub as mandatory for Phase 1. AMLKit already ingests EOCN and UN lists directly from primary sources, which is actually **more defensible** than relying on a third-party aggregator — the regulator expects you to screen against the official list, and a primary-source adapter proves you did. Sumsub adds value for:
- Biometric verification (not currently in scope)
- Ongoing monitoring (AMLKit already does this via `rescreen_all`)
- Additional list coverage (already covered by 6 ingest adapters)

**Recommendation:** Sumsub should be optional, not mandatory. Keep primary-source ingestion as the foundation; add Sumsub as a supplementary layer if biometric verification is needed.

---

## Adjusted Implementation Plan

### Revised Phase 1: Data Integrity & Freeze Workflow (Weeks 1–3)

| # | Task | Effort | Builds On |
|---|---|---|---|
| 1.1 | Pre-screening data-integrity guard (block onboarding if mandatory datasets empty/stale) | 2–3 days | `ingest/loader.py:staleness_report()` |
| 1.2 | Freeze obligation table + SLA deadline tracking | 3–4 days | New schema |
| 1.3 | MLRO notification on sanctions match (email webhook) | 2–3 days | `mail.py` |
| 1.4 | Auto-draft FFR on confirmed match | 2–3 days | `reporting/goaml.py` |
| 1.5 | Versioned REST API layer (`/v1/screenings/check`) | 2–3 days | `match/engine.py:screen()` |

### Revised Phase 2: Sector-Specific Thresholds & Identity (Weeks 4–6)

| # | Task | Effort | Builds On |
|---|---|---|---|
| 2.1 | Sector-aware transaction thresholds (gaming AED 11K, wire/VA AED 3.5K) | 3–4 days | `screening/kyt.py` |
| 2.2 | Gaming operator sector in risk model | 1–2 days | `risk/ruleset.yaml` |
| 2.3 | Collision-count "Rarity Gate" with EID disambiguation | 3–4 days | `cases/ocr.py` |
| 2.4 | Currency conversion via Open Exchange Rates API | 2–3 days | `cases/manager.py:record_transaction()` |
| 2.5 | Adverse media keyword refinement (optional — current set is already strong) | 1–2 days | `screening/adverse_media.py` |

### Revised Phase 3: Corporate Transparency (Weeks 7–9)

| # | Task | Effort | Builds On |
|---|---|---|---|
| 3.1 | Recursive UBO traversal (multi-layer holding structures) | 5–7 days | `cases/manager.py`, `db.py` |
| 3.2 | 15-working-day structure-update countdown timer | 2–3 days | New compliance-deadline system |
| 3.3 | UBO diagram update for recursive structures | 2–3 days | `cases/diagram.py` |
| 3.4 | EWRA alignment — PF risk factors in ruleset.yaml | 1–2 days | `risk/ruleset.yaml` |

### Revised Phase 4: Audit, Reporting & Compliance Hardening (Weeks 10–12)

| # | Task | Effort | Builds On |
|---|---|---|---|
| 4.1 | Role-based UI partitioning (analyst vs. officer views) | 5–7 days | `api/app.py`, templates |
| 4.2 | Retention enforcement job (5-year automated purge) | 1–2 days | `customers.retention_until` |
| 4.3 | goAML XSD validation (requires obtaining official schema) | 2–3 days | `reporting/goaml.py` |
| 4.4 | Filing deadline SLA dashboard | 2–3 days | Freeze obligation table from Phase 1 |
| 4.5 | goAML B2B submission (if API available) | 3–5 days | External dependency |

### Deferred (External Dependencies)

| # | Task | Blocker |
|---|---|---|
| D.1 | UAE Pass / EID verification API integration | Government licensing process |
| D.2 | DED/Free Zone registry integration | No standard API available |
| D.3 | FIU IEMS integration | No public API documentation |
| D.4 | Sumsub aggregator integration | Commercial decision pending |
| D.5 | OpenCorporates KYB integration | Phase 2 budget item |

---

## Validation Checklist (Adjusted)

- [ ] **Data Integrity:** Mandatory dataset staleness guard blocks onboarding when lists are empty or stale
- [ ] **Sanctions Pipeline:** EOCN + UNSC ingestion confirmed operational (already working)
- [ ] **Arabic Matching:** Transliteration + fuzzy matching verified against golden set (already working)
- [ ] **PF Classification:** Proliferation vs. terrorism distinction validated (already working)
- [ ] **Freeze Workflow:** Obligation record created on match, MLRO notified, FFR auto-drafted
- [ ] **Sector Thresholds:** Gaming (AED 11K), Real Estate/PM (AED 55K), Wire/VA (AED 3.5K) all enforced
- [ ] **UBO Engine:** Recursive traversal through holding structures, 25% threshold with fallback
- [ ] **goAML Reports:** STR, SAR, FFR, PNMR, REAR validated against official XSD
- [ ] **Audit Trail:** Append-only, 5-year retention enforced, partitioned triage active
- [ ] **Risk Model:** EWRA-aligned with PF factors, gaming sector scored

---

## Summary of Findings

| Plan Item | Status | True Effort |
|---|---|---|
| Cold-start hard-gating | Misdiagnosed — fix is simpler | 2–3 days |
| TFS freeze workflow | Partially exists — needs freeze obligation tracking | 5–7 days |
| Arabic transliteration | **Already exists** — 453-line module | 0 days |
| Fuzzy matching (Jaro-Winkler) | **Already exists** — rapidfuzz integration | 0 days |
| Emirates ID scanning | **Already exists** — MRZ extraction | 0 days |
| Rarity Gate (collision disambiguation) | New work | 3–4 days |
| Predicate crime filter | **Already exists** — keyword + exculpatory filtering | 1–2 days (refinement) |
| 25% UBO threshold | **Already exists** — hardcoded constant | 0 days |
| Recursive UBO traversal | New work (current model is flat) | 5–7 days |
| 15-day UBO update timer | New work | 2–3 days |
| goAML XML export | **Already exists** — all 8 report types | 0 days |
| goAML XSD validation | New work | 2–3 days |
| PF classification | **Already exists** — standalone module | 0 days |
| Transaction monitoring (AED 55K) | **Already exists** | 0 days |
| Gaming threshold (AED 11K) | New work | 1–2 days |
| Wire/VA threshold (AED 3.5K) | New work | 1–2 days |
| Currency conversion API | New work | 2–3 days |
| Role-based triage UI | New work | 5–7 days |
| IEMS integration | **Blocked** — no API docs | Unknown |
| Sumsub integration | Optional | 5–7 days if pursued |

**Total estimated new work:** ~40–55 development days (8–11 weeks for one engineer)
**Already-built capabilities reused:** ~40% of the plan's scope

The plan is feasible with the adjustments above. The primary risks are external dependencies (UAE Pass, IEMS, DED registries) whose timelines are outside our control.
