# amlkit deployed-site review — 21 September 2026

Multi-lane review of the production amlkit deployment (Cloud Run, me-central1), run with the review methods from the sibling reference repositories:

| Lane | Method / source repo | Report |
|---|---|---|
| Security | gstack `/cso` audit phases + `review/specialists/security.md`, `red-team.md`; live probes | [01-security.md](01-security.md) |
| QA | gstack `/qa` phases + `webapp-testing` skill (Playwright reconnaissance-then-action) | [02-qa.md](02-qa.md) |
| UX / accessibility / design | ui-ux-pro-max (`ux-guidelines.csv`, `ui-reasoning.csv`) + gstack `/design-review` checklist | [03-ux-design.md](03-ux-design.md) |
| Test coverage / TDD | superpowers `test-driven-development`, `verification-before-completion` + gstack `review/specialists/testing.md` | [04-test-coverage.md](04-test-coverage.md) |
| Infrastructure, public APIs, workflow, MCP | freefordev, public-apis, langflow, MCP Toolbox config | [05-infra-api-workflow.md](05-infra-api-workflow.md) |
| Deploy pipeline | direct read of `.github/workflows`, `Dockerfile`, `entrypoint.sh`, `litestream.yml` | [06-deploy-pipeline.md](06-deploy-pipeline.md) |

Proposed failing tests for the gaps found: [proposed_tests/test_proposed_gaps.py](proposed_tests/test_proposed_gaps.py). Evidence screenshots: [evidence/](evidence/).

## How the review was run, and one important limitation

The live URL `https://amlkit-720622408077.me-central1.run.app` is denied by the review sandbox's egress proxy at the CONNECT step (curl and WebFetch both fail before any request reaches Cloud Run). The repo's own `docs/CONTINUOUS_IMPROVEMENT.md` records the same block for weeks. **No request in this review touched production.**

Instead, the exact deployed code (`aad9a39`, current `origin/master`, minus the one-commit TOTP change described below) was started in the sandbox in Cloud Run mode (`AMLKIT_BEHIND_PROXY=1`, secure cookies, HSTS, CSP) and every live check ran against it. Outbound sanctions and GDELT fetches fail in the sandbox, which turned out to be a useful test in itself (see finding 1).

The branch under review was `65be993`; `origin/master` was one commit ahead (`aad9a39`, TOTP enforced at MLRO login). That commit was reviewed by reading. Where a lane reported "MFA exists but is not wired into login", that is **already fixed on master** and is not repeated below.

Test suite in the sandbox: **996 passed, 1 skipped, 6 failed**. All six failures are `ModuleNotFoundError: passporteye` (the OCR wheel cannot build here); CI on Ubuntu/Python 3.12 builds it. Not a code regression.

## Top findings, ranked

