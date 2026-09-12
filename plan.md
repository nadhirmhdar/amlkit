# AMLKit UAE 2026 Regulatory Retrofit: Feasibility Analysis & Implementation Plan

**Date:** 2026-09-12
**Status:** Analysis Complete — Awaiting Approval
**Scope:** Retrofit AMLKit for UAE FDL No. (10) of 2025 & Cabinet Resolution No. (134) of 2025

---

## Executive Summary

The proposed 12-week retrofit plan is **largely feasible** given the existing codebase. AMLKit already carries significant UAE-specific infrastructure — EOCN ingestion, Arabic name handling, PF classification, goAML serialization, UBO tracking at 25%, and AED-denominated transaction monitoring. The plan overstates several gaps (describing capabilities that already exist as new work) and understates a few real structural challenges. This document maps each proposed deliverable to the current codebase, flags true gaps, raises concerns, and proposes an adjusted implementation approach.

**Key finding:** ~40-45% of the proposed scope already exists. The proposed SQL migrations target PostgreSQL but AMLKit runs SQLite by design. Several claimed gaps (Arabic matching, PF classification, goAML export) are already shipped features.

---

## 1. Regulatory Context & System Gap Analysis Accuracy

| Claimed Gap | Actual Status | Verdict |
|---|---|---|
| Gaming operators not scoped | Correct — no gaming sector in `ruleset.yaml`, no AED 11K threshold | **TRUE GAP** |
| Screening allows "Unavailable" pass | **Wrong** — `screen()` returns `ScreeningResult(hits=[], clear=True)` meaning "screened, no matches." Not "data unavailable." | **MISDIAGNOSIS** |
| Standard ownership tracking | Partially wrong — `UBO_THRESHOLD_PCT = 25.0` in `cases/manager.py`; `ubo_links` table has `ownership_pct`, `control_type`, `is_ubo` | **PARTIAL** |
| Internal logs only | Wrong — `reporting/goaml.py` serializes STR, SAR, PNMR, FFR, HRCT, HRCA, DPMSR, REAR to goAML XML | **WRONG** |
| Exact token binding / no Arabic | Wrong — `names/arabic.py` (453 lines) does full Arabic transliteration; `scorer.py` uses `rapidfuzz.JaroWinkler` | **WRONG** |
| No PF module | Wrong — `screening/pf.py` classifies UNSCR 1718/1737/2231 (PF) vs 1267/1988/1373 (CT) | **WRONG** |

---

## 2. SQL Migrations — MAJOR ARCHITECTURAL MISMATCH

**Problem:** The proposed DDL is PostgreSQL (UUIDs, JSONB, PL/pgSQL triggers, RLS, table partitioning). AMLKit uses SQLite deliberately — single-file portable database for DNFBP compliance officers. The `db.py` docstring explicitly states this is a design choice, not a limitation.

### Translation Required

| Proposed (PostgreSQL) | Required (SQLite) | Notes |
|---|---|---|
| `UUID PRIMARY KEY` | `INTEGER PRIMARY KEY` | SQLite autoincrement; existing pattern |
| `JSONB` columns | `TEXT` (JSON as string) | Already the pattern in `db.py` for `topics`, `programs`, `detail` |
| `PARTITION BY RANGE` | Not available; indexed `created_at` | Quarterly archival via application logic |
| PL/pgSQL triggers | SQLite triggers | `db.py` already has append-only audit triggers |
| Row-Level Security (RLS) | Application-level access control | Route guards in `api/app.py` checking `operator.role` |
| `CHECK (emirates_id ~ '^784-...')` | Application-level regex | SQLite CHECK can't use regex |

### UBO Schema: Extend, Don't Replace

The proposed `ubo_corporate_entities` + `ubo_ownership_layers` tables redesign the existing `ubo_links` table. **Recommendation:** Extend `ubo_links` with `parent_ubo_id INTEGER` and `is_nominee INTEGER DEFAULT 0` columns via `_MIGRATIONS` in `db.py`. This preserves backward compatibility with all existing UBO queries, screening logic, and diagram generation.

