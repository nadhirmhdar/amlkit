# AMLKit — Existing Capabilities Reference

Components that are fully built (100%) or near-complete (95%+), requiring no new development under the proposed UAE regulatory retrofit. This document covers the logic, function signatures, and regulatory alignment of each module.

---

## 1. Arabic Name Transliteration & Fuzzy Matching (100% Complete)

**Files:** `amlkit/names/arabic.py` (453 lines), `amlkit/match/scorer.py`

### What It Does

Handles the core challenge of UAE screening: matching Arabic-origin names that arrive in three inconsistent forms (Arabic script with/without diacritics, Latin transliteration variants, abbreviated Latin forms like "Mohd").

### Key Functions

**`normalize_arabic(text: str) -> str`**
Collapses Arabic orthographic variation to a canonical form. Removes diacritics (harakat), tatweel (kashida), unifies hamza-carrying letters (alef madda, alef hamza above/below, alef wasla all map to plain alef), and strips the definite article "ال" when prefixed to a name token.

**`transliterate_arabic(token: str) -> str`**
Romanises a single Arabic-script token. Resolves known Arabic spellings directly via the `ARABIC_FORMS` dictionary (38 common names like محمد → "mohammed", احمد → "ahmed", عبدالله → "abdullah"). Unknown tokens fall through to consonant-based transliteration where semivowels (waw, ya) are resolved positionally — consonant word-initially, long vowel elsewhere.

**`canonical_token(token: str) -> str`**
Maps a single Latin name token to its canonical spelling using a three-step resolution:
1. Exact hit in the `VARIANT_TABLE` (e.g., "mohd" → "mohammed", "khalid"/"khaled"/"kalid" all → "khalid")
2. Skeleton hit against a known canonical name (transliterated Arabic "mhmd" → skeleton → "mohammed")
3. Bare consonant skeleton for everything else

The `VARIANT_TABLE` contains 45+ canonical name groups covering the most common UAE/GCC names with all known spelling variants. This is where "Mohd" matches "Muhammad" — a 6-character Levenshtein distance that no edit-distance threshold can catch without drowning in false positives.

**`consonant_skeleton(token: str) -> str`**
Reduces a token to a vowel-light consonant skeleton. Handles digraph reduction (sh→š, kh→ḫ, gh→ġ), drops medial vowels and medial 'w' (because Arabic waw is a consonant initially but a long vowel elsewhere), collapses doubled consonants, and preserves the nisba suffix (-i/-y) as an explicit marker to prevent "Mansour" from matching "Mansoori".

**`tokenize(name: str) -> tuple[list[str], list[str]]`**
Splits a full name into content tokens and particle tokens ("bin", "bint", "al", "el", "abu", etc.). Rejoins "Abdul"+"Rahman" theophoric compounds before canonicalisation. Particles are kept rather than discarded — weak evidence individually but useful as a tie-breaker.

**`canonical_key(name: str) -> str`**
Order-independent fingerprint of a name. Sorts canonical tokens so "Rashid Mohammed" matches "Mohammed Rashid" — Arabic name chains routinely arrive in different orders across documents.

**`blocking_keys(name: str) -> set[str]`**
Generates cheap keys for candidate retrieval. Returns canonical tokens plus 4-character prefixes for tokens ≥ 4 characters. Deliberately generous — recall at this stage bounds the recall of the entire system.

### Scoring: `scorer.py`

**`name_score(query: str, candidate: str) -> tuple[float, dict]`**
Compares two full names using canonical tokens and Jaro-Winkler similarity (via `rapidfuzz`). Combines recall (how much of the query appears in the candidate) with precision (how much of the candidate is accounted for), weighted toward recall via `PRECISION_FLOOR = 0.60`. The precision weight (0.40) was calibrated to prevent a single-token query like "Mohammed" from clearing the 0.85 threshold against two-token listed names.

**`score_entity(...) -> ScoreResult`**
Scores a query against all aliases of one candidate entity, taking the best match. Applies feature adjustments: exact identifier match overrides name similarity (`W_IDENTIFIER_MATCH = 0.95`), country mismatch (-0.20), DOB year mismatch (-0.15), DOB day mismatch (-0.25), gender mismatch (-0.20). Weights follow OpenSanctions logic-v2 model. Family name carries 1.3x weight because "Mohammed" is near-noise in the UAE market while "Al Maktoum" is not.