| # | Sev | Finding | Where | Lane |
|---|---|---|---|---|
| 1 | **P0 compliance** | With every remote sanctions source failing, the bundled FATF jurisdiction list (26 rows, `is_mandatory=True`, hardcoded fallback) alone satisfies `datasets_fresh()`. Dashboard says "Sanctions lists refreshed within the 24-hour window", Compliance Health shows one green row and no failed-source rows, onboarding is unblocked, and every customer is screened against **0 records** and recorded **Clear**. Mobile `/api/v1/screen` returns `clear:true`. | `amlkit/ingest/loader.py:221-245` (`datasets_fresh` returns True on any one fresh mandatory dataset); `amlkit/ingest/fatf.py:61-78` | QA-01 |
| 2 | **P0 UI** | `/freeze-obligations`, `/freeze-obligations/{id}` and `/admin/rule-config` render **blank**: the templates declare `{% block content %}` but `base.html` renders `{% block body %}`. The TFS freeze workflow (Cabinet Resolution 134/2025) and KYT rule configuration are unusable in the UI. Confirmed on `origin/master`. | `amlkit/web/templates/freeze_obligations.html:5`, `freeze_obligation_detail.html`, `admin/rule-config.html`; `base.html:156` | UX #1, QA-12/19 |
| 3 | **CRITICAL infra** | Cloud Run deploys with `--max-instances 10` and no `--concurrency`, while every instance restores its own SQLite file and runs `litestream replicate -exec` against **one** GCS replica path. Litestream is single-writer; two instances under load means divergent databases and a corrupted or partial restore. `docs/CONTINUOUS_IMPROVEMENT.md:44` already noticed the refresh-storm symptom of this root cause. | `.github/workflows/source-canary.yml:388-389`, `scripts/entrypoint.sh:89`, `litestream.yml` | Deploy, Survey A |
| 4 | **HIGH security** | `client_ip()` returned the **first** non-private `X-Forwarded-For` hop, which the client controls behind Cloud Run. Live: rotating XFF values bypassed the `/login` 10/min limit entirely (14 attempts, zero 429s), and a customer signature POST recorded an attacker-chosen `ip_address` on the legally significant signature record. **Already fixed on master** (see Corrections below) — the reviewed branch predates the fix. | `amlkit/api/deps.py` `client_ip()`; consumers `app.py:185,196,1563` | Security #1 |
| 5 | **HIGH data integrity** | `POST /reports` with the `report_id` of a **submitted** report overwrites it (UI says "locked and archived"). Filed regulatory reports are mutable after submission. Separately, "Report submitted to UAE FIU successfully." is shown after a local status flip with no transmission or goAML receipt. | `amlkit/api/app.py` reports save route; `app.py:2783` | QA-03, Tests T3 |
| 6 | **HIGH four-eyes** | `bulk_dismiss_alerts` writes `status='false_positive'` directly, bypassing the independent-review gate a single dismissal requires; one operator can clear every open sanctions match on a customer. The state-machine review also found four-eyes applies only to `false_positive`: one operator can confirm a match and execute a freeze in both modes. | `amlkit/cases/review.py:437-463`; `POST /alerts/bulk-dismiss` (zero tests) | Tests T2, Survey C |
| 7 | **HIGH availability** | Under 30 parallel authenticated GETs, 2 requests returned HTTP 500 with `sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread`, raised from `get_db()` teardown. The per-request connection is opened with the default `check_same_thread=True` and FastAPI's generator-dependency teardown can run on a different threadpool thread. | `amlkit/api/deps.py:59-66`, `amlkit/db.py:1109` | QA-04 |
| 8 | **HIGH lockout** | The org's only MLRO can deactivate themselves; there is no reactivate route or UI, so the org loses policy upload, operator management, resets and refresh until someone edits the database. | `POST /admin/operators/{id}/deactivate` | QA-02 |
| 9 | **HIGH secrets** | `SCHEDULER_SECRET`, `ADMIN_API_SECRET`, SendGrid password, EU FSF token and Gemini key are passed as plaintext `--set-env-vars`, readable by anyone with `run.services.get` and shown in revision history. CI reads them back from the live service each deploy. | `.github/workflows/source-canary.yml:296-325, 378` | Deploy, Survey A, Security #5 |
| 10 | **HIGH tenant** | MCP Toolbox config exposes `search_customers`, `get_alerts`, `get_screenings` with **no `org_id` filter**: any MCP client can read every tenant's customers, alerts and screenings. The SQLite source is opened read-write. | `toolbox/tools.yaml` | Survey D |
| 11 | **MEDIUM** | Mobile `/api/v1/auth/login` has no rate limit (web login has 10/min IP and 3/min account). With the 8-failure/15-minute lockout this enables a mass account-lockout denial of service. | `amlkit/api/mobile.py` `api_login` | Security #2 |
| 12 | **MEDIUM** | Server-side validation gaps on onboarding, operators and reports: 5,000-char names (page becomes 51,510 px wide), `birth_date=2030-13-45`, `nationality=ZZZZ`, `customer_type=alien`, `role=superadmin`, `email=not-an-email`, `report_type=BOGUS` (creates `goAML-BOGUS-3`), negative STR amounts. An invalid `jurisdiction_tier` scores **0 points**, so bad input lowers risk. | `POST /customers`, `POST /admin/operators`, `POST /reports`, STR builder | QA-08/09/10/11 |
| 13 | **MEDIUM** | `GET /customers/{id}/gdelt-bq` → 500 (`TypeError: unhashable type: 'dict'`); `GET /policies/{missing}/download` → 500; `GET /admin/refresh-stream` starts a full refresh and re-screen as a side effect of a GET. | `app.py` | QA-06/07/16 |
| 14 | **MEDIUM a11y** | WCAG AA failures across the app: `--ink-3` (#888d92) at 3.2:1 on every label, eyebrow and muted text; placeholders 2.4:1; 23 unlabelled inputs on onboarding; nationality combobox not keyboard-operable and silently posts `""` for free text; modals without dialog role or focus trap; login fields with no visible focus ring; body text 14.5px on phones. | `amlkit/web/static/app.css`, templates | UX #3–#12 |
| 15 | **MEDIUM mobile** | Feedback FAB overlaps the bottom tab bar on every phone page; admin operator rows overprint name over email; evidence pack scrolls horizontally on phones. | `base.html`, `admin.html`, `evidence.html` | UX #6, #9, #10 |
| 16 | **MEDIUM nav** | `/alerts` has no navigation entry anywhere; with zero open alerts the dashboard has no link to it. `/profile` is unreachable from any menu. Transaction alerts do not appear on `/alerts` or the customer Alerts tab, only under Monitoring. | `base.html`, `dashboard.html` | UX #2, #18; QA-13 |
| 17 | **LOW** | `app.js` is included twice, so every page throws `Identifier 'assetCount' has already been declared`; `/favicon.ico` 404 on every page; no `Cache-Control: no-store` on authenticated pages; JSON 404/422 bodies on HTML routes. | `base.html`, `login.html` | QA-18/26/28 |

Everything the lanes verified as solid is listed at the end of [01-security.md](01-security.md) and [02-qa.md](02-qa.md): tenant isolation held end to end on web and mobile (a second org could not read or modify the first org's customer, notes, documents or evidence by id), CSRF, cookie flags, argon2id parameters, RBAC, CSP/HSTS headers, upload MIME checks, CSV-formula escaping, goAML XML validity, Arabic/RTL rendering, and audit logging.

## Corrections to lane reports

- **`scripts/security_scan.py`**: all 16 flags it raises today are false positives (multi-line `WHERE ... AND org_id=?` the regex cannot parse, correlated subqueries, keyword-only `org_id`, super-admin routes gated by `require_super_admin`). The scanner needs an AST-aware rewrite or it will train people to ignore it.
- **Survey lane, "cross-tenant MLRO `To:` leak in `mail.py:169`"**: false positive. `amlkit/cases/scheduler.py:213-236` already sends the staleness alert per organization (issue #138). Multiple MLROs of the *same* org share a `To:` line, which is acceptable.
- **MFA "dead code" (security #6, QA-29, tests T1)**: superseded by `aad9a39` on master, which locks MLRO sessions until TOTP is verified on web and mobile.
- **XFF spoofing (security #1, finding 4)**: already fixed on master by `b775623` (PR #248), which reads `X-Forwarded-For` right-to-left so a client cannot pick which hop is treated as trusted. The reviewed branch (`65be993`) predates this fix; the live probe results above are accurate against that branch, not against current master.

## Backlog status (p31–p34, from the amlkit-full-review skill)

| Item | Status |
|---|---|
| p31 Freeze Obligations inside Dashboard | Partial. `<details>` panel exists but its CSS classes do not, so it renders unstyled; the target page is blank (finding 2). |
| p32 Nationality dropdown, full ISO list with search | Partial. 194 entries (HK, PS, TW, XK, MO missing), search works, keyboard and ARIA broken, free text posts `""`. |
| p33 Alerts as a dashboard drawer | Not done, and Alerts lost its nav entry. |
| p34 Avatar chip with Profile / Admin / Audit / Policies | Mostly done. Profile missing from both menus; phone menu omits Policies. |

## Coverage and tests

- Statement coverage 75% (6,819 statements). Lowest: `ingest/uk` 8%, `un` 11%, `ofac` 14%, `eu` 17% (the international sanctions parsers are essentially untested), `scheduler` 48%, `mail` 49%, `mobile.py` 68%, `app.py` 77%.
- 29 of 145 routes have no test hitting the path (22 mobile, 7 web), including `POST /alerts/bulk-dismiss`, `/console/org/{id}/customers`, mobile alert confirm/assign, mobile admin deactivate/reset-password.
- Five failing tests are provided in `proposed_tests/` (run with `-p tests.conftest` since the file lives outside `tests/`): bulk-dismiss four-eyes, submitted-report immutability, FIU "submitted" wording, `Cache-Control` on authenticated pages, and super-admin console access leaving audit rows. The MFA test in that file is already satisfied by master.
- Test smells worth fixing: `test_p40_adverse_media_async.py` does a real GDELT request inside the unit suite with a 30-second sleep loop and accepts "failed" as a pass; `test_p30_goaml_gate.py:43-48` swallows the validation error so the positive case cannot fail; several `status_code in [200, 403, 404]` assertions.

## Recommended order of work

1. **Today, no code**: `gcloud run services update amlkit --max-instances 1 --concurrency 80` in me-central1. This removes the split-brain risk (finding 3) and makes the in-memory login limiter coherent.
2. **Small PRs, one each**: rename `block content` to `block body` in the three templates (finding 2); make `datasets_fresh()` require at least one fresh *sanctions* list (EOCN, UN or OFAC) and surface failed sources as BREACH rows (finding 1); open SQLite with `check_same_thread=False` in `connect()` (finding 7); reject `POST /reports` unless status is `draft` (finding 5); route `bulk_dismiss_alerts` through `propose_disposition` (finding 6); refuse deactivating the last active MLRO and add reactivate (finding 8); add `@limiter.limit` to mobile login (finding 11); add `org_id` parameters to every `toolbox/tools.yaml` query (finding 10). (Finding 4's XFF fix is already on master — see Corrections above.)
3. **Deploy hygiene**: move the five secrets to Secret Manager with `--set-secrets`; install from `requirements.lock` in the Dockerfile; add `pip-audit`, `bandit` and `ruff` jobs; set Litestream `retention` and `snapshot-interval`; add an external uptime check on `/health` (options in [05-infra-api-workflow.md](05-infra-api-workflow.md) section A).
4. **Design pass**: darken `--ink-3`, bind labels to inputs, fix the FAB offset and admin row layout on phones, restore Alerts and Profile to navigation, make the nationality combobox keyboard-operable. The token system itself is good and does not need replacing.
5. **Ingest robustness**: OFAC is on the legacy treasury.gov path, EOCN and CIA are HTML/Gatsby scrapes, FATF silently falls back to a hardcoded list. Candidate replacements and supplements are in section B of the survey.

## Reproducing this review

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt playwright
AMLKIT_DB=/tmp/aml.db AMLKIT_BEHIND_PROXY=1 AMLKIT_DISABLE_AUTO_REFRESH=1 \
  AMLKIT_REGISTRATION_INVITE_CODE=<code> .venv/bin/python scripts/serve.py
.venv/bin/python -m pytest tests/ -q --ignore=tests/test_ocr.py
.venv/bin/python scripts/security_scan.py   # currently all false positives, see above
```

Lane scripts (probe*.py, flow_*.py, census.py, concurrency.py, capture*.py) and the 200-plus screenshots stayed in the review sandbox; the six in `evidence/` are the ones the top findings cite.