### Audit Log: Don't Duplicate

The proposed `screening_audit_logs` table duplicates `audit_log` which already exists with append-only triggers, storing `actor`, `action`, `entity_type`, `entity_id`, `detail` (JSON), `org_id`, `created_at`. Add `rationale TEXT` and `metadata TEXT` columns to the existing table rather than creating a parallel system.

### New Tables Needed (SQLite DDL)

```sql
-- TFS freeze obligation tracking
CREATE TABLE IF NOT EXISTS tfs_freeze_obligations (
    id            INTEGER PRIMARY KEY,
    org_id        INTEGER NOT NULL REFERENCES organizations(id),
    customer_id   INTEGER NOT NULL REFERENCES customers(id),
    alert_id      INTEGER REFERENCES alerts(id),
    match_type    TEXT NOT NULL,       -- confirmed | partial_pnmr
    sla_deadline  TEXT NOT NULL,       -- ISO timestamp, created_at + 24h
    executed_at   TEXT,
    notified_at   TEXT,
    created_at    TEXT NOT NULL
);

-- goAML report submission queue
CREATE TABLE IF NOT EXISTS goaml_report_queue (
    id                INTEGER PRIMARY KEY,
    org_id            INTEGER NOT NULL REFERENCES organizations(id),
    report_type       TEXT NOT NULL,    -- STR | SAR | FFR | PNMR | REAR | DTR
    customer_id       INTEGER REFERENCES customers(id),
    payload_xml       TEXT,
    submission_status TEXT NOT NULL DEFAULT 'draft',  -- draft | ready | submitted | failed
    filing_deadline   TEXT,
    submitted_at      TEXT,
    created_at        TEXT NOT NULL
);

-- Compliance deadlines (UBO 15-day timer, FFR 5-day SLA)
CREATE TABLE IF NOT EXISTS compliance_deadlines (
    id            INTEGER PRIMARY KEY,
    org_id        INTEGER NOT NULL REFERENCES organizations(id),
    deadline_type TEXT NOT NULL,       -- ubo_update | ffr_filing | retention_expiry
    entity_type   TEXT NOT NULL,       -- customer | ubo | report
    entity_id     INTEGER NOT NULL,
    deadline_at   TEXT NOT NULL,
    completed_at  TEXT,
    created_at    TEXT NOT NULL
);
```

---

## 3. Codebase Capability Baseline

| Capability | Current State | Key Files |
|---|---|---|
| **EOCN Local Terrorist List** | Direct ingestion from UAEIEC, Excel parser, delisting-aware | `ingest/eocn.py` (700+ lines) |
| **UN/OFAC/EU/UK sanctions** | Bulk-loaded, refresh-on-schedule | `ingest/un.py`, `ingest/ofac.py`, `ingest/eu.py`, `ingest/uk.py` |
| **Arabic name matching** | Dual-script processing, token stripping, Arabic-Latin candidate comparison. Remaining need: only lightweight orthographic character folding for exact diacritic consistency (e.g. mapping [أإآٱ] -> ا and ة -> ه) | `names/arabic.py` (453 lines) |
| **Fuzzy scoring** | Jaro-Winkler with family-name weighting, OpenSanctions logic-v2 weights | `match/scorer.py` (uses `rapidfuzz`) |
| **PF classification** | PF separated from generic sanctions. Entities categorized by designating programmes (UNSCR 1718 DPRK, UNSCR 2231/1737 Iran, OFAC NPWMD), generating regime-specific obligations. No new classifier needed; list ingestion preserves programme metadata. | `screening/pf.py` |
| **goAML XML export** | STR, SAR, PNMR, FFR, HRCT, HRCA, DPMSR, REAR | `reporting/goaml.py` |
| **UBO tracking** | 25% threshold, ownership diagrams (Graphviz SVG) | `cases/manager.py`, `cases/diagram.py` |
| **Transaction monitoring** | AED 55,000 large-cash, structuring detection, velocity, high-risk country | `screening/kyt.py` |
| **Risk scoring** | YAML-driven, versioned, EDD triggers, review cycles | `risk/model.py`, `risk/ruleset.yaml` |
| **Adverse media** | GDELT-based, predicate-crime keyword filtering | `screening/adverse_media.py` |
| **Audit trail** | Append-only by DB trigger, org-scoped, 5-year retention column | `db.py` |
| **Tenant isolation** | org_id mandatory on every query, session-scoped | `queries.py`, `api/deps.py` |
| **Emirates ID scanning** | MRZ extraction from passport/EID images | `cases/ocr.py`, `api/mobile.py` |
| **Four-eyes review** | Dual-approval for sanctions/PF dispositions; structured reason codes | `cases/review.py` |
| **Operator roles** | `role` field (officer/mlro) exists but not enforced at route level | `db.py` operators table |