**`DEFAULT_THRESHOLD = 0.85`** — calibrated against a golden set and false-positive suite in `tests/test_matching.py`.

### Why No New Work Is Needed

The proposed retrofit describes "Inverted name flow" and "Jaro-Winkler fuzzy matching" as new deliverables. Both already exist: `canonical_key()` produces order-independent tokens, `scorer.py` uses token-sorted Jaro-Winkler. Arabic transliteration is not a Phase 2 deliverable — it has been the foundation of the screening engine since the start.

---

## 2. Proliferation Financing Classification (100% Complete)

**File:** `amlkit/screening/pf.py`

### What It Does

Classifies sanctions programme identifiers into "proliferation" (PF) vs "terrorism" (CT) categories. Federal Decree-Law No. 10 of 2025 elevated PF from a subset of AML/CFT to a standalone criminal offence with its own chapter — folding PF hits into generic sanctions alerts understates that.

### Key Constants

**`PF_PROGRAM_PREFIXES`**: UN Security Council non-proliferation regimes
- `UN-SC1718` — DPRK: nuclear, ballistic missile, WMD programmes
- `UN-SC1737` — Iran: nuclear programme (superseded by 2231 but still carried)
- `UN-SC2231` — Iran: JCPOA implementation, successor to 1737

**`PF_OFAC_CODES`**: OFAC WMD proliferation programmes
- `NPWMD`, `DPRK`, `DPRK2`, `DPRK3`, `DPRK4`, `NPWMD-EO13382`, `IFSR`, `IRAN-TRA`

