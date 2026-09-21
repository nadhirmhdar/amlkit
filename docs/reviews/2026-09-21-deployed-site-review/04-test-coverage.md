# amlkit — Test-coverage / TDD lane findings

Date: 2026-09-21. Scope: /home/user/amlkit (read-only). Interpreter: `.venv/bin/python` (pytest 9.1.1, coverage 7.16.1 installed for this run). Method: superpowers `test-driven-development` + `verification-before-completion`, gstack `review/specialists/testing.md`. Every number below comes from a command run in this session; logs are in `scratchpad/tdd/`.

## 1. Suite results (fresh run)

Command: `cd /home/user/amlkit && .venv/bin/python -m pytest tests/ -q -p no:cacheprovider --ignore=tests/test_ocr.py`

| Metric | Value |
|---|---|
| Passed | 996 |
| Failed | 6 |
| Skipped | 1 (`test_gdelt_bq.py:90` — `GOOGLE_CLOUD_PROJECT` not set) |
| Test functions collected (AST count, excl. test_ocr.py) | 980 defs / 1003 items incl. parametrisation |
| Wall time | 144.65 s (coverage re-run: 146.86 s) |
| Exit code | 1 |

All six failures are the same environmental cause — `ModuleNotFoundError: No module named 'passporteye'` raised at `amlkit/cases/ocr.py:41` (module-level `from passporteye import read_mrz`), reached lazily from the mobile scan handlers:

- `tests/test_mobile_api.py::TestDocumentScan::test_scan_passport_merges_image_quality_into_response` — `E ModuleNotFoundError: No module named 'passporteye'`
- `tests/test_mobile_api.py::TestDocumentScan::test_scan_passport_extraction_failure_is_a_clean_400` — `E ModuleNotFoundError: No module named 'passporteye'`
- `tests/test_mobile_api.py::TestDocumentScan::test_scan_passport_failure_includes_quality_flags_when_available` — `E ModuleNotFoundError: No module named 'passporteye'`
- `tests/test_mobile_api.py::TestDocumentScan::test_scan_emirates_id_merges_image_quality_into_response` — `E ModuleNotFoundError: No module named 'passporteye'`
- `tests/test_mobile_api.py::TestDocumentScan::test_scan_emirates_id_extraction_failure_is_a_clean_400` — `E ModuleNotFoundError: No module named 'passporteye'`
- `tests/test_new_features_e2e.py::TestIdentityVerificationE2E::test_scan_passport_response_includes_authenticity_field` — `E ModuleNotFoundError: No module named 'passporteye'`

Notes: (a) `tests/test_ocr.py` was excluded as instructed for the same reason (passporteye wheel cannot build here). (b) Those six tests should `pytest.importorskip("passporteye")` rather than error, so the suite can be green on hosts without tesseract — today an optional OCR dependency makes the whole suite red. (c) PLAN.md's ground-truth table says two `test_csp_no_inline_scripts` failures are pre-existing on master; they passed in this run, so that note is stale. (d) No lock errors were observed despite a concurrent run.

## 2. Coverage (measured)

Command: `.venv/bin/python -m coverage run --include='amlkit/*' -m pytest tests/ -q -p no:cacheprovider --ignore=tests/test_ocr.py` then `coverage report -m --include='amlkit/*' --sort=cover`. **TOTAL: 6,819 statements, 1,733 missed, 75%.** Lowest first (100%-covered `__init__`/tiny modules omitted):