---

## 4. Phase-by-Phase Feasibility Assessment

### Phase 1: Critical TFS Baseline (Weeks 1–3)

#### 1.1 Hard-Gate Onboarding — CONCERN: MISDIAGNOSIS

**Plan claim:** "Prefetch/Background sweeps; allow 'Unavailable' status for cold names" must be replaced with hard-gate decision tree.

**Codebase reality:** This is **not how AMLKit works**. The screening engine (`match/engine.py:screen()`) operates against a locally-ingested entity database, not a live HTTP API. When `_candidates()` returns no matches, the result is `ScreeningResult(hits=[], clear=True)` — meaning "screened against all loaded lists, no matches found." This is a genuine clear result, not an "unavailable" artifact of missing data.

The actual risk is **stale or empty sanctions data**. AMLKit already has a staleness mechanism:
- `ingest/loader.py` computes `staleness_report()` — datasets overdue based on `max_age_hours`
- `datasets.last_refresh` and `datasets.entity_count` track currency
- `datasets.is_mandatory` flags lists that must be present

**What's actually needed:** A pre-screening check: if any `is_mandatory` dataset has `entity_count = 0` or `last_refresh` is NULL, block onboarding. NOT a 24-hour retry timer — trigger a refresh immediately instead. **Effort: 2–3 days.**

#### 1.2 Real-Time TFS & 24h Freeze — PARTIALLY EXISTS

**Codebase reality:**
- `rescreen_all()` re-screens the entire customer book after each list refresh
- Onboarding blocks on sanctions hits (`OnboardingResult.blocked = True`) with obligation text from `pf.py:obligation_note()`
- goAML FFR export already exists in `reporting/goaml.py`

**What's missing:**
- No automated freeze workflow (SLA timer, notification chain)
- No `accounts` or `ledger` table — AMLKit is a screening tool for DNFBPs, not a banking system
- No automated FFR generation triggered by a match — currently manual

**Concern:** The plan's `POST /v1/accounts/freeze/{acc_id}` assumes AMLKit manages financial accounts. It does not. Freeze = compliance obligation record + MLRO notification + audit entry, not a ledger operation. **Effort: 5–7 days** for `tfs_freeze_obligations` table + MLRO email + auto-draft FFR.

#### 1.3 Screening Check API — ALREADY EXISTS

AMLKit already has `POST /screen` (web), `POST /customers/screen/{customer_id}` (mobile), and `match/engine.py:screen()`. Wrapping in a versioned REST endpoint is **1–2 days**.

---

### Phase 2: Regional Localization (Weeks 4–6)

#### 2.1 Arabic Transliteration & Multi-Script Matching — ALREADY EXISTS

**Plan claim:** "Multi-script Arabic transliteration; fuzzy/inverted flow; EID primary disambiguation."

**Codebase reality:** The matching pipeline already handles dual-script processing, token stripping, and Arabic-Latin candidate comparisons:
- `names/arabic.py` (453 lines): diacritic removal, hamza unification ([أإآٱ] -> ا, ة -> ه already mapped in `_ARABIC_LETTER_MAP`), Buckwalter transliteration, Latin-to-canonical mapping with 100+ variant entries
- `match/scorer.py`: uses `rapidfuzz.distance.JaroWinkler` with token sorting (order-independent — handles inverted name flows)
- `blocking_keys()` collapses "Mohammed"/"Muhammad"/"Mohd" onto the same candidate set
- Family-name weighting (`FAMILY_NAME_WEIGHT = 1.3`) addresses the "Mohammed is near-noise" problem

