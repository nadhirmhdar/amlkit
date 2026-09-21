# AMLKit — Implementation Plan

Last updated: 2026-09-21. Single source of truth for all complex, multi-step work on AMLKit.
Bug-sized work stays in GitHub issues; this file orders it and adds the research/design work
that has no issue yet.

## How to read this file

- **[#nnn]** — existing open GitHub issue. Priorities preserved from their labels.
- **[NEW]** — requirement added 2026-09-21 with no issue yet.
- **[DONE PR-ui]** — closed by the responsive/avatar PR on branch `claude/kind-cerf-dzibnq`.
- **[HUMAN]** — needs a decision from the owner before work can start; do not assume.
- Phases are ordered by dependency. Within a phase, items are ordered by severity, then by the
  order they were raised.

## Sources merged

1. Open GitHub issues as of 2026-09-21 (16 after the nine bot-generated health/triage issues
   were closed today). Issues #85 EU FSF token and #84/#83 merge are listed but **deliberately
   not queued** — owner to handle.
2. The previous `PLAN.md` (single TDD plan for #98). #98 was closed by PR #159 — retired.
3. The Hermes multi-agent audit plan v2.1 (kept outside the repo at
   `AMLKit-Audit/2026-09-20_amlkit-hermes-kanban-audit-plan-v2.1.md`); referenced, not copied.
4. New requirements list received 2026-09-21 (UI/UX, greeting/timezone, dashboard, audit, APIs,
   client data, comparable products, accessibility, local data, privacy/cookies/ads,
   Stripe, roadmap).

**Not merged:** the p-/t-numbered Todo and the Marketing/Investment/Legal boards are not in
this repository. When that list is pasted in, merge it here per the rules in "Integration
rules" below.

## Integration rules (applied, and to apply on future merges)

- Read the existing list first; update an existing item rather than adding a near-duplicate.
- Keep every still-valid item; never delete work to shorten the list.
- Preserve existing priorities unless a dependency or severity reason is stated inline.
- Never present planned functionality as existing.

## Ground truth established while building this plan

These are facts from the code, cited so later phases start from evidence, not memory.

| Topic | Finding | Where |
|---|---|---|
| Top-left "☰" button on desktop | A late `.no-print { display:block }` overrode `display:none/flex` on `.nav-hamburger`, `.sidebar`, `.desktop-topnav`; the hamburger appeared on desktop and did nothing useful, and the avatar chip fell to the left. Fixed. | `app.css` (rule removed) |
| Greeting | Uses a fixed UTC+4 offset, explicitly "cosmetic"; no per-user or per-org timezone exists anywhere in the schema | `api/app.py:897-908` |
| Local browser data | No `localStorage`, `sessionStorage`, or IndexedDB use in `amlkit/web/` | grep |
| Cookies | Session cookie: `HttpOnly`, `SameSite=Lax`, `Secure` only when `AMLKIT_BEHIND_PROXY=1`; a 60 s flash cookie with the same flags | `api/app.py:277-315` |
| Third-party scripts / analytics / ads | None. Only external reference is Google Fonts, and the CSP (`style-src 'self' 'unsafe-inline'`) blocks it, so the Manrope font silently falls back | `base.html:7-9`, browser console |
| Stripe / billing | No code, schema or tests | grep |
| Policy pages | `policies.html` (org AML policies), `about.html`. No privacy, terms, or cookie templates | `web/templates/` |
| Audit-log access | `/audit` requires role `mlro`; console routes require super-admin | `api/app.py:1712-1759` |
| Retention | Logic and copy use 10 years; a stale comment at `db.py:240` says 8 | see #78, #79 |
| Test suite (local) | Two `test_csp_no_inline_scripts` failures are pre-existing on `master` (`customer.html`); `test_ocr.py` needs the `passporteye` wheel | — |

---

## Phase 0 — Discovery / Verification

Research and inspection only; no product changes except the two bug fixes already landed.

| # | Item | Status / notes |
|---|---|---|
| 0.1 | [DONE PR-ui] Investigate the non-working top-left corner button | Root-caused and fixed (see ground truth) |
| 0.2 | [#222] CI repeatedly breaks on `master` from untested/syntax-error commits | Add a required "Tests" status check on `master`; document `scripts/pre_pr_check.py` in CONTRIBUTING; [HUMAN] enable branch protection |
| 0.3 | [#40] Refresh error (low) | Reproduce on current `master` with `scripts/refresh.py`; close or re-scope |
| 0.4 | [NEW] Greeting/timezone discovery | Confirm no timezone field exists (org or operator); list every place that renders a local time (greeting, `hours_since_identified`, deadlines, audit timestamps) |
| 0.5 | [NEW] Local-data discovery | Enumerate cookies, cache headers on API responses, downloaded files (CSV/XML/PDF exports), service-worker/offline (none expected) |
| 0.6 | [NEW] Terminology inventory | Grep all user-visible strings for `MLRO`, `Mlro`, `mlro`, "compliance officer", "Admin Settings", "Audit Trails"/"Audit trail" and list inconsistencies with file:line |
| 0.7 | [NEW] Comparable-product research | Collect public privacy, data, retention, security, residency, cookie, terms and subprocessor pages of 5–8 AML/KYC SaaS products; produce a benchmark matrix. **Benchmark only; never copy wording** |
| 0.8 | [NEW] Accessibility legal research | UAE requirements (Federal Law No. 29 of 2006 as amended, TDRA digital-accessibility guidance) and US (ADA Title III case law, Section 508); WCAG 2.2 AA as the practical benchmark. Record which are binding vs. advisory |
| 0.9 | [NEW] API inventory | List every outbound call today (`ingest/*`, `screening/adverse_media.py` GDELT, `ai/gemini.py`, `mail.py`, `storage.py` GCS) with provider, purpose, data exchanged, auth, cost, limits, failure handling, security implications |
| 0.10 | Hermes multi-agent audit, Round 1 | Runs per audit plan v2.1 (read-only). Its confirmed findings enter this plan as issues via the human gate |
| 0.11 | Baseline test run | Record base-red tests on `master` before each phase's work starts |

## Phase 1 — Critical Bugs and Core UX

| # | Item | Notes |
|---|---|---|
| 1.1 | [#141] (high) Confirmation message claims report submitted to UAE FIU when no transmission occurred | Compliance/UX deception — fix copy and state model first |
| 1.2 | [#142] (high) goAML XML hardcodes default reporting entity (Grovisor, Dubai HQ) | Multi-tenancy correctness; read entity from the org record |
| 1.3 | [DONE PR-ui] Move the operator chip to a `G` avatar in the top-right; name/role/org in its dropdown | Desktop now matches phone |
| 1.4 | [DONE PR-ui] Remove the sidebar Alerts button and Alerts nav link; alerts live in Dashboard | `/alerts` route kept; Dashboard nav highlights on it |
| 1.5 | [DONE PR-ui] Remove the stray em dash in the stale-source banner | `base.html` |
| 1.6 | [NEW] Review every Home button; keep arrows only where they mean navigation | Today: three action cards and the alerts pill all carry `→`. Cards are links, so the arrow is redundant with the whole-card affordance — decide per card; remove decorative ones |
| 1.7 | [NEW] Standardise MLRO terminology | From 0.6. Pick one form per context (role tag `mlro`, label "MLRO") and fix `admin.html:36,42,63,126` and all templates |
| 1.8 | [NEW] Greeting logic | Decide source of truth [HUMAN]: browser timezone (render greeting client-side from `Date`), operator setting, or org setting. Recommendation: browser timezone client-side — no location collection, correct when travelling, DST-safe; fall back to org timezone when JS is off |
| 1.9 | [NEW] Greeting tests | Device timezone change, browser timezone change, travel between countries, DST transitions, JS disabled. Assert no precise location is collected or stored |
| 1.10 | [NEW] Overall UI/UX consistency pass | Spacing, button styles, headings, empty states, tag colours across all templates; produce a short findings list before changing anything |
| 1.11 | [NEW] Bug-report / feedback experience | `feedback-btn` modal: match AMLKit tokens, add page context (already sent), confirm delivery path and success/error states |
| 1.12 | [#77] (low) Show organisation name in the UI | Partially done (sidebar + dropdown show it); verify every page, then close |
| 1.13 | [DONE PR-ui] Self-host the Manrope font | CSP `font-src 'self'` blocked Google Fonts → production rendered in the fallback font. Variable woff2 (latin + latin-ext) now under `/static/fonts` with `@font-face`; smoke test in `test_static_assets.py` |
| 1.14 | [NEW] Tablet layout decision [HUMAN] | 681–960 px keeps the hamburger sidebar; phone chrome (tab bar) applies ≤ 680 px. Extend phone chrome to tablets, or keep? |

## Phase 2 — Security, Audit and Data Protection

| # | Item | Notes |
|---|---|---|
| 2.1 | [#99] (medium) `POST /admin/*` returns 200 for officer role instead of 403 | RBAC response ambiguity |
| 2.2 | [#143] (medium) Rate limiter resolves link-local proxy IP on Cloud Run, collapsing limits across tenants | Note `tests/conftest.py:41` disables the limiter suite-wide; add runtime probe |
| 2.3 | [#78] (high) Verify legally required retention period (8 vs 10 years) | [HUMAN]/compliance source needed; then fix `db.py:240` comment |
| 2.4 | [#79] (high) Extend `retention_until` dates stored under the old 5-year rule | Depends on 2.3 |
| 2.5 | [#71] (high) Static check for tenant-isolation conventions (`org_id` scoping) | Lint rule + CI job |
| 2.6 | [NEW] Complete audit-log review | Enumerate all `db.audit()` call sites; map to compliance-critical events (CDD decisions, dispositions, freeze actions, STR export, role changes, login/logout/failed login, exports/downloads, retention purge); list missing ones |
| 2.7 | [NEW] Audit-log access controls and tenant isolation | Verify `/audit` and CSV export scope by `org_id`; super-admin cross-org access is logged |
| 2.8 | [NEW] Sensitive data in audit rows | Check no secrets, full ID numbers, or document contents are written to `audit`; define masking |
| 2.9 | [NEW] Audit-log integrity | Prove append-only triggers hold for every role including super-admin; consider hash chaining |
| 2.10 | [NEW] Client-data inventory | What AMLKit collects, processes, stores, transmits — per table/column and per outbound API (from 0.9); classify AML/KYC/CDD/UBO/screening/risk data |
| 2.11 | [NEW] Protection gap analysis | Encryption at rest (SQLite file, GCS objects, ID documents), access control, tenant isolation, retention, deletion, masking, backups (`backup-verify.yml`), logging. Decide what needs adding |
| 2.12 | [NEW] Local browser data | Test logout, session expiry, browser restart, user switch on one device; confirm exports are the only client-side persistence; add `Cache-Control: no-store` to authenticated responses if missing |
| 2.13 | [#82] (low) CSP: remove `'unsafe-inline'` from `script-src` | Pre-existing `customer.html` inline script/`onclick` must go first (`test_csp_no_inline_scripts` is red on `master`) |
| 2.14 | PR #197 MFA TOTP gate | Rebase onto the `mfa_*` DDL now on `master` (#219); blockers: no login-time enforcement, plaintext TOTP secret, no re-auth on `mfa_disable` |
| 2.15 | PR #112 CSV formula injection (mobile API) | Ready for review; merge when reviewed |

## Phase 3 — Accessibility

Depends on 0.8 for the legal baseline; WCAG 2.2 AA is the working benchmark.

| # | Item | Notes |
|---|---|---|
| 3.1 | Colour contrast audit | All tokens in `app.css :root`; `--ink-3` (64% L) on `--bg` is the likely failure for small text — measure |
| 3.2 | Light text → darker grey where it fails | Sub-labels, `.muted`, `.small`, card subtitles |
| 3.3 | Keyboard navigation | Tab order through sidebar, avatar menu, tab bar, modals; Escape closes menus (exists) |
| 3.4 | Focus states | `:focus-visible` exists for links/selects/textarea; add for buttons and inputs |
| 3.5 | Screen-reader compatibility | Landmarks (exist), `aria-expanded` on menus (exists), live regions for async results, table/grid semantics on `.grid-table` label/value stacks |
| 3.6 | Semantic structure | One `h1` per page, heading order, lists |
| 3.7 | Accessible names for icon-only controls | Avatar button (has `aria-label`), feedback button (has), action-card arrows (decorative → `aria-hidden`) |
| 3.8 | Forms and error messages | `aria-describedby` for errors, required markers, error summary focus |
| 3.9 | Responsive/mobile accessibility | 44 px targets (tested for tab bar and avatar), zoom to 200%, orientation |
| 3.10 | Existing coverage | Keep `test_p82_accessibility.py`, `test_p83_screen_reader.py`, `test_p84_mobile_accessibility.py`, `test_103_aria_labels.py` green; extend rather than replace |

## Phase 4 — Dashboard / Product Experience

| # | Item | Notes |
|---|---|---|
| 4.1 | [#72] (medium) Warn operators when a sanctions source is stale or failing | Banner exists for MLRO; extend to officers and to the dashboard |
| 4.2 | [NEW] Alerts/Dashboard experience review | With the sidebar Alerts entry removed, the dashboard is the only alerts surface — verify queue, filters, disposition flow, four-eyes state are discoverable |
| 4.3 | [NEW] Metrics that can be derived from existing data | Candidates with a real source: open alerts by category/severity, alert age, disposition turnaround, screening volume, customers by risk tier, overdue reviews, freeze obligations vs 24 h, dataset freshness. **No metric without a query behind it** |
| 4.4 | [NEW] Visualisations | Only for 4.3 metrics; small multiples over dashboards-for-show; follow the `dataviz` skill palette rules |
| 4.5 | [NEW] Investor-facing visibility | Separate, aggregated, tenant-anonymised view — never inside the operator dashboard. [HUMAN] confirm audience and what may be shown |
| 4.6 | Do not create fake, decorative, or unsupported metrics | Rule, not task |

## Phase 5 — Settings / Administration

| # | Item | Notes |
|---|---|---|
| 5.1 | [NEW] "Admin Settings" → "Settings"? | Review current `admin.html` structure and 0.7 comparables; [HUMAN] decide naming and whether operator-level settings (timezone from 1.8, notification prefs) need a separate page |
| 5.2 | Roles and administrative controls | Officer / MLRO / super-admin matrix documented; align with #99 fix |
| 5.3 | [#73] (low) Move business logic out of `api/app.py` (~2,280 lines) | Tech debt; do incrementally alongside 5.1 |

## Phase 6 — APIs / External Integrations

| # | Item | Notes |
|---|---|---|
| 6.1 | [#85] (critical) Register EU FSF token, set `AMLKIT_EU_FSF_TOKEN` | **Owner action** — deliberately not queued |
| 6.2 | [#84] (medium) Merge #83 and set `AMLKIT_REGISTRATION_INVITE_CODE` | **Owner action** — deliberately not queued |
| 6.3 | [NEW] Categorise all APIs from 0.9 | Mandatory / Recommended / Optional / Future. Mandatory only when AMLKit cannot meet a regulatory obligation without it (EOCN, UN, OFAC, EU, UK lists; goAML schema). PEP (CIA), GDELT, OpenSanctions, Gemini, GCS, SendGrid are not automatically mandatory |
| 6.4 | [NEW] Mandatory API list for V1 | Output of 6.3 with provider, purpose, data exchanged, auth, cost, limits, failure handling, security |
| 6.5 | [NEW] Integration architecture | Retry/backoff (exists in `ingest/base.py`), staleness policy, secrets handling, per-tenant tokens where providers require them |

## Phase 7 — Billing / Stripe

Nothing exists today. Design before code; keep billing data physically separate from AML data.

| # | Item |
|---|---|
| 7.1 | [HUMAN] Pricing tiers, trial length, usage units (screenings? customers? seats?) |
| 7.2 | Subscription lifecycle: create, upgrade/downgrade (proration), cancellation, failed payment (dunning, grace period, read-only mode) |
| 7.3 | Usage limits, consumption tracking, overage handling |
| 7.4 | Organisation-level billing (one Stripe customer per org) |
| 7.5 | Usage/consumption dashboard and cost-management dashboard (org admin only) |
| 7.6 | Separation review: billing tables/keys never join AML tables; Stripe never receives customer (KYC) data |
| 7.7 | Webhook security, idempotency, audit events for billing changes |

## Phase 8 — Privacy / Cookies / Ads

| # | Item | Notes |
|---|---|---|
| 8.1 | [NEW] Ads / Advertising & Tracking review | Ground truth: no ads, no ad-tech, no analytics, no tracking scripts, no advertising cookies, no third party receives user/device data for advertising or measurement. Re-verify at each release |
| 8.2 | [NEW] Consent / cookie-preference controls | Only strictly-necessary cookies (session, CSRF, flash) → no consent banner required; document the reasoning. Revisit if analytics is ever added |
| 8.3 | [NEW] Privacy Policy, Terms of Use, Cookie Policy | Do not exist as pages. Draft from 0.7 benchmark and 2.10 inventory; wording must reflect actual behaviour (no ads, no analytics, UAE/GCP hosting, retention per 2.3) |
| 8.4 | [NEW] Cookie Preferences page / notices | Only if 8.2 concludes one is needed |
| 8.5 | Rule | Never add advertising because comparable sites have it; never imply ads exist when they don't |

## Phase 9 — Product Roadmap / Commercial Presentation

| # | Item | Notes |
|---|---|---|
| 9.1 | Roadmap diagram | Lanes: AML/CFT, CDD/KYC, UBO, Screening, Risk, Alerts, Cases, Reporting, Audit, Integrations, Mobile, Analytics, Billing, AI. Columns: Current / Near-term / Planned / Future |
| 9.2 | "Current" is populated only from shipped code with tests | e.g. MFA (#197) is Near-term until merged; Stripe is Planned; investor analytics is Future |
| 9.3 | Investor-facing product presentation | Built from 9.1 and 4.5; every "current" claim traceable to a route or test |

## Phase 10 — Final QA

| # | Item |
|---|---|
| 10.1 | Full regression (pytest + Playwright at 1440/900/390 px) |
| 10.2 | Admin role walkthrough; MLRO role walkthrough; officer role walkthrough |
| 10.3 | Accessibility re-check (Phase 3 checklist) |
| 10.4 | Security re-check (Phase 2: RBAC, tenant isolation, audit integrity, CSP) |
| 10.5 | Privacy/local-data re-check (2.12, 8.1) |
| 10.6 | Billing and integration tests (Phases 6–7) |
| 10.7 | Hermes audit Round r+1 on the release candidate; Certificate A required, Certificate B targeted |

---

## Open decisions for the owner

1. Greeting timezone source of truth (1.8).
2. Tablet layout: extend phone chrome to ≤ 960 px or keep the hamburger sidebar (1.14).
3. Retention period source document (2.3).
4. "Settings" naming and page structure (5.1).
5. Pricing/trial/usage model (7.1).
6. Investor visibility audience and permitted aggregates (4.5).
7. #85 and #84 remain owner actions.
8. Paste the external p/t Todo and board items so they can be merged here.