| Module | Stmts | Miss | Cover | Missing lines (abridged) |
|---|---|---|---|---|
| `amlkit/cases/ocr.py` | 174 | 168 | 3% | 46-463 |
| `amlkit/ingest/uk.py` | 119 | 109 | 8% | 25-30, 33-38, 41-187 |
| `amlkit/ingest/un.py` | 92 | 82 | 11% | 18-23, 26-31, 34-159 |
| `amlkit/ingest/ofac.py` | 71 | 61 | 14% | 18-23, 26-31, 36-129 |
| `amlkit/ingest/eu.py` | 106 | 88 | 17% | 49-53, 59-108, 111-202 |
| `amlkit/cases/scheduler.py` | 137 | 71 | 48% | 32-93, 104-111, 128, 166-170, 196-200, 212, 231, 237-238 |
| `amlkit/mail.py` | 105 | 54 | 49% | 113, 142-189, 217, 243-282 |
| `amlkit/ai/gemini.py` | 47 | 24 | 49% | 36-45, 50-54, 86, 94, 151-176, 193-227, 247-272 |
| `amlkit/ingest/base.py` | 92 | 32 | 65% | 154-158, 162-166, 172-204 |
| `amlkit/storage.py` | 74 | 25 | 66% | 36-37, 43, 49-51, 67, 71-75, 80-84, 125, 135, 148-153 |
| `amlkit/cases/operators.py` | 83 | 28 | 66% | 33, 35, 106-151, 178 |
| `amlkit/api/mobile.py` | 768 | 248 | 68% | 104-113, 117, 198, 210-211, 366-372, 377-407, 418, 423, 542, 565-584, 589-599, 604-614, 623, 635-640, 670-6... |
| `amlkit/ingest/fatf.py` | 64 | 17 | 73% | 91-97, 188-211 |
| `amlkit/db.py` | 141 | 34 | 76% | 880, 901-923, 937-980, 1008-1071, 1121, 1128, 1157, 1235 |
| `amlkit/api/app.py` | 1582 | 367 | 77% | 109-135, 162-170, 209, 272-273, 317, 320, 371-373, 413-415, 492, 539-540, 551, 558-559, 578-592, 597, 605, ... |
| `amlkit/ingest/eocn.py` | 322 | 73 | 77% | 148, 264, 274-294, 299-305, 313-314, 325, 383, 425, 429-435, 501, 525-549, 556-557, 568-569, 580-581, 607, ... |
| `amlkit/cases/diagram.py` | 47 | 10 | 79% | 92-94, 107-110, 138-143 |
| `amlkit/cases/reports.py` | 39 | 6 | 85% | 105-107, 135, 143-149 |
| `amlkit/cases/manager.py` | 561 | 80 | 86% | 65-78, 82-85, 89, 93, 170-171, 215, 304, 334-335, 371, 377, 395-397, 422, 428-429, 921, 972-973, 986, 1041,... |
| `amlkit/ingest/loader.py` | 88 | 12 | 86% | 29, 44, 80-96, 138-143, 152, 239, 246-247 |
| `amlkit/screening/gdelt_bq.py` | 67 | 8 | 88% | 36-37, 52, 56-58, 94-95 |
| `amlkit/cases/review.py` | 151 | 17 | 89% | 103, 135-137, 142, 167, 215, 251, 310, 340, 348, 354, 373-377, 394 |
| `amlkit/cases/freeze.py` | 36 | 4 | 89% | 28-29, 75, 78 |
| `amlkit/queries.py` | 284 | 31 | 89% | 40-41, 47, 52-54, 81-82, 231-241, 321-322, 710-725, 753, 829-830 |
| `amlkit/screening/adverse_media.py` | 200 | 18 | 91% | 265-272, 367-370, 396-397, 400-401, 461, 480, 508-509, 609 |
| `amlkit/ingest/cia.py` | 103 | 9 | 91% | 125-126, 133-134, 152, 155-156, 196, 241 |
| `amlkit/logging_config.py` | 35 | 3 | 91% | 35, 39, 43 |
| `amlkit/ingest/interpol.py` | 57 | 4 | 93% | 39-40, 53, 67 |
| `amlkit/auth.py` | 234 | 16 | 93% | 190, 208-212, 263, 284-287, 297-299, 306-308, 426, 546 |
| `amlkit/match/engine.py` | 148 | 10 | 93% | 78-81, 107, 141, 417-425 |
| `amlkit/reporting/goaml.py` | 120 | 8 | 93% | 92, 135, 166, 223-227 |
| `amlkit/api/deps.py` | 63 | 3 | 95% | 43, 114-115 |
| `amlkit/names/arabic.py` | 166 | 5 | 97% | 179, 307, 406-408 |
| `amlkit/match/cache.py` | 34 | 1 | 97% | 27 |
| `amlkit/screening/kyt.py` | 119 | 3 | 97% | 182, 290, 292 |
| `amlkit/risk/model.py` | 90 | 2 | 98% | 64, 163 |
| `amlkit/match/scorer.py` | 96 | 2 | 98% | 90, 202 |

Reading the floor:
- `ingest/uk.py` 8%, `ingest/un.py` 11%, `ingest/ofac.py` 14%, `ingest/eu.py` 17%: the four international sanctions **parsers** are essentially untested. Only `eocn.py` (77%), `cia.py` (91%), `interpol.py` (93%) have fixture-driven parser tests. A silent format change on the UN/OFAC/EU/UK feeds would ship unnoticed — this is the highest-risk coverage hole in a sanctions product.
- `cases/ocr.py` 3%: environmental (passporteye).
- `cases/scheduler.py` 48% (lines 32-93 = the refresh/notify loop), `mail.py` 49%, `ai/gemini.py` 49%: outbound integrations exercised only through stubs.
- `api/mobile.py` 68% (248 missed lines) vs `api/app.py` 77%: the mobile REST surface is the thinner-tested of the two — see the route table.
- `cases/operators.py` 66%: lines 106-151 (`complete_initial_setup`) never run.

## 3. Route → test mapping (static)

Method: every `@app.<verb>("...")` / `@router.<verb>("...")` decorator in `amlkit/api/app.py` and `amlkit/api/mobile.py` (router prefix `/api/v1` applied) was matched against `tests/**/*.py` with `{param}` segments turned into a wildcard. `files` = number of test files containing the path; `hits` = occurrences. Handler-name references are counted separately (route-registration smoke tests). Script: `scratchpad/tdd/map_coverage.py`; raw data `routes_map.json`.

**145 routes total (87 web, 58 mobile). 29 routes have zero tests hitting their path** (22 mobile, 7 web).

### 3a. Routes with ZERO tests