**Remaining need:** Only lightweight orthographic character folding for exact diacritic consistency — the core mappings already exist in `_ARABIC_LETTER_MAP`. The plan's `POST /v2/screening/match_config` for "enabling" Arabic transliteration is unnecessary — it's the default behavior.

**Effort: 0–1 days** (minor refinement at most).

#### 2.2 Emirates ID Disambiguation ("Rarity Gate") — NEW WORK

- EID scanning exists (`cases/ocr.py`, `api/mobile.py:api_scan_emirates_id()`)
- No collision-count logic exists today
- Collision threshold of 25 is arbitrary — needs empirical calibration against real UAE name distributions

**Effort: 3–4 days** — collision counting on `canonical_key`, configurable threshold, EID-based disambiguation.

#### 2.3 Predicate Crime Filter — ALREADY EXISTS

`screening/adverse_media.py` already implements all three proposed layers:
- GDELT returns article metadata, not sentiment — no "tone" to discard
- `CRIME_KEYWORDS` mapped to EOCN/FATF-aligned predicate offences
- `EXCULPATORY_TERMS` for down-ranking ("acquitted", "cleared", "dismissed")

**Effort: 0–1 days** (keyword list refinement only).

---

### Phase 3: Corporate & Thresholds (Weeks 7–9)

#### 3.1 Recursive UBO Engine — PARTIALLY EXISTS

**Codebase reality:**
- `ubo_links` table with `ownership_pct`, `control_type`, `is_ubo` — but flat model (customer -> UBOs), no graph traversal
- `UBO_THRESHOLD_PCT = 25.0` hardcoded in `cases/manager.py`
- `cases/diagram.py` generates ownership SVG diagrams via Graphviz

**What's missing:**
- No recursive traversal through intermediate holding companies
- No nominee exclusion (`is_nominee` field)
- No 15-working-day countdown timer for structure updates
- No DED/Free Zone registry integration (external dependency — no standard API)

**Approach:** Extend `ubo_links` with `parent_ubo_id` and `is_nominee` via `_MIGRATIONS` (preserves backward compatibility). Recursive traversal in `cases/manager.py`. UAE holiday calendar needed for working-day computation.

**Effort: 7–10 days** for recursive engine + nominee logic + timer. External registry integration deferred.

#### 3.2 Threshold Rules Engine — PARTIALLY EXISTS

**Existing:** `LARGE_CASH_THRESHOLD_AED = 55_000.0` in `kyt.py` covers Real Estate and Precious Metals. Structuring, velocity, and high-risk country rules all work.

**Missing:**
- Gaming operator threshold (AED 11,000) — no gaming sector exists
- Sector-aware threshold routing — `evaluate_transaction()` applies same threshold to all sectors
- Wire/VA AED 3,500 CDD scrutiny trigger
- Currency conversion API — `amount_aed` column exists but caller computes the conversion manually

**Effort: 5–7 days** — sector-aware thresholds in `kyt.py`, gaming sector in `ruleset.yaml`, Open Exchange Rates integration via `httpx`.

---

### Phase 4: PF & Automation (Weeks 10–12)

#### 4.1 Proliferation Financing Module — ALREADY EXISTS

**Codebase reality:** PF is already separated from generic sanctions in `screening/pf.py`. Entities are categorized by designating programmes (UNSCR 1718 DPRK, UNSCR 2231/1737 Iran, OFAC NPWMD), generating regime-specific obligations. No new classifier or separate PF list is required; list ingestion already preserves programme metadata.

- `classify_programs()` distinguishes proliferation from terrorism
- `obligation_note()` returns regime-specific legal obligations
- Hit objects carry `.is_proliferation`, `.is_terrorism`, `.categories` properties

