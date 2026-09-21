# Google AML AI data model: gap analysis for amlkit

Status: proposal, 2026-09-21. No code changes yet.

## Summary

Google Cloud's AML AI publishes an input data model (what a bank feeds its
models) and an output data model (risk scores, explanations, and model-quality
metrics). This document maps both, field by field, onto amlkit's schema on
`master`, and recommends what to adopt.

**Conclusion: don't integrate with Google AML AI; borrow its data model.**

- AML AI targets "retail or commercial banking customers". Its core tables are
  built on bank accounts (`AccountPartyLink`), which DNFBPs don't have.
- It needs roughly 30 months of history (36 recommended) and learns from
  filed SARs. A DNFBP files too few STRs to train on.
- Quotas allow 10 instances per project per region, so one instance per amlkit
  org stops at 10 orgs. Sharing an instance across orgs would train one model
  on several tenants' customers and STRs, which `org_id` scoping can't prevent.
- Sending UAE customer data to it raises PDPL data-residency questions
  (not assessed).

Several of its design choices would still make amlkit more defensible to a
regulator. They are listed under [Recommendations](#recommendations).

Sources:
[input model](https://docs.cloud.google.com/financial-services/anti-money-laundering/docs/reference/schemas/aml-input-data-model),
[output model](https://docs.cloud.google.com/financial-services/anti-money-laundering/docs/reference/schemas/aml-output-data-model),
[quotas](https://docs.cloud.google.com/financial-services/anti-money-laundering/docs/quotas),
and "Understand data scope and duration" (linked from the input model page).

## Input data model

### Rules that apply to every table

- Each table and field is MANDATORY, RECOMMENDED or EXPERIMENTAL.
  EXPERIMENTAL fields aren't used by any production model yet.
- Enums must use a listed value. Empty strings and NULL are not allowed unless
  the field says so.
- **Records that can change are never overwritten.** Every change adds a new
  row with `validity_start_time`: when the organisation received and verified
  the information, not when the real-world change happened.
  `is_entity_deleted = TRUE` marks an end, with the other fields left empty.
- **Events never change.** `RiskCaseEvent` and `InteractionEvent` carry only
  `event_time`; new activity is a new row.
- **Joins must work at any point in time.** A `party_id` used on a given date
  must exist in `Party` with a row on or before that date.
- Sensitive values may be partly masked; for example, the 1st of the birth
  month is better than a NULL birth date.

### Party: the customer (MANDATORY)

Key: `party_id` + `validity_start_time`. amlkit table: `customers`.

| AML AI field | Level | amlkit | Gap |
|---|---|---|---|
| `party_id` | Mandatory | `id` (and `reference`) | Needs a pseudonymous ID (e.g. HMAC of org and id), never `id_number` |
| `validity_start_time` | Mandatory | none | **Missing.** Rows are overwritten; `updated_at` keeps only the latest change |
| `is_entity_deleted` | Recommended | none | Retention purge deletes rows outright (`cases/manager.py` `purge_expired`) |
| `source_system` | Recommended | none | Could record web / mobile / OCR |
| `type` (COMPANY, CONSUMER) | Mandatory | `customer_type` (legal, natural) | Maps directly |
| `name` | Experimental | `full_name`, `name_arabic` | OK |
| `addresses[]`: `address_line`, `street`, `building_number`, `post_office_box`, `post_code`, `town` | Recommended | `address_line1`, `address_line2`, `postal_code`, `city` | No street / building / PO Box split; one address only |
| `addresses.subregion` | **Mandatory, no NULL** | none | **Missing: the emirate** |
| `addresses.region_code` | Mandatory | `country` | OK if stored as ISO-2 |
| `birth_date` | Recommended | `birth_date` | OK |
| `establishment_date` | Recommended | none | **Missing** for legal persons; only `trade_licence` |
| `occupation` | Recommended | `sector` | Different meaning: sector is the business, not an individual's occupation |
| `gender` | Recommended | `gender` | OK |
| `nationalities[]` | Recommended | `nationality` (single) | Dual nationals can't be recorded |
| `residencies[]` (tax residency) | Recommended | `country` | `country` is the address country, not tax residency |
| `join_date` | **Mandatory** | `onboarded_at` | OK |
| `exit_date` | **Mandatory** | none | **Missing:** only `status = 'closed'` and `retention_until` |
| `assets_value_range` (range; units + nanos + ISO currency) | Recommended | `source_of_wealth` (free text) | No figures |
| `civil_status_code` | Recommended | none | Missing |
| `phone_numbers[]`, `email_addresses[]` | Experimental | `phone`, `email`, `contact_*` | Single values only |
| `education_level_code` | Recommended | none | Missing (low value for DNFBPs) |

Party registration sizes commercial parties SMALL below 500 transactions a month
and LARGE at or above.

### AccountPartyLink: who holds which account (MANDATORY)

Fields: `account_id`, `party_id`, `validity_start_time`, `is_entity_deleted`,
`role` (PRIMARY_HOLDER, SECONDARY_HOLDER, SUPPLEMENTARY_HOLDER). Every account
needs a primary holder at all times.

**amlkit has no accounts.** The nearest concepts are `ubo_links` (ownership,
not account holding, with no validity history) and the customer relationship
itself. This table is the clearest sign that AML AI is built for banks.

### Transaction (MANDATORY)

Key: `transaction_id` + `validity_start_time`. amlkit table: `transactions`.

| AML AI field | Level | amlkit | Gap |
|---|---|---|---|
| `transaction_id` | Mandatory | `id` / `reference` | OK |
| `validity_start_time`, `is_entity_deleted` | Mandatory / Recommended | `created_at` only | No way to record corrections or reversals |
| `type` (WIRE, CASH, CHECK, CARD, OTHER, CRYPTO) | Mandatory | `method` (cash, wire, cheque, crypto, other) | No CARD |
| `direction` (DEBIT, CREDIT; from the account's side) | Mandatory | `direction` (outbound, inbound) | Maps directly |
| `account_id` | Mandatory | `customer_id` | No account level |
| `counterparty_account.account_id` | Mandatory, nullable | none | NULL is allowed for external counterparties |
| `counterparty_account.counterparty_name` | Experimental | `counterparty_name` | OK |
| `counterparty_account.addresses[]` (with mandatory `subregion`, `region_code`) | Experimental | none | No counterparty address |
| `counterparty_account.region_code` (for cash: where paid in or out) | Recommended | `counterparty_country` | OK |
| `book_time` | Mandatory | `occurred_at` | OK |
| `normalized_booked_amount` (one currency for the dataset; units + nanos; non-negative) | Mandatory | `amount_aed REAL`, plus `amount`, `currency` | Floating point, not exact; FX rate and source not recorded |
| `ip_address` (type, region, `is_vpn`) | Experimental | none | Missing; relevant only to online payments |

### InteractionEvent (EXPERIMENTAL)

Fields: `interaction_event_id`, `party_id`, `account_id`, `type` (LOGIN,
PAYMENT_METHOD_ADDED, KYC_CHANGE, PASSWORD_CHANGE, OTHER), `event_time`,
`ip_address`.

The nearest thing in amlkit is customer-related `audit_log` entries, which cover
KYC_CHANGE only. Those are operator actions, not the customer's own activity.

### RiskCaseEvent: case lifecycle and training labels (MANDATORY)

Fields: `risk_case_event_id`, `event_time`, `type`, `party_id`,
`risk_case_id`, `risk_typology_measurements[].risk_typology_id`.

Minimum per party and case: one AML_PROCESS_START, one AML_PROCESS_END, and
AML_EXIT where the customer is exited. AML_SUSPICIOUS_ACTIVITY_START and _END
are strongly recommended.

| AML AI event type | Nearest in amlkit |
|---|---|
| AML_ALERT_LEGACY (rule-based alert) | `alerts` (screening), `transaction_alerts` (transaction monitoring) |
| AML_ALERT_ADHOC, AML_ALERT_EXTERNAL | Adverse-media hits; a `reports` row with no alert |
| AML_PROCESS_START, AML_PROCESS_END | Implied: alert `created_at`, then `alert_reviews`, then `dispositioned_at` |
| AML_SUSPICIOUS_ACTIVITY_START, _END | **Missing:** when the suspicious activity itself began and ended |
| AML_SAR | `reports` (STR/SAR) with `submitted_at` |
| AML_EXIT | Relationship closure (no date column) |
| `risk_case_id` | **Missing:** nothing groups related alerts, reviews, reports and freezes into one case |
| `risk_typology_id` | **Missing:** only `transaction_alerts.rule_key` |

`freeze_obligations` (UAE targeted financial sanctions) has no AML AI
equivalent; it would be a UAE-specific event type.

### PartySupplementaryData (RECOMMENDED)

Up to 100 numeric (FLOAT64) values per customer, keyed by
`party_supplementary_data_id`, each with its own validity history. The
organisation is responsible for making sure they don't leak outcomes into the
model.

Natural amlkit candidates:
- `risk_assessments.score`
- the EDD flag (`requires_edd`)
- PEP and sanctions hit counts from `screenings.hits`
- adverse-media severity
- the cash-intensive flag
- the number of open freeze obligations

## Output data model

All outputs are written to BigQuery.

| Output | Fields | Meaning | Nearest in amlkit |
|---|---|---|---|
| Risk scores | `party_id`, `risk_period_end_time`, `risk_score` (0 to 1) | One score per customer per month | `risk_assessments.score` / `rating`: rule-based points and a band, per assessment rather than monthly |
| Explainability | `party_id`, `risk_period_end_time`, `attributions[]` (`feature` family, `attribution`) | Which signal *families* drove the score | `risk_assessments.factors`, `alerts.score_detail`. amlkit explains individual rules, which is finer-grained |
| Registered parties | `party_id`, `party_size`, `earliest_remove_time`, `party_with_prediction_intent`, `registration_or_uptier_time` | Billing and registration | Not applicable |
| Engine config metadata | `ExpectedRecallPreTuning`, `ExpectedRecallPostTuning`, `Missingness` | Expected detection rate for a given investigation capacity | None |
| Model metadata | `Missingness`, `Importance` per feature family | How much each signal family matters | None |
| Backtest metadata | `ObservedRecallValues` (20 operating points plus one at the hint), `ObservedRecallValuesPerTypology`, `Missingness`, `Skew` | Measured recall at different thresholds, per typology | **None:** amlkit's thresholds are never back-tested |
| Prediction metadata | `Missingness`, `Skew` (family and max, 0 to 1; -1 means unused) | Data drift since training | None |

What the output model suggests for amlkit, beyond the input tables:

- **Recall at an operating point.** "At threshold X we would have caught Y% of
  the cases that became STRs, with Z investigations a month." amlkit can compute
  this from its own history for its rule thresholds (the KYT large-cash
  threshold, the screening match threshold, the risk-band cut-offs). This is a
  model-governance item a UAE MLRO can use.
- **Missingness.** The share of customers missing each CDD field (nationality,
  source of funds, UBO verification and so on) is a direct CDD-quality measure.
- **Skew.** Watching month-to-month drift in the customer and transaction mix
  is cheap to add as a dashboard metric.

## Quotas and multi-tenancy

| Limit | Value |
|---|---|
| Instances per project per region | 10 |
| Datasets / models per project per region | 1,000 each |
| Engine configs per project per region | 2,000 |
| Concurrent jobs per project per region | tuning 1, training 5, prediction and backtest combined 5 |
| API requests | 100 per second per project per region, and 100 per Google Cloud organization per region |
| Parties processed per day, per operation type | 55,000,000 per project and per Google Cloud organization |
| Registered parties per project per region | 1,500,000 |

Quota increases are available only through Google support. The quotas page
states no table-size or data-volume cap.

For amlkit's tenancy:

- One instance per amlkit org stops at 10 orgs per project per region. Beyond
  that, each org needs its own GCP project.
- All amlkit orgs under one Google Cloud organization share the
  100 requests-per-second limit.
- **Do not share an instance across orgs.** One model trained on several
  tenants' customers and STR labels leaks data between tenants through the
  model's weights and explanations.

Minimum history (from "Understand data scope and duration", engine v004.010):
about 30 months of transactions and account links, 29 months of case events and
17 months of party data, with 36 months recommended for a first test. With
DNFBP STR volumes this also means very few positive labels.

## Recommendations

For amlkit itself, in rough priority order. Effort: S small, M medium, L large.

| # | Change | Effort | Why it matters | Main files |
|---|---|---|---|---|
| 1 | Customer and UBO version history: an append-only `customer_versions` table (`org_id`, `valid_from`, `recorded_at`, snapshot), trigger-protected like `audit_log`, written on onboard, edit, close and reactivate; "as of" queries | M | Answers "what did we know about this customer on the day we rated them?" | `db.py`, `cases/manager.py`, `api/mobile.py`, `api/app.py`, `queries.py` |
| 2 | Cases with an event timeline: `cases` and `case_events` (`org_id`, `case_id`, `customer_id`, `type`, `event_time`, `typology`), fed by alert, review, STR, freeze and exit | M to L | One timeline per case; evidences deadlines such as the 24-hour freeze | `db.py`, `cases/manager.py`, `cases/review.py`, `reporting/goaml.py`, `queries.py` |
| 3 | `exit_date` and `exit_reason` on closure | S | The retention clock should run from closure; today there is no closure date | `db.py`, `cases/manager.py` |
| 4 | Richer CDD fields: emirate, multiple nationalities, `establishment_date`, tax residency | S to M | Better screening and jurisdiction risk | `db.py`, `cases/manager.py`, templates, `risk/model.py` |
| 5 | Exact money: integer fils or Decimal instead of REAL, plus FX rate and source | S to M | Avoids rounding drift in thresholds and goAML amounts | `db.py`, `cases/manager.py`, `screening/kyt.py`, `reporting/goaml.py` |
| 6 | Typology tags on alerts and reports | S | Per-typology hit rates; aligns with goAML indicators | `db.py`, `screening/kyt.py`, `cases/review.py`, `reporting/goaml.py` |
| 7 | Counterparty address and emirate on transactions | S | Geographic risk on counterparties | `db.py`, `cases/manager.py`, `screening/kyt.py` |
| 8 | Back-test report for rule thresholds: recall at current thresholds from past alerts and STRs, per typology | M | Evidence that thresholds are calibrated, not arbitrary | new `reporting/backtest.py`, `queries.py`, dashboard |
| 9 | CDD completeness report: share of missing CDD fields per org | S | Direct CDD-quality measure | `queries.py`, dashboard |

Notes on the recommendations:

- Every new table carries `org_id NOT NULL`, and every query takes `org_id`, as
  in the rest of the codebase.
- Items 1 and 2 are design changes and should get their own design review
  before implementation.
- Version history (item 1) must still be erasable when a customer's retention
  period ends. That needs a controlled, audited exception to the append-only
  rule.
- Items 8 and 9 are metrics with a real query behind them, as PLAN 4.3 requires.

**Not recommended now:** an export adapter to AML AI. It would depend on items 1
and 2, since without real validity times it would have to invent them, which the
input model warns causes leakage. The scope, history and tenancy problems above
also make it unrealistic for DNFBPs.

## Open questions

- Which GCP regions AML AI is available in, and whether any satisfy UAE
  data-residency requirements.
- Whether AML AI has a minimum number of positive labels (not stated in the
  pages reviewed).
- Retention of version history: 10 years from closure, the same as the customer
  record (`RETENTION_YEARS = 10`)?