| Method | Path | Handler | Defined at | Why it matters |
|---|---|---|---|---|
| POST | `/acknowledge-disclaimer` | `acknowledge_disclaimer` | app.py:573 | gate on first login; untested = could be skippable |
| POST | `/admin/org-profile` | `admin_save_org_profile` | app.py:2013 | writes the goAML reporting-entity fields (#142 fix path) — write side untested |
| POST | `/alerts/bulk-dismiss` | `alerts_bulk_dismiss` | app.py:1617 | closes sanctions alerts in bulk; bypasses four-eyes (see proposed test 2) |
| GET | `/api/alerts-summary` | `alerts_summary` | app.py:2832 | dashboard JSON; tenant scoping unverified |
| GET | `/console/org/{org_id}/customers` | `console_org_customers` | app.py:1928 | super-admin cross-tenant CDD view, unaudited (proposed test 5) |
| GET | `/customers/{customer_id}/gdelt-bq` | `customer_gdelt_bq` | app.py:1226 | outbound BigQuery call from a customer page |
| GET | `/reports/new` | `report_new_view` | app.py:2629 | entry to STR builder |
| POST | `/api/v1/admin/operators/{operator_id}/deactivate` | `api_admin_deactivate_operator` | mobile.py:1365 | mobile RBAC — officer→403 tested only on web (#99) |
| POST | `/api/v1/admin/operators/{operator_id}/reset-password` | `api_admin_reset_password` | mobile.py:1310 | mobile RBAC — same |
| POST | `/api/v1/admin/refresh` | `api_admin_refresh` | mobile.py:1383 | mobile RBAC — same |
| POST | `/api/v1/adverse-media/run-due` | `api_adverse_media_run_due` | mobile.py:919 | scheduled adverse-media sweep trigger |
| GET | `/api/v1/alerts.csv` | `api_alerts_csv` | mobile.py:1225 | CSV export — formula-injection guard (PR #112) only tested via web /alerts.csv |
| GET | `/api/v1/alerts/summary` | `api_alerts_summary` | mobile.py:1065 | dashboard counts |
| POST | `/api/v1/alerts/{alert_id}/assign` | `api_alert_assign` | mobile.py:1215 | mobile assignment |
| POST | `/api/v1/alerts/{alert_id}/confirm` | `api_alert_confirm` | mobile.py:1196 | mobile four-eyes confirm — 'different operator' rule unverified on mobile |
| GET | `/api/v1/auth/setup` | `api_setup_check` | mobile.py:364 | first-run bootstrap over the mobile API (GET+POST) |
| POST | `/api/v1/auth/setup` | `api_setup_submit` | mobile.py:375 | first-run bootstrap over the mobile API (GET+POST) |
| GET | `/api/v1/customers.csv` | `api_customers_csv` | mobile.py:1238 | CSV export — same |
| GET | `/api/v1/customers/{customer_id}/documents/{doc_id}` | `api_customer_download_document` | mobile.py:1021 | document download — cross-tenant read of ID documents unverified |
| GET | `/api/v1/customers/{customer_id}/evidence` | `api_customer_evidence` | mobile.py:627 | evidence bundle over mobile |
| POST | `/api/v1/customers/{customer_id}/risk` | `api_customer_reassess_risk` | mobile.py:660 | mobile risk re-assessment write |
| PATCH | `/api/v1/customers/{customer_id}/risk-factors` | `api_customer_update_risk_factors` | mobile.py:683 | mobile PATCH of risk factors |
| POST | `/api/v1/customers/{customer_id}/signatures` | `api_customer_add_signature` | mobile.py:1042 | signature upload over mobile |
| GET | `/api/v1/datasets` | `api_datasets` | mobile.py:416 | read-only list |
| GET | `/api/v1/reason-codes` | `api_reason_codes` | mobile.py:421 | read-only list |
| GET | `/api/v1/reports/{report_id}/export` | `api_report_export` | mobile.py:1507 | goAML XML over mobile |
| GET | `/api/v1/review-queue` | `api_customers_due_review` | mobile.py:1154 | four-eyes queue over mobile |
| GET | `/api/v1/risk/ruleset` | `api_risk_ruleset` | mobile.py:738 | read-only ruleset |
| POST | `/api/v1/transaction-alerts/{alert_id}/disposition` | `api_txn_alert_disposition` | mobile.py:857 | KYT alert closure over mobile |

### 3b. Routes with exactly one test file (thin)

53 routes are hit from a single file; the security-relevant ones: `POST /freeze-obligations/{freeze_id}/execute`, `POST /freeze-obligations/{freeze_id}/resolve`, `POST /transaction-alerts/{alert_id}/disposition`, `POST /adverse-media/{finding_id}/disposition`, `POST /customers/{customer_id}/signatures`, `POST /alerts/{alert_id}/confirm`, `POST /alerts/{alert_id}/assign`, `GET /alerts.csv`, `GET /customers.csv`, `GET /audit/export`, `POST /admin/operators/{operator_id}/reset-password`, `POST /admin/refresh`, `GET /admin/refresh-stream`, `POST /api/v1/adverse-media/{finding_id}/disposition`, `POST /api/v1/alerts/{alert_id}/disposition`, `GET /api/v1/audit`, `POST /api/v1/admin/threshold`, `GET /api/v1/audit/export`.

### 3c. Full table (sorted by test-file count)

| Method | Path | Test files | Hits | Handler refs |
|---|---|---|---|---|
| POST | `/acknowledge-disclaimer` | 0 | 0 | 0 |
| POST | `/admin/org-profile` | 0 | 0 | 0 |
| POST | `/alerts/bulk-dismiss` | 0 | 0 | 0 |
| GET | `/api/alerts-summary` | 0 | 0 | 0 |
| POST | `/api/v1/admin/operators/{operator_id}/deactivate` | 0 | 0 | 0 |
| POST | `/api/v1/admin/operators/{operator_id}/reset-password` | 0 | 0 | 0 |
| POST | `/api/v1/admin/refresh` | 0 | 0 | 0 |
| POST | `/api/v1/adverse-media/run-due` | 0 | 0 | 0 |
| GET | `/api/v1/alerts.csv` | 0 | 0 | 0 |
| GET | `/api/v1/alerts/summary` | 0 | 0 | 0 |
| POST | `/api/v1/alerts/{alert_id}/assign` | 0 | 0 | 0 |
| POST | `/api/v1/alerts/{alert_id}/confirm` | 0 | 0 | 0 |
| GET | `/api/v1/auth/setup` | 0 | 0 | 0 |
| POST | `/api/v1/auth/setup` | 0 | 0 | 0 |
| GET | `/api/v1/customers.csv` | 0 | 0 | 0 |
| GET | `/api/v1/customers/{customer_id}/documents/{doc_id}` | 0 | 0 | 0 |
| GET | `/api/v1/customers/{customer_id}/evidence` | 0 | 0 | 0 |
| POST | `/api/v1/customers/{customer_id}/risk` | 0 | 0 | 0 |
| PATCH | `/api/v1/customers/{customer_id}/risk-factors` | 0 | 0 | 0 |
| POST | `/api/v1/customers/{customer_id}/signatures` | 0 | 0 | 0 |
| GET | `/api/v1/datasets` | 0 | 0 | 0 |
| GET | `/api/v1/reason-codes` | 0 | 0 | 0 |
| GET | `/api/v1/reports/{report_id}/export` | 0 | 0 | 0 |
| GET | `/api/v1/review-queue` | 0 | 0 | 0 |
| GET | `/api/v1/risk/ruleset` | 0 | 0 | 0 |
| POST | `/api/v1/transaction-alerts/{alert_id}/disposition` | 0 | 0 | 0 |
| GET | `/console/org/{org_id}/customers` | 0 | 0 | 0 |
| GET | `/customers/{customer_id}/gdelt-bq` | 0 | 0 | 0 |
| GET | `/reports/new` | 0 | 0 | 0 |
| GET | `/about` | 1 | 7 | 0 |
| POST | `/admin/operators/{operator_id}/reset-password` | 1 | 1 | 0 |
| POST | `/admin/refresh` | 1 | 1 | 0 |
| GET | `/admin/refresh-stream` | 1 | 2 | 0 |
| POST | `/adverse-media/run-due` | 1 | 2 | 0 |
| POST | `/adverse-media/{finding_id}/disposition` | 1 | 2 | 0 |
| GET | `/alerts.csv` | 1 | 3 | 1 |
| POST | `/alerts/{alert_id}/assign` | 1 | 5 | 0 |
| POST | `/alerts/{alert_id}/confirm` | 1 | 2 | 2 |
| POST | `/api/ai/draft-narrative` | 1 | 3 | 0 |
| POST | `/api/v1/admin/threshold` | 1 | 1 | 0 |
| GET | `/api/v1/adverse-media` | 1 | 2 | 0 |
| POST | `/api/v1/adverse-media/{finding_id}/disposition` | 1 | 2 | 0 |
| GET | `/api/v1/alerts` | 1 | 3 | 0 |
| GET | `/api/v1/alerts/{alert_id}` | 1 | 1 | 0 |
| POST | `/api/v1/alerts/{alert_id}/disposition` | 1 | 1 | 0 |
| GET | `/api/v1/audit` | 1 | 4 | 0 |
| GET | `/api/v1/audit/export` | 1 | 4 | 0 |
| POST | `/api/v1/auth/logout` | 1 | 1 | 0 |
| GET | `/api/v1/auth/me` | 1 | 1 | 0 |
| POST | `/api/v1/auth/resend-verification` | 1 | 4 | 0 |
| POST | `/api/v1/customers/scan-emirates-id` | 1 | 3 | 0 |
| POST | `/api/v1/customers/scan-passport` | 1 | 4 | 0 |
| POST | `/api/v1/customers/{customer_id}/adverse-media` | 1 | 2 | 0 |
| POST | `/api/v1/customers/{customer_id}/close` | 1 | 1 | 0 |
| POST | `/api/v1/customers/{customer_id}/notes` | 1 | 1 | 0 |
| POST | `/api/v1/customers/{customer_id}/transactions` | 1 | 6 | 0 |
| GET | `/api/v1/customers/{customer_id}/transactions` | 1 | 6 | 0 |
| POST | `/api/v1/reports/{report_id}/submit` | 1 | 3 | 0 |
| POST | `/api/v1/screen` | 1 | 3 | 0 |
| GET | `/api/v1/transaction-alerts` | 1 | 2 | 0 |
| GET | `/audit/export` | 1 | 3 | 4 |
| PATCH | `/compliance/deadlines/{deadline_id}` | 1 | 2 | 0 |
| DELETE | `/compliance/deadlines/{deadline_id}` | 1 | 2 | 0 |
| GET | `/console/org/{org_id}/alerts` | 1 | 2 | 1 |
| GET | `/customers.csv` | 1 | 2 | 1 |
| POST | `/customers/scan-passport` | 1 | 2 | 0 |
| POST | `/customers/{customer_id}/adverse-media` | 1 | 2 | 0 |
| GET | `/customers/{customer_id}/kg-screen` | 1 | 2 | 0 |
| POST | `/customers/{customer_id}/reactivate` | 1 | 6 | 0 |
| POST | `/customers/{customer_id}/signatures` | 1 | 3 | 0 |
| POST | `/customers/{customer_id}/ubo` | 1 | 10 | 0 |
| POST | `/feedback` | 1 | 3 | 0 |
| POST | `/freeze-obligations/{freeze_id}/execute` | 1 | 5 | 0 |
| POST | `/freeze-obligations/{freeze_id}/resolve` | 1 | 3 | 0 |
| GET | `/health` | 1 | 7 | 3 |
| GET | `/policies` | 1 | 10 | 2 |
| POST | `/policies/upload` | 1 | 5 | 3 |
| GET | `/policies/{policy_id:int}/download` | 1 | 2 | 2 |
| GET | `/profile` | 1 | 4 | 0 |
| POST | `/profile/change-password` | 1 | 2 | 0 |
| POST | `/resend-verification` | 1 | 3 | 1 |
| POST | `/transaction-alerts/{alert_id}/disposition` | 1 | 1 | 0 |
| GET | `/account/password` | 2 | 11 | 0 |
| POST | `/account/password` | 2 | 11 | 0 |
| GET | `/admin/compliance` | 2 | 8 | 0 |
| POST | `/admin/operators/{operator_id}/deactivate` | 2 | 2 | 0 |
| POST | `/admin/rescreen` | 2 | 6 | 5 |
| GET | `/admin/rule-config` | 2 | 15 | 6 |
| POST | `/admin/rule-config` | 2 | 15 | 6 |
| POST | `/admin/threshold` | 2 | 7 | 0 |
| GET | `/api/v1/admin` | 2 | 5 | 0 |
| POST | `/api/v1/admin/operators` | 2 | 2 | 0 |
| POST | `/api/v1/customers/{customer_id}/documents` | 2 | 9 | 0 |
| GET | `/api/v1/customers/{customer_id}/documents` | 2 | 9 | 0 |
| POST | `/api/v1/customers/{customer_id}/ubo` | 2 | 6 | 0 |
| GET | `/api/v1/dashboard` | 2 | 5 | 0 |
| GET | `/api/v1/reports` | 2 | 7 | 0 |
| POST | `/api/v1/reports` | 2 | 7 | 0 |
| GET | `/api/v1/reports/{report_id}` | 2 | 4 | 0 |
| GET | `/compliance/calendar` | 2 | 4 | 0 |
| GET | `/compliance/deadlines` | 2 | 9 | 0 |
| POST | `/compliance/deadlines` | 2 | 9 | 0 |
| GET | `/console` | 2 | 13 | 0 |
| POST | `/customers/{customer_id}/close` | 2 | 2 | 1 |
| GET | `/customers/{customer_id}/evidence` | 2 | 4 | 2 |
| POST | `/customers/{customer_id}/notes` | 2 | 5 | 0 |
| POST | `/customers/{customer_id}/transactions` | 2 | 7 | 0 |
| GET | `/freeze-obligations` | 2 | 12 | 0 |
| GET | `/freeze-obligations/{freeze_id}` | 2 | 10 | 0 |
| POST | `/freeze-obligations/{freeze_id}/file-ffr` | 2 | 2 | 0 |
| GET | `/reports/{report_id}/export` | 2 | 3 | 0 |
| GET | `/setup` | 2 | 4 | 1 |
| POST | `/setup` | 2 | 4 | 0 |
| POST | `/system/create-operator` | 2 | 11 | 1 |
| POST | `/system/refresh` | 2 | 6 | 1 |
| POST | `/alerts/{alert_id}/disposition` | 3 | 13 | 3 |
| GET | `/reports/build` | 3 | 4 | 0 |
| POST | `/reports/{report_id}/submit` | 3 | 7 | 5 |
| POST | `/admin/operators` | 4 | 9 | 0 |
| POST | `/api/v1/auth/login` | 4 | 8 | 0 |
| POST | `/logout` | 4 | 7 | 0 |
| GET | `/screen` | 4 | 19 | 0 |
| POST | `/screen` | 4 | 19 | 0 |
| POST | `/api/v1/auth/verify-email` | 5 | 14 | 0 |
| GET | `/api/v1/customers/{customer_id}` | 5 | 35 | 0 |
| GET | `/customers/new` | 5 | 6 | 0 |
| POST | `/api/v1/auth/register-organization` | 6 | 16 | 2 |
| GET | `/api/v1/customers` | 6 | 54 | 0 |
| POST | `/api/v1/customers` | 6 | 54 | 0 |
| GET | `/audit` | 7 | 17 | 0 |
| GET | `/dashboard` | 7 | 11 | 46 |
| GET | `/customers/{customer_id}` | 8 | 58 | 3 |
| GET | `/alerts` | 9 | 31 | 162 |
| GET | `/reports/{report_id}` | 9 | 23 | 0 |
| GET | `/reports` | 10 | 35 | 0 |
| POST | `/reports` | 10 | 35 | 1 |
| GET | `/admin` | 11 | 72 | 1 |
| GET | `/customers` | 16 | 108 | 323 |
| POST | `/customers` | 16 | 108 | 0 |
| GET | `/login` | 24 | 80 | 1 |
| POST | `/login` | 24 | 80 | 0 |
| GET | `/verify-email` | 25 | 30 | 1 |
| GET | `/register-organization` | 26 | 81 | 0 |
| POST | `/register-organization` | 26 | 81 | 1 |
| GET | `/` | 76 | 262 | 4 |

## 4. Public functions → test mapping (static + coverage cross-check)

Method: `ast` walk of each module's top-level `def`s and class methods not starting with `_`; a function counts as referenced if its name appears in any test file (methods: `.name(`). Cross-checked against the measured missing-line list above so 'referenced' ≠ 'exercised'. Raw data `funcs_map.json`.

| Module | Public fns | Referenced by tests | Unreferenced |
|---|---|---|---|
| `amlkit/match/engine.py` | 11 | 3 | 8 |
| `amlkit/match/scorer.py` | 4 | 2 | 2 |
| `amlkit/names/arabic.py` | 9 | 8 | 1 |
| `amlkit/reporting/goaml.py` | 1 | 1 | 0 |
| `amlkit/screening/kyt.py` | 4 | 2 | 2 |
| `amlkit/screening/pf.py` | 4 | 4 | 0 |
| `amlkit/risk/model.py` | 4 | 4 | 0 |
| `amlkit/ingest/base.py` | 7 | 3 | 4 |
| `amlkit/ingest/cia.py` | 3 | 2 | 1 |
| `amlkit/ingest/eocn.py` | 3 | 2 | 1 |
| `amlkit/ingest/eu.py` | 3 | 3 | 0 |
| `amlkit/ingest/fatf.py` | 4 | 3 | 1 |
| `amlkit/ingest/interpol.py` | 2 | 2 | 0 |
| `amlkit/ingest/loader.py` | 3 | 3 | 0 |
| `amlkit/ingest/ofac.py` | 2 | 2 | 0 |
| `amlkit/ingest/opensanctions.py` | 7 | 2 | 5 |
| `amlkit/ingest/uk.py` | 2 | 2 | 0 |
| `amlkit/ingest/un.py` | 2 | 2 | 0 |
| `amlkit/cases/diagram.py` | 1 | 1 | 0 |
| `amlkit/cases/freeze.py` | 2 | 0 | 2 |
| `amlkit/cases/manager.py` | 33 | 25 | 8 |
| `amlkit/cases/ocr.py` | 5 | 5 | 0 |
| `amlkit/cases/operators.py` | 3 | 0 | 3 |
| `amlkit/cases/reports.py` | 1 | 0 | 1 |
| `amlkit/cases/review.py` | 7 | 3 | 4 |
| `amlkit/cases/scheduler.py` | 3 | 3 | 0 |

### 4a. Public functions with no direct test reference

Grouped, with the coverage verdict (from `coverage report -m`) so indirect coverage is not miscounted:

**Unreferenced AND lines missed (genuinely untested)**

| Where | Function(s) | Note |
|---|---|---|
| `amlkit/cases/manager.py:1071` | `reassess_risk` | body 1097-1160 never executed |
| `amlkit/cases/operators.py:91` | `complete_initial_setup` | 106-151 never executed; the `/setup` route tests do not reach it |
| `amlkit/ingest/base.py:120` | `fetch_with_retry` | retry/backoff branches 32 lines missed; only stubbed adapters in test_heartbeat |
| `amlkit/ingest/opensanctions.py:155-175` | `uae_local_terrorists, un_sanctions, global_sanctions, peps, cia_world_leaders` | adapter factories never constructed |
| `amlkit/ingest/cia.py:239` | `cia_world_leaders` | factory never constructed (parser is tested) |
| `amlkit/ingest/eocn.py:741` | `uae_local_terrorists` | factory never constructed (parser is tested) |
| `amlkit/ingest/fatf.py:183` | `get_country_risk` | public lookup untested |
| `amlkit/cases/review.py:74` | `single_operator_mode` | only reached via env-var branches |
| `amlkit/cases/manager.py:64-92` | `OnboardingResult.summary / all_hits / obligations / has_proliferation_hit` | lines 65-93 missed — the result object's public API is dead in tests |

**Unreferenced by name but exercised via routes (OK, but no unit contract)**

| Where | Function(s) | Note |
|---|---|---|
| `amlkit/cases/review.py:418` | `assign_alert` | via POST /alerts/{id}/assign |
| `amlkit/cases/review.py:408` | `review_history` | via console/alerts pages |
| `amlkit/cases/review.py:198` | `needs_independent_review` | via propose_disposition |
| `amlkit/cases/manager.py:409` | `reactivate_customer` | via POST /customers/{id}/reactivate |
| `amlkit/cases/manager.py:540` | `due_for_review` | via dashboard |
| `amlkit/cases/manager.py:1014` | `reassess_adverse_media` | via adverse-media routes |
| `amlkit/cases/operators.py:18,158` | `register_organization, provision_operator` | via /register-organization and /system/create-operator |
| `amlkit/cases/reports.py:25` | `save_report` | via POST /reports |
| `amlkit/cases/freeze.py:13,42` | `parse_freeze_assets_from_form, file_ffr_report` | via freeze routes (freeze.py 89%) |
| `amlkit/screening/kyt.py:77` | `evaluate_transaction` | via add_transaction (kyt.py 97%) |
| `amlkit/match/engine.py:34-105` | `Hit.is_sanction/is_pep/categories/is_proliferation/is_terrorism/obligation, ScreeningResult.summary, EntityMatch.keys` | engine.py 93% — properties exercised through screen(); no direct assertions on the obligation mapping |
| `amlkit/match/scorer.py:57,66` | `ScoreResult.as_dict, token_similarity` | scorer.py 98% |
| `amlkit/names/arabic.py:292` | `canonical_token` | arabic.py 97% |
| `amlkit/screening/kyt.py:73` | `TriggeredRule.to_detail_json` | serialised into alerts |
| `amlkit/ingest/base.py:66-86` | `SourceEntity.name_rows / tokens / raw_json` | via loader.load() |

Modules where every public function is referenced: `screening/pf.py`, `risk/model.py`, `reporting/goaml.py` (`serialize_goaml_xml`), `ingest/{eu,uk,un,ofac,interpol,loader}.py` (by name — but see coverage: uk/un/ofac/eu parsers are referenced only through the loader/heartbeat stubs and their parse bodies are 83-92% unexecuted), `cases/{ocr,scheduler,diagram}.py`.

## 5. Test-quality smells (file:line)

Scanner: `scratchpad/tdd/smells.py` (AST) plus manual reading. Good news first: **no test mocks the database** — the only `monkeypatch`/`patch` targets are `httpx.get`, `amlkit.mail.*`, `amlkit.storage._gcs_client`, `amlkit.storage.delete`, and two `amlkit.db.audit`/`record_dataset_error` stubs in `test_p41_sanctions_refresh_sse.py:79-80`. Real SQLite everywhere, per CLAUDE.md.

### Assert-nothing / vacuous

- `tests/test_p21_compliance_cal.py:7-25` — three 'smoke' tests assert only that a path is in `app.routes`, a function `hasattr`s on `queries`, and a template file exists. Zero behaviour. `test_t15_compliance_calendar.py` covers the real behaviour, so these are dead weight that would still pass if the calendar returned garbage.
- `tests/test_p41_sanctions_refresh_sse.py:9` — same route-registration pattern for `/admin/refresh-stream`.
- `tests/test_p30_goaml_gate.py:43-48` — `try: serialize_goaml_xml(...) except GoAMLValidationError: pass`. The 'supported types serialise' test swallows the very error class the serializer uses, so it passes even if STR/SAR/FFR serialisation is broken.
- `tests/test_compliance_health.py:56`, `tests/test_kyt.py:498`, `tests/test_t13_password_complexity.py:42`, `tests/test_password_complexity.py:92` — 'should not raise' tests with no assertion. Acceptable pattern only if the negative twin exists; it does for the password tests, not for `save_rule_config` (no assertion that the saved values round-trip).
- `tests/test_p40_adverse_media_async.py:93` — `assert status["status"] in ["complete", "failed"]` accepts failure as success.

### Over-broad status assertions

- `tests/test_t2_report_submit.py:189` — `assert r.status_code in [200, 403, 404]` then `"not found" in text or "denied" in text or "reports" in r.url`: a cross-tenant submit test that passes on almost any response.
- `tests/test_t5_password_change.py:112` — `in [200, 400, 401]`.
- `tests/test_p13_mime_validation.py:46,84,120` — `in [400, 401, 403]`: a 401 (unauthenticated) would satisfy a test meant to prove MIME rejection.

### Flaky / time-dependent / network

- `tests/test_p40_adverse_media_async.py:88,127` — `time.sleep(1)` in a 30-iteration poll loop, and the background thread calls `amlkit/screening/adverse_media.py:339 httpx.get(...)` against GDELT with no stub: a real network call inside the unit suite. On this sandbox it 'passes' because failure is accepted (see above). Up to 60 s of wall time in the worst case.
- `tests/test_sanctions_banner.py:78,93` and 60 other files (213 lines) build timestamps from `datetime.now()`/`utcnow()`; the ones computing `-timedelta(hours=50)` against a 24 h max-age are safe, but `tests/test_p38_ubo_last_verified.py`, `tests/test_retention_until.py` and `tests/test_t15_compliance_calendar.py` compare stored dates to 'today' and will behave differently at 23:59 UTC vs 00:01 UTC. No `freezegun`/clock injection is used anywhere.
- `tests/test_gdelt_bq.py:85` — the single `skipif` (needs `GOOGLE_CLOUD_PROJECT`); the rest of the file uses `MagicMock` clients, i.e. it tests the mock (superpowers 'tests mock not code').

### Implementation-coupled

- `tests/test_storage.py:58-95` — asserts `mock_client.bucket.assert_called_once_with(...)`, `mock_blob.delete.assert_called_once()`: verifies the call shape of the GCS SDK, not an observable outcome. Unavoidable at the SDK boundary, but the two `purge_expired` tests (`:97,:121`) patch `amlkit.storage.delete` so a regression in `storage.delete` itself is invisible.
- `tests/test_p41_sanctions_refresh_sse.py:79-80` — stubs `amlkit.db.audit` to a no-op, so the SSE refresh path's audit trail is untested.

### Missing negative-path next to happy-path

- Four-eyes: single dismissal has full positive+negative coverage (`test_api.py:517-560`), but `POST /alerts/bulk-dismiss` has no route test and `test_p43_alerts_group_dismiss.py:150-195` tests only the happy path of `bulk_dismiss_alerts` (count, org isolation, audit) — never that a sanctions match is *not* closed by one operator. Proposed test 2 shows it is.
- RBAC: `test_admin_rbac.py` proves officer→403 for six web `POST /admin/*` routes (#99 fixed), but none of the mobile twins (`/api/v1/admin/operators/{id}/deactivate`, `/reset-password`, `/admin/refresh`) have a denied-case test.
- Tenant isolation: `test_tenant_isolation.py` has zero `/api/v1` references; the mobile document download `/api/v1/customers/{id}/documents/{doc_id}` has no cross-org test.
- MFA: `test_p15_mfa_totp.py` covers enrol/verify/backup codes at unit level; there is no test that login *requires* MFA — because it doesn't (proposed test 1).

### Duplication / drift

- Nine p-/t- file pairs test the same feature twice with different fixtures (password change p16/t5, session limit p22/t12, compliance calendar p21/t15, report submit p17/t2, audit export/t14, password complexity/t13, login rate limit p23/keying, auth-log IP/t7, MIME p13/t6). Not wrong, but each pair re-implements `_register`/`client` locally instead of importing `tests/conftest.register_org`, so a change to the registration flow must be fixed in ~12 places (it already bit once: `_register` docstring in `test_api.py:69-86`).
- `amlkit/match/engine.py` starts with a UTF-8 BOM (`U+FEFF`); Python tolerates it but any tool that `ast.parse`s a plain `read_text()` (this mapper, linters, coverage plugins) trips over it.

### Skips

- Only one conditional skip in the whole suite (`test_gdelt_bq.py:85`); no unconditional skips. Good. The passporteye-dependent tests should join it via `importorskip` instead of erroring.

## 6. Proposed failing tests (RED, verified)

File: `scratchpad/tdd/test_proposed_gaps.py`. It imports `_register`, `_csrf`, `_seed_sanctions_data`, `LISTED` from `tests/test_api.py` and builds the same `client` fixture, so it can be copied into `tests/` unchanged. Because the file lives outside `tests/`, the repo's autouse fixtures must be loaded explicitly:

```
cd /home/user/amlkit && .venv/bin/python -m pytest -p tests.conftest \
  scratchpad/tdd/test_proposed_gaps.py -q -p no:cacheprovider
```

Result (fresh): **9 failed, 0 errors, 0 passed in 3.21 s** — 5 behaviours, one parametrised over 4 paths. Each failure is on the test's own assertion (import/fixture errors were fixed first: the initial run errored on the rate limiter because conftest was not loaded, and test 5 on the table name `audit` → `audit_log`; both corrected and re-run).

```
FAILED ../../..test_proposed_gaps.py::TestMfaLoginGate::test_password_alone_does_not_open_a_session_for_an_mfa_enrolled_operator
FAILED ../../..test_proposed_gaps.py::TestBulkDismissFourEyes::test_bulk_dismiss_of_a_sanctions_match_is_staged_for_independent_review
FAILED ../../..test_proposed_gaps.py::TestReportSubmitDoesNotClaimFiuTransmission::test_finalising_a_report_does_not_tell_the_mlro_it_reached_the_fiu
FAILED ../../..test_proposed_gaps.py::TestNoStoreOnAuthenticatedResponses::test_authenticated_html_carries_no_store[/]
FAILED ../../..test_proposed_gaps.py::TestNoStoreOnAuthenticatedResponses::test_authenticated_html_carries_no_store[/customers]
FAILED ../../..test_proposed_gaps.py::TestNoStoreOnAuthenticatedResponses::test_authenticated_html_carries_no_store[/alerts]
FAILED ../../..test_proposed_gaps.py::TestNoStoreOnAuthenticatedResponses::test_authenticated_html_carries_no_store[/audit]
FAILED ../../..test_proposed_gaps.py::TestNoStoreOnAuthenticatedResponses::test_csv_export_carries_no_store
FAILED ../../..test_proposed_gaps.py::TestConsoleCrossOrgAccessIsAudited::test_viewing_another_orgs_customers_writes_an_audit_row
9 failed, 2 warnings in 3.21s
```

| # | Test | Fails today because | Why it matters (value) | Backlog ref |
|---|---|---|---|---|
| 1 | `TestMfaLoginGate::test_password_alone_does_not_open_a_session_for_an_mfa_enrolled_operator` | `login responded 303 -> /` and the dashboard rendered: `app.py:475 login_submit` never reads `mfa_secrets`; `auth.mfa_enroll/mfa_verify` exist but nothing calls them at login | Enrolled MFA that is never enforced is worse than none — it tells the MLRO they are protected. Blocker named in PLAN 2.14 / PR #197 | PLAN 2.14, p15 |
| 2 | `TestBulkDismissFourEyes::test_bulk_dismiss_of_a_sanctions_match_is_staged_for_independent_review` | `statuses == ['false_positive']`: `review.py:437 bulk_dismiss_alerts` writes the final status directly, skipping `needs_independent_review()` that `propose_disposition` applies | One operator can clear a UN/EOCN sanctions match with a single click — the exact 'thin disposition record' the four-eyes rule exists to prevent; the route has zero tests | untested route `POST /alerts/bulk-dismiss` |
| 3 | `TestReportSubmitDoesNotClaimFiuTransmission::test_finalising_a_report_does_not_tell_the_mlro_it_reached_the_fiu` | page contains `report submitted to uae fiu successfully.` (`app.py:2783`) though no transmission exists | Regulatory deception risk: an MLRO may believe a STR was filed when the goAML XML was never uploaded | Issue #141 (PLAN 1.1, high) |
| 4 | `TestNoStoreOnAuthenticatedResponses` (4 HTML paths + `/customers.csv`) | `Cache-Control=''` — no header set anywhere in `amlkit/api/` (grep confirmed) | Customer CDD pages and CSV exports can be served from a shared-browser disk cache after logout | PLAN 2.12 |
| 5 | `TestConsoleCrossOrgAccessIsAudited::test_viewing_another_orgs_customers_writes_an_audit_row` | `audit_log` has no `console.%` row: `app.py:1877-1953` console routes contain no `audit()` call | Platform staff viewing a tenant's KYC data leaves no trace — fails 'super-admin cross-org access is logged' and undermines the append-only audit story sold to regulators | PLAN 2.7 |

GREEN path for each is named in the test docstring (the production change that would make it pass). Not chosen, with reasons: stale-source banner for officers (#72) — `render()` at `app.py:278-280` already injects `dataset_banner` for any session, so a test would pass; officer→403 on web `/admin/*` (#99) — already covered by `test_admin_rbac.py`; goAML per-org entity (#142) — covered by `test_issue_142_goaml_org_name.py`; privacy/terms pages (PLAN 8.3) — real gap but lower value than the five above; p18 — no reference to it exists anywhere in the repo, so its content is unknown.

## 7. Board items p14–p22 — status from the tests that exist

The p-/t- board itself is not in the repo (PLAN.md 'Sources merged'), so this is reconstructed from test docstrings:

| Item | Feature | Evidence | State |
|---|---|---|---|
| p14 | Idle session timeout (`last_active`) | `test_idle_timeout.py`, `auth.py:45,191,207` | built + tested |
| p15 | MFA TOTP | `test_p15_mfa_totp.py` (unit only) | half-built: enrol/verify exist, **login never enforces** (proposed test 1) |
| p16 | Self-service password change | `test_p16_*`, `test_t5_*` | built + tested (twice) |
| p17 | Report submit validation | `test_p17_*`, `test_t2_*` | built; confirmation copy is wrong (#141, proposed test 3) |
| p18 | unknown | no reference in repo | — |
| p19 | Password complexity server-side | `test_password_complexity.py`, `test_t13_*` | built + tested |
| p20 | Audit CSV export with date filter | `test_audit_export.py`, `test_t14_*` | built + tested; mobile twin `/api/v1/audit/export` 1 file |
| p21 | Compliance calendar | `test_p21_*` (smoke only), `test_t15_*` | built; p21 file is vacuous |
| p22 | Concurrent session limit | `test_p22_*`, `test_t12_*` | built + tested (twice) |

## 8. Artefacts

- `scratchpad/tdd/suite_run1.log` — full pytest output (run 1)
- `scratchpad/tdd/coverage_run.log`, `coverage_report.txt` — coverage run + `report -m`
- `scratchpad/tdd/map_coverage.py`, `routes_map.json`, `funcs_map.json` — static mapper and raw data
- `scratchpad/tdd/smells.py` — smell scanner
- `scratchpad/tdd/test_proposed_gaps.py`, `proposed_run.txt` — the five RED tests and their verified failing run