**Effort: 0 days** for classification. **1–2 days** for EWRA-specific PF risk factors in `ruleset.yaml`.

#### 4.2 Partitioned RBAC (Anti-Tipping Off) — NEW WORK

**Codebase reality:**
- Operators table has `role` field (officer/mlro) but routes don't restrict access
- Four-eyes review exists for sanctions dispositions (`cases/review.py`)
- Audit trail is append-only with triggers preventing UPDATE/DELETE

**What's missing:**
- Role-based view separation (RM vs. compliance officer) — must be application-level route guards since SQLite has no RLS
- Visibility control on `goaml_report_queue`, audit `rationale`, TFS freeze rationale
- IEMS integration — **external dependency, no public API docs**

**Effort: 5–7 days** for route-level RBAC. IEMS deferred until API specs obtained.

#### 4.3 goAML B2B Adapter — LARGELY EXISTS

`reporting/goaml.py` already serializes all 8 report types (STR, SAR, PNMR, FFR, HRCT, HRCA, DPMSR, REAR). Web UI has report creation and submission workflows.

**Missing:** DTR (Dealer Transaction Report) variant, XSD validation against official schema, automated FFR on match, B2B API submission to portal.

**Effort: 2–3 days** XSD validation + DTR variant. **3–5 days** B2B submission (if portal provides API).

#### 4.4 5-Year Retention Enforcement

`RETENTION_YEARS = 5` and `retention_until` column exist. Need automated purge job triggered by relationship termination + 5-year offset.

**Effort: 1–2 days.**

---

## 5. API Specifications Assessment

### Proposed Endpoints vs. Codebase Reality

| Proposed Endpoint | Exists? | Assessment |
|---|---|---|
| `POST /v1/screenings/check` | Partially — `screen()` function + web/mobile routes exist | Wrap in versioned REST route. `emirates_id` and `transliteration_path` params unnecessary — Arabic is always-on. **1–2 days.** |
| `POST /v1/accounts/freeze/{acc_id}` | No — and architecturally wrong | AMLKit has no accounts/ledger. Reframe as `POST /v1/freeze-obligations` creating a compliance record. **Part of TFS work.** |
| `PUT /v1/entities/{id}/ubo` | Partially — `add_ubo()` exists | Extend with `is_nominee` flag and statutory clock. **Part of UBO work.** |

### API Payload Adjustments

The proposed screening payload includes `"enable_inverted_flow": true` and `"transliteration_path": "Arabic_to_Latin"` — both are unnecessary since the screening engine handles these by default. The `fuzziness_score: 0.85` matches the existing `DEFAULT_THRESHOLD = 0.85` in `scorer.py` and is already configurable per-org via `org_settings.alert_threshold`.

---

## 6. Auditability & Security Assessment

### Existing Controls

- Append-only `audit_log` with SQLite triggers preventing UPDATE/DELETE
- Four-eyes review for sanctions/PF dispositions (`cases/review.py`) with structured reason codes
- `org_id` tenant isolation on every table
- 5-year `retention_until` column on customers
- Explicit "freeze without delay and do not tip off" messaging in UI

### Article 29 Anti-Tipping Off

The proposed PostgreSQL RLS approach cannot be implemented in SQLite. Must be application-level:
- Route guards in `api/app.py` checking `operator.role` (officer vs. mlro)
- `goaml_report_queue`, audit `rationale`, and freeze details hidden from non-compliance roles
- The `operators.role` field already exists — enforcement logic is what's missing

### Data Retention

| Entity Type | Retention | Trigger | Status |
|---|---|---|---|
| Customer Record | 5 Years | Relationship termination | Column exists (`retention_until`), no purge job |
| Transaction Data | 5 Years | Account closing | Column needed |
| Audit/Investigation | 5 Years | Conclusion of proceeding | Append-only, no deletion possible by design |

---

## 7. Concerns & Risks