**`CT_PROGRAM_PREFIXES`**: Counter-terrorism regimes
- `UN-SCISIL` — ISIL (Da'esh) & Al-Qaida, res. 1267/1989/2253
- `UN-SC1988` — Taliban
- `AE-UNSC1373` — UAE Local Terrorist List, res. 1373 basis

### Key Functions

**`classify_programs(programs: list[str] | None) -> set[str]`**
Maps programme identifiers to `{"proliferation"}`, `{"terrorism"}`, or empty set (country/conflict regime — still a sanctions match, but not PF or CT). An unrecognised programme is treated as neither rather than defaulting into one.

**`is_proliferation(programs) -> bool`** / **`is_terrorism(programs) -> bool`**
Convenience wrappers around `classify_programs()`.

**`obligation_note(categories: set[str]) -> str`**
Plain-language statement for the alert record:
- PF → "PROLIFERATION FINANCING match. Standalone offence under Federal Decree-Law No. 10 of 2025. Freeze without delay…"
- CT → "TERRORISM FINANCING match. Freeze without delay…"
- Other → "SANCTIONS match. Freeze without delay…"

### Integration

`Hit.categories` property on every screening result calls `classify_programs()`. `Hit.is_proliferation` and `Hit.is_terrorism` are derived properties. `Hit.obligation` generates the plain-language note. The classification is automatic and immediate on every screening hit — no new classifier needed.

---

## 3. Sanctions List Ingestion — EOCN & International Sources (100% Complete)

**Files:** `amlkit/ingest/eocn.py` (700+ lines), `amlkit/ingest/un.py`, `amlkit/ingest/ofac.py`, `amlkit/ingest/eu.py`, `amlkit/ingest/uk.py`, `amlkit/ingest/cia.py`, `amlkit/ingest/fatf.py`, `amlkit/ingest/loader.py`, `amlkit/ingest/base.py`

### What It Does

Bulk-loads sanctions, PEP, and terrorism designation lists from primary sources into AMLKit's local SQLite database. Every screening check runs locally against this pre-ingested data — AMLKit is an offline-first, local-first screening engine with no per-screening API calls.

### EOCN Adapter (`eocn.py`)

Ingests the UAE Local Terrorist List directly from the Executive Office for Control & Non-proliferation (`uaeiec.gov.ae`). Parses the Excel workbook (not PDF), handles three listing sheets (individuals, groups/organisations, legal entities) and explicitly skips two delisting sheets — identified structurally by the presence of a "قرار رفع الإدراج" (delisting resolution) column rather than by sheet name, so a renamed tab doesn't silently turn delisted people back into screening targets. Every entry is emitted under programme `AE-UNSC1373`. Licensed for commercial use (primary government source, no third-party licence restriction).

### Loader (`loader.py`)

**`load(conn, adapter, actor) -> LoadResult`**
Core loading function. Fetches, parses, and stores one dataset. Loading is transactional (all-or-nothing) and replace-on-refresh: a delisted person must actually disappear. Entities with stable `source_id` are updated in place (preserving alert references), while new entities are inserted and removed entities are cascade-deleted. Refuses to clear existing data when zero entities parse (a safeguard against silently emptying the screening database).

**`staleness_report(conn) -> list[dict]`**
Returns hours since each dataset was last refreshed, with a `breach` flag on any mandatory dataset past 24 hours. This is the compliance control that satisfies EOCN's 24-hour list update requirement.

### Adapter Protocol (`base.py`)

All source adapters implement `SourceAdapter`:
- `key`, `title`, `publisher`, `source_url`, `licence`, `is_mandatory`
- `fetch()` → raw payload
- `parse(payload)` → iterator of `SourceEntity`

`fetch_with_retry` provides HTTP resilience with exponential backoff and configurable retries.

### Why No New Work Is Needed

The proposed plan describes EOCN/UNSC list ingestion as a Phase 1 deliverable. It is already fully implemented, tested, and handles the workbook format, delisting detection, programme tagging, and staleness monitoring.

---

## 4. goAML XML Reporting — 8 Report Types (95% Complete)

**File:** `amlkit/reporting/goaml.py`

### What It Does

Serializes compliance reports into goAML 5.x-compliant XML for filing with the UAE FIU via goAML portal.

### Supported Report Types

| Code | Report Type | Description |
|------|------------|-------------|
| STR | Suspicious Transaction Report | Core filing for suspicious transactions |
| SAR | Suspicious Activity Report | Activity-based suspicion, no specific transaction |
| PNMR | Partial Name Match Report | Near-match requiring disposition |
| FFR | Fund Freeze Report | Report on frozen assets/relationships |
| HRCT | High Risk Country Transaction | Transaction involving FATF-listed jurisdiction |
| HRCA | High Risk Country Activity | Activity involving FATF-listed jurisdiction |
| DPMSR | Dealers in Precious Metals and Stones Report | DPMS-specific filing |
| REAR | Real Estate Activity Report | Real estate sector filing |

### Key Function

**`serialize_goaml_xml(report_data: dict) -> str`**
Generates complete XML with:
- Report header (code, entity reference, submission date, currency)
- Reporting entity details (name, branch)
- Reporting person (legally accountable officer — validated, never placeholder)
- Reason/narrative with optional action taken
- Subject details (natural person with ID/DOB/nationality, or legal entity with trade licence)
- Transaction node (with unique `transactionnumber` using UUID suffix to prevent collisions) or activity node for non-financial reports
- Evidence pack attachment metadata

**`GoAMLValidationError`** is raised when required fields are missing — the module will not silently export a blank source account or unnamed reporting officer.

### What's Missing (5%)

- **DTR** (Dealer Transaction Report): Not yet added as a report_code variant. The XML structure would follow the same pattern as REAR/DPMSR.
- **XSD validation**: Output follows the standard but is not validated against the official goAML 5.x XSD. Requires obtaining the XSD from the FIU portal. Integration would be via `lxml.etree.XMLSchema`.
- **Automated FFR draft on match**: Serialization exists but is currently manual — needs a trigger from screening hits.

---

## 5. UBO Identification & Ownership Opacity Scoring (90% Complete)

**Files:** `amlkit/cases/manager.py`, `amlkit/risk/ruleset.yaml`

### What It Does

Implements the beneficial ownership identification required by Cabinet Resolution No. 134 of 2025, with a 25% threshold and automatic risk scoring based on ownership transparency.

### Key Constants & Logic

**`UBO_THRESHOLD_PCT = 25.0`** — Cabinet Resolution threshold.

**`add_ubo(conn, customer_id, *, org_id, person_name, ownership_pct, control_type, ...)`**
Records a beneficial owner. `is_ubo` is set automatically from:
- `ownership_pct >= 25.0`, OR
- `control_type == "senior_official"` (the regulation's explicit fallback when no natural person meets the ownership test)

**`ownership_state(conn, customer_id, org_id, customer_type) -> str`**
Derives an ownership-opacity band from recorded UBO data:
- Natural person → `"fully_transparent"`
- Legal entity with no UBO links → `"ubo_undisclosed"` (absence of evidence is a risk indicator)
- Any nominee → `"nominee_or_bearer"`
- No identified UBO → `"ubo_undisclosed"`
- Identified ownership < 50% → `"multi_layer_offshore"`
- Identified ownership < 75% → `"single_layer_foreign"`
- Identified ownership ≥ 75% → `"fully_transparent"`

### Risk Scoring Impact (`ruleset.yaml`)

```yaml
ownership_opacity:
  points_by_state:
    ubo_undisclosed: 45      # Near-automatic high risk
    nominee_or_bearer: 40
    multi_layer_offshore: 30
    single_layer_foreign: 15
    fully_transparent: 0
```

A legal entity with no UBO automatically receives 45 points — nearly enough for a "high" rating (50+ threshold) on its own. This is deliberate: the regulation treats inability to identify a UBO as a significant risk indicator, not merely a missing field.

### UBO Screening

During onboarding, every UBO is automatically screened against all loaded sanctions/PEP lists. A hit on any UBO blocks the customer just as a direct hit would:

```python
sanctions_hit = any(h.is_sanction for h in result.hits) or any(
    h.is_sanction for _, r in ubo_results for h in r.hits
)
```

### What's Missing (10%)

- **Frontend input bounds validation**: No check preventing negative ownership percentages or sums exceeding 100% — needs adding at the API/form layer.
- **Recursive multi-layer traversal**: Current model is flat (customer → UBOs). A corporate chain where Company A owns Company B which owns Company C requires recursive traversal through corporate layers to reach the natural person. Needs `parent_ubo_id` column on `ubo_links`.
- **Nominee exclusion flag**: `is_nominee` field does not exist on `ubo_links` — the `ownership_state()` function checks for `control_type == "nominee"` but there's no explicit `is_nominee` boolean column.

---

## 6. Transaction Monitoring / KYT — AED 55K Threshold (95% Complete)

**File:** `amlkit/screening/kyt.py`

### What It Does

Evaluates transactions against four rules that are standard, defensible, and checkable from data AMLKit already collects. Deliberately narrow — getting a small rule set right and explainable beats a large one that produces unjustifiable alerts.

### Rules

**1. Large Cash (`large_cash`)** — Severity: high
```python
LARGE_CASH_THRESHOLD_AED = 55_000.0
```
Triggered when a cash transaction meets or exceeds AED 55,000 (the standard UAE DNFBP occasional-transaction CDD trigger, aligned with FATF's EUR/USD 15,000 benchmark).

**2. Structuring (`structuring`)** — Severity: high
```python
STRUCTURING_WINDOW_DAYS = 7
STRUCTURING_MIN_COUNT = 2
```
Detects multiple cash transactions individually under the threshold that sum to meet or exceed it within a 7-day rolling window. Only fires when the *current* transaction is under-threshold (a large cash transaction is caught by rule 1 instead) and when at least 2 under-threshold transactions are involved.

**3. High Risk Country (`high_risk_country`)** — Severity: medium
```python
HIGH_RISK_COUNTRIES: frozenset = {"KP", "IR", "MM", "SY", "AF", "YE", "SS", "SD"}
```
Triggered when the counterparty country is on the FATF black/grey list or heavily sanctioned. Illustrative, not authoritative — a real deployment must keep this current.

**4. Velocity (`velocity`)** — Severity: medium
```python
VELOCITY_WINDOW_HOURS = 24
VELOCITY_MAX_COUNT = 5
```
Catches an unusually high transaction count in a 24-hour window, independent of amount — catches rapid movement that structuring (which requires near-threshold amounts) would miss.

### Key Function

**`evaluate_transaction(conn, *, org_id, customer_id, transaction_id, method, amount_aed, counterparty_country, occurred_at) -> list[TriggeredRule]`**
Runs all four rules against one just-recorded transaction. Reads sibling transactions from the database for structuring and velocity checks. Returns `TriggeredRule` dataclasses with `rule_key`, `severity`, and `detail` dict.

### Alert Deduplication (in engine.py)

The screening engine (`engine.py:_persist`) already deduplicates sanctions alerts — if an open (undispositioned) alert for the same entity/customer/UBO combination exists, no new alert row is created. The screening row is still recorded as evidence the obligation was met.

### What's Missing (5%)

- **KYT alert deduplication**: The structuring check can double-count transactions that already have an open alert. Needs a check to exclude transactions already covered by an existing open structuring alert within the same window.
- **Gaming threshold (AED 11,000)**: Not implemented — gaming operators are not currently scoped.
- **Wire/VA AED 3,500 CDD trigger**: Not implemented.

---

## 7. Adverse Media Screening via GDELT (100% Complete)

**File:** `amlkit/screening/adverse_media.py`, integrated via `amlkit/cases/manager.py`

### What It Does

Searches GDELT DOC 2.0 for adverse media coverage of customers, in both Arabic and Latin script. Uses a risk-based cadence (3/6/12 months per risk rating) with mandatory human disposition before any finding touches a risk rating.

### Architecture Decisions

1. **Query-time, not ingested.** Unlike sanctions lists, news cannot be bulk-loaded — there's no list to snapshot. Lives in `screening/` alongside `kyt.py` and `pf.py`, not in `ingest/`.
2. **Failure is soft, not loud.** A failed GDELT search returns `status="unavailable"` rather than blocking onboarding. The screening row still records the attempted check.
3. **Not auto-swept.** GDELT rate-limits to ~1 request per 5 seconds, so a 400-customer book would take over an hour. Explicit per-customer action instead, with periodic batches.

### Key Functions

**`search(name, *, name_arabic, client, window_months, max_records) -> AdverseMediaResult`**
Searches adverse coverage in both Latin and Arabic. Dual-script search merges findings by URL, keeping the stronger reading. Default window is 24 months. Never raises for provider failure — returns `status="unavailable"` instead.

**`classify(title: str) -> tuple[str, list[str]]`**
Classifies headline severity across three tiers, scanning all tiers (not stopping at first hit):
- `financial_crime_alleged` — money laundering, fraud, terrorism financing, trafficking, etc.
- `regulatory_action` — fines, enforcement, licence revocation, etc.
- `reputational_only` — scandal, allegations, whistleblower mentions, etc.

Terms include Arabic equivalents (e.g., "غسل الأموال" for money laundering, "رشوة" for bribery, "فضيحة" for scandal) because a Gulf fraud case is frequently reported in Arabic before English outlets pick it up.

**`build_query(name: str) -> str`**
Constructs GDELT query: exact-phrase name match AND any risk term. Server-side filtering via 19 English + 12 Arabic risk keywords to surface adverse coverage rather than neutral mentions.

### Risk-Based Cadences (`ruleset.yaml`)

```yaml
adverse_media_months:
  low: 12      # Annual re-check
  medium: 6    # Semi-annual
  high: 3      # Quarterly
```

### Disposition Flow (`manager.py`)

**`run_adverse_media(conn, *, org_id, name, name_arabic, customer_id, ...)`**
Runs the search and persists the screening record and findings. Deduplicates by URL — same article from a previous run for the same customer is not re-inserted.

**`disposition_adverse_media_finding(conn, finding_id, org_id, *, status, note, actor)`**
Operator marks a finding as `"relevant"` or `"not_relevant"`. Only relevant findings feed the risk model — no automatic scoring. This is the correct architecture: GDELT indexes coverage, it doesn't decide that a headline mentioning "Ahmed Al Mansoori" is about *your* Ahmed Al Mansoori. A human decides, and the rating follows.

**`adverse_media_severity(conn, customer_id, org_id) -> str`**
Returns worst severity among operator-confirmed relevant findings. Open and not_relevant findings score nothing.

**`adverse_media_due(conn, org_id) -> list[dict]`**
Returns customers whose adverse-media check is missing or stale, based on the cadence in `ruleset.yaml`. Only successful runs count — a failed attempt doesn't reset the clock. Never-checked customers sort first.

**`run_due_adverse_media(conn, org_id, *, limit, ...)`**
Batch re-check with default limit of 5 customers (rate-limit aware — 5 customers is already ~30-60 seconds of wall clock).

---

## 8. Customer Risk Rating Engine (100% Complete)

**Files:** `amlkit/risk/model.py`, `amlkit/risk/ruleset.yaml` (version 2025.12.2)

### What It Does

Implements the risk-based approach required by Cabinet Resolution No. 134 of 2025. Rules live in `ruleset.yaml` so changes are dated, reviewable documents rather than code diffs.

### Scoring Factors

| Factor | Possible Values | Points Range | Notes |
|--------|----------------|-------------|-------|
| `sanctions_hit` | true/false | 100 | `mandatory_high: true` — forces high regardless of total |
| `pep` | foreign/domestic/intl_org/rca | 25-45 | EDD always required for PEPs |
| `jurisdiction` | blacklist/greylist/high_risk/standard | 0-60 | `fatf_blacklist` is `mandatory_high` |
| `sector` | precious_metals/real_estate/VASPs/etc. | 5-35 | Virtual assets explicitly in scope under Law 10/2025 |
| `ownership_opacity` | fully_transparent to ubo_undisclosed | 0-45 | Absence of UBO is 45 points |
| `delivery_channel` | face_to_face to non_face_to_face_unverified | 0-25 | |
| `cash_intensity` | non_cash/mixed/predominantly_cash | 0-25 | |
| `adverse_media` | none to financial_crime_alleged | 0-35 | Only operator-confirmed findings |
| `structure` | natural_person to offshore_company | 0-25 | |

### Bands

- **Low**: 0–24 points → 36-month review cycle
- **Medium**: 25–49 points → 24-month review cycle
- **High**: 50+ points → 12-month review cycle

### Key Functions

**`assess(profile: CustomerProfile) -> RiskAssessment`**
Computes a risk rating. Returns `RiskAssessment` with `score`, `rating`, `requires_edd`, `factors` (per-factor contribution), `ruleset_version`, and `next_review` date.

**`save(conn, customer_id, assessment, org_id, actor)`**
Persists the assessment with full factor breakdown. Audit-logged.

**`RiskAssessment.explain() -> str`**
Human-readable breakdown showing each factor's point contribution, the total, the rating, and whether EDD is required.

### EDD Triggers

Enhanced Due Diligence is required when:
- Rating is "high", OR
- Customer is a PEP (any type), OR
- Customer has a sanctions hit, OR
- Customer's jurisdiction is FATF blacklist or greylist

### Re-Assessment

Three specialised re-assessment functions in `cases/manager.py` update exactly one factor at a time while carrying all others forward from the prior assessment — so a supervisor comparing two dated assessments sees the single thing that changed:

- `reassess_transaction_risk()` — maps open alert count to cash_intensity level
- `reassess_adverse_media()` — applies current adverse-media severity
- `reassess_risk()` — general re-rate with optional factor overrides

---

## 9. Screening Engine & Onboarding Pipeline (100% Complete)

**Files:** `amlkit/match/engine.py`, `amlkit/cases/manager.py`

### Screening Engine

**`screen(conn, name, *, org_id, trigger, threshold, ...) -> ScreeningResult`**
Screens one name against every loaded dataset. Pipeline:
1. `blocking_keys()` generates candidate retrieval keys
2. `_candidates()` retrieves entities sharing keys (up to 400, ranked by key overlap)
3. `score_entity()` scores each candidate with full feature breakdown
4. Hits above threshold are sorted by score and persisted with the screening record

Valid triggers: `"onboarding"`, `"list_update"`, `"periodic"`, `"transaction"`, `"adhoc"`

**`rescreen_all(conn, org_id, *, threshold, actor) -> dict`**
Re-screens every active customer and their UBOs after a dataset refresh. Satisfies the EOCN 24-hour obligation. Scoped to a single org — a dataset refresh triggers this once per active organization.

### Onboarding Pipeline

**`onboard(conn, *, org_id, full_name, ubos, ...) -> OnboardingResult`**
Complete CDD onboarding:
1. Creates customer record with canonical key
2. Screens customer in both Latin and Arabic scripts (keeps stronger evidence)
3. Screens every UBO
4. Derives PEP status from hits
5. Computes ownership opacity from UBO data
6. Runs risk assessment (screening result informs `sanctions_hit` factor)
7. Returns `OnboardingResult` with `blocked` flag and `obligations` set

The `OnboardingResult` carries typed obligations: each hit's `obligation` property returns the specific regulatory instruction (PF, TF, or generic sanctions), so the operator acting on the alert knows the regime.

---

## 10. Four-Eyes Review for Sanctions/PF Dispositions (100% Complete)

**File:** `amlkit/cases/review.py`

### What It Does

Independent review for the genuinely dangerous decision: dismissing a sanctions or PF match. Confirmed matches escalate to freeze and reporting anyway. Firms with one officer use `single_operator_mode`.

### Key Functions

**`propose_disposition(conn, alert_id, *, org_id, status, reason_code, operator, narrative)`**
Records a disposition or stages it for review. Applies immediately unless dismissing a sanctions/PF match in multi-operator mode, in which case the alert moves to `pending_review`.

**`confirm_disposition(conn, alert_id, *, org_id, operator, agree, ...)`**
Second-operator confirmation. Enforces that the confirming operator differs from the proposer. Can override (disagree → escalate).

### Structured Reason Codes

```python
REASON_CODES = {
    "different_dob": "Date of birth does not match",
    "different_nationality": "Nationality or country does not match",
    "name_coincidence": "Name coincidence - different person",
    "different_entity_type": "Different entity type",
    "insufficient_data": "Insufficient data to clear",
    "confirmed_match": "Confirmed match to the listed party",
    "other": "Other - see narrative",
}
```

Narrative is required for `true_positive`, `escalated`, `other`, and `insufficient_data` — but NOT for routine false-positive closures, preventing "FP" typed a hundred times.

---

## 11. Audit Trail & Tenant Isolation (100% Complete)

**File:** `amlkit/db.py`

### Audit Trail

Append-only `audit_log` table with SQLite triggers preventing UPDATE and DELETE on audit rows. Every write operation in the codebase calls `db.audit()` with:
- `actor` — who performed the action
- `action` — what was done (e.g., `"screening.run"`, `"alert.propose"`, `"customer.onboard"`)
- `object_type` and `object_id` — what it was done to
- `detail` — JSON with the specifics
- `org_id` — tenant scope (explicitly `None` for shared data like dataset refreshes)

### Tenant Isolation

Every query function takes `org_id` as a mandatory argument. Every table carrying tenant data has an `org_id` column. Routes resolve `org_id` from the session — no route skips this. Cross-tenant customer/alert IDs are treated as "not found" rather than filtered, so a mismatched `org_id` is indistinguishable from a nonexistent record.

---

## Summary Table

| Module | Completeness | Lines of Code | Remaining Work |
|--------|-------------|---------------|----------------|
| Arabic transliteration + fuzzy matching | 100% | ~650 | None |
| Proliferation financing classification | 100% | 110 | None |
| Sanctions list ingestion (EOCN + intl) | 100% | 900+ | None |
| goAML XML (8 report types) | 95% | 152 | DTR variant, XSD validation, auto-draft FFR |
| UBO identification + opacity scoring | 90% | ~150 | Frontend validation, recursive traversal, nominee flag |
| Transaction monitoring AED 55K | 95% | 162 | Alert dedup fix, gaming/wire thresholds |
| Adverse media screening (GDELT) | 100% | 611 | None |
| Customer risk rating engine | 100% | 206 + YAML | None |
| Screening engine + onboarding | 100% | 413 + 840 | None |
| Four-eyes review | 100% | 320 | None |
| Audit trail + tenant isolation | 100% | In db.py | None |