### 1. PostgreSQL DDL Won't Work
All proposed SQL must be rewritten for SQLite. The migration pattern is additive columns via `_MIGRATIONS` list in `db.py`, not standalone DDL scripts. UUIDs, JSONB, RLS, and partitioning are not available.

### 2. AMLKit Is Not a Banking System
The plan assumes AMLKit manages financial accounts and ledgers. It is a compliance screening tool for DNFBPs. Freeze workflow = obligation record + MLRO notification + audit entry, not a ledger lock.

### 3. "Cold Name Vulnerability" Is Misdiagnosed
AMLKit screens locally against ingested data. "Unavailable" is not a status it returns. The real risk is stale/empty data — a simpler fix than the proposed 24h retry architecture.

### 4. External Dependencies Have Unknown Timelines

| Dependency | Risk | Notes |
|---|---|---|
| UAE Pass / EID verification | HIGH | Government licensing required |
| DED/Free Zone registries | HIGH | No standard API |
| FIU IEMS | HIGH | No public API documentation |
| goAML B2B submission | MEDIUM | Portal-based, API unclear |
| Open Exchange Rates ($12/mo) | LOW | REST API, documented |
| Sumsub ($299/mo) | LOW | Optional — primary-source ingestion is more defensible |
| OpenCorporates ($2,850/yr) | LOW | Phase 2 item |

### 5. Gaming Operator Scope Is Entirely New
No gaming sector in `ruleset.yaml`, no AED 11K threshold, no gaming-specific report type. Genuine net-new work.

### 6. Sumsub as Mandatory Is Debatable
AMLKit ingests EOCN and UN lists from primary sources — more defensible than a third-party aggregator. Sumsub adds value for biometric verification (not in scope) but is not needed for list coverage (6 ingest adapters already work).

---

## 8. Adjusted Implementation Plan

### Phase 1: Data Integrity & Freeze Workflow (Weeks 1–3)

| # | Task | Effort | Builds On |
|---|---|---|---|
| 1.1 | Pre-screening data-integrity guard (block onboarding if mandatory datasets empty/stale) | 2–3 days | `ingest/loader.py:staleness_report()` |
| 1.2 | `tfs_freeze_obligations` table + SLA deadline tracking | 3–4 days | New schema in `db.py:_MIGRATIONS` |
| 1.3 | MLRO notification on sanctions match (email webhook) | 2–3 days | `mail.py` |
| 1.4 | Auto-draft FFR on confirmed match | 2–3 days | `reporting/goaml.py` |
| 1.5 | Versioned REST API layer (`/v1/screenings/check`) | 2–3 days | `match/engine.py:screen()` |

### Phase 2: Sector-Specific Thresholds & Identity (Weeks 4–6)

| # | Task | Effort | Builds On |
|---|---|---|---|
| 2.1 | Sector-aware transaction thresholds (gaming AED 11K, wire/VA AED 3.5K) | 3–4 days | `screening/kyt.py` |
| 2.2 | Gaming operator sector in risk model | 1–2 days | `risk/ruleset.yaml` |
| 2.3 | Collision-count "Rarity Gate" with EID disambiguation | 3–4 days | `cases/ocr.py` |
| 2.4 | Currency conversion via Open Exchange Rates API | 2–3 days | `cases/manager.py:record_transaction()` |
| 2.5 | DTR report type addition in goAML | 1 day | `reporting/goaml.py` |

### Phase 3: Corporate Transparency (Weeks 7–9)

| # | Task | Effort | Builds On |
|---|---|---|---|
| 3.1 | Recursive UBO traversal + nominee exclusion (`parent_ubo_id`, `is_nominee` on `ubo_links`) | 5–7 days | `cases/manager.py`, `db.py` |
| 3.2 | 15-working-day statutory countdown timer + UAE holiday calendar | 2–3 days | `compliance_deadlines` table |
| 3.3 | UBO diagram update for recursive structures | 2–3 days | `cases/diagram.py` |
| 3.4 | EWRA PF risk factors in ruleset | 1–2 days | `risk/ruleset.yaml` |

### Phase 4: Audit, Reporting & Compliance Hardening (Weeks 10–12)

| # | Task | Effort | Builds On |
|---|---|---|---|
| 4.1 | Role-based route guards (Article 29 anti-tipping-off) | 5–7 days | `api/app.py`, `operators.role` |
| 4.2 | `goaml_report_queue` table + submission status tracking | 2–3 days | New schema |
| 4.3 | goAML XSD validation (requires obtaining official schema) | 2–3 days | `reporting/goaml.py` |
| 4.4 | Retention enforcement job (5-year automated purge) | 1–2 days | `customers.retention_until` |
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

## 9. Validation Checklist

- [ ] **Data Integrity:** Mandatory dataset staleness guard blocks onboarding when lists are empty or stale
- [ ] **Sanctions Pipeline:** EOCN + UNSC ingestion confirmed operational (already working)
- [ ] **Arabic Matching:** Dual-script processing verified; orthographic folding complete (already working, minor refinement)
- [ ] **PF Classification:** Programme-based proliferation vs. terrorism classification validated (already working)
- [ ] **Freeze Workflow:** Obligation record created on match, MLRO notified, FFR auto-drafted
- [ ] **Sector Thresholds:** Gaming (AED 11K), Real Estate/PM (AED 55K), Wire/VA (AED 3.5K) all enforced
- [ ] **UBO Engine:** Recursive traversal through holding structures, nominee exclusion, 25% threshold with fallback
- [ ] **goAML Reports:** STR, SAR, FFR, PNMR, REAR, DTR validated against official XSD
- [ ] **Audit Trail:** Append-only, 5-year retention enforced, role-based access active
- [ ] **Risk Model:** EWRA-aligned with PF factors, gaming sector scored
- [ ] **SQL Migrations:** All new tables use SQLite-compatible DDL via `_MIGRATIONS` pattern

---

## 10. Summary of Findings

| Plan Item | Status | True Effort |
|---|---|---|
| Cold-start hard-gating | Misdiagnosed — fix is simpler (staleness guard) | 2–3 days |
| TFS freeze workflow | Partially exists — needs obligation tracking | 5–7 days |
| Arabic transliteration | **Already exists** — dual-script pipeline, minor folding refinement | 0–1 days |
| Fuzzy matching (Jaro-Winkler) | **Already exists** — rapidfuzz, token-sorted, order-independent | 0 days |
| Emirates ID scanning | **Already exists** — MRZ extraction | 0 days |
| Rarity Gate (collision disambiguation) | New work | 3–4 days |
| Predicate crime filter | **Already exists** — keyword + exculpatory filtering | 0–1 days |
| 25% UBO threshold | **Already exists** — hardcoded constant | 0 days |
| Recursive UBO traversal | New work (current model is flat) | 5–7 days |
| 15-day UBO update timer | New work | 2–3 days |
| goAML XML export | **Already exists** — 8 report types (missing DTR) | 1 day |
| goAML XSD validation | New work | 2–3 days |
| PF classification | **Already exists** — programme-based, no new classifier needed | 0 days |
| Transaction monitoring (AED 55K) | **Already exists** | 0 days |
| Gaming threshold (AED 11K) | New work | 1–2 days |
| Wire/VA threshold (AED 3.5K) | New work | 1–2 days |
| Currency conversion API | New work | 2–3 days |
| Role-based RBAC (Art. 29) | New work (role field exists, no enforcement) | 5–7 days |
| SQL migrations (PostgreSQL) | **Must be rewritten** for SQLite | Part of each task |
| IEMS integration | **Blocked** — no API docs | Unknown |
| Sumsub integration | Optional — primary sources more defensible | 5–7 days if pursued |

**Total estimated new work:** ~40–55 development days (8–11 weeks for one engineer)
**Already-built capabilities reused:** ~40-45% of the plan's scope

The plan is feasible with the adjustments above. The primary risks are external dependencies (UAE Pass, IEMS, DED registries) whose timelines are outside our control, and the PostgreSQL-to-SQLite DDL rewrite which affects every proposed migration script.
