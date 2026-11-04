# Compliance specialist — daily report 2026-11-04

**Instructions I ran under.** Standing role from Nadhir: Regulatory Compliance Specialist for Law 10/2025, Cabinet Resolution 134/2025, Cabinet Decision 109/2023 and Cabinet Resolution 74/2020, citation-grounded, additive only, no production access, no `/system/*` calls, no secrets. This run's routine prompt: review changes since the previous report against UAE AML/CFT obligations, then one previously not-checked item; push the report to `routine/<DATE>-compliance-specialist`, never master. The no-change shortcut did not apply because master moved. No message from dreamon arrived. `corpus/` and `citation_register.json` do not exist in the repo, so every Article is unverified (PLAUSIBLE). Not legal advice.

**Headline: AMBER (unchanged).** Two commits add a public landing page, an AML-law explainer and self-serve billing with no change to screening, freeze, reporting or retention logic, but the new public copy overstates two things (freeze scope and UAE PASS verification) and the 24-hour clock (CS-13) and PNMR (CS-14) are still open.

## What I did, with evidence

- `git ls-remote origin refs/heads/master` at 01:16 UTC on 2026-11-04: `c5da8aa06f192ec6ec3f90534b6c9264e4088da1` (`c5da8aa`). Previous report SHA was `938050fda10fe248b2cc327ea5d0770b5cb08f01`.
- `git log 938050f..origin/master`: two commits merged 2026-11-03: `c2191e5` #457 WP-26 (public landing page, AML-law explainer, always-on pricing, payment-gated self-serve sign-up with a 14-day trial) and `c5da8aa` #458 WP-27 (Stripe go-live wiring, annual prices, setup script, runbook). 38 files, +1,269/-139; 25 non-test, non-screenshot files.
- I read the whole non-test diff: `aml_law.html`, `landing.html`, `pricing.html`, nav and footer partials, `routers/auth.py`, `routers/public.py`, `cases/operators.py`, `billing/*`, `db.py`, `source-canary.yml`, `CLAUDE.md`, `scripts/stripe_setup.py` (scanned for committed secrets; none, the one pattern hit is a `sk_live_` prefix check in code).
- No screening, matching, freeze, review, reporting, retention or UBO source is touched. `sanctions_scope.py`, `cases/review.py`, `cases/manager.py`, `reporting/goaml.py` and `match/*` are identical to `938050f`.
- **Full test suite on `c5da8aa`** (detached worktree): **2860 passed, 2 skipped in 868 s, exit 0.** Supersedes `2810 passed, 2 skipped` on `938050f`. This session resumed on a fresh container, so I rebuilt my scratch venv with Python 3.11 from the repo's `requirements.txt` plus `requirements-dev.txt` (`pytest`, `hypothesis`); the first attempt exited before running because the old venv no longer existed, not because of a code failure.
- **Not-checked item taken this run:** the public statutory claims the new pages make, compared with the product's actual behaviour and with my earlier findings. Results below.
- PR list: #457 and #458 are the only PRs merged since #456. Drafts #411 and #412 remain open; #411 was updated at 01:16 UTC today. Neither reviewed.

## Public copy check (the not-checked item)

- **`aml_law.html`** is conservative: it names Federal Decree-Law No. 10 of 2025, Cabinet Resolution No. 134 of 2025, Cabinet Decision No. 109 of 2023 and Cabinet Resolution No. 74 of 2020 as instruments to read, gives no Article numbers, deadlines or penalties, and says it is general information, not legal advice. The four instrument names match the standing brief (existence and wording unverified without `corpus/`). Its duty table claims no PNMR support and makes no retention-period claim ("retention dates set per customer").
- **Overstated freeze scope.** `landing.html` ("Confirmed sanctions matches create freeze obligations that are tracked until they are executed") and the `aml_law.html` duty table ("Freeze obligations created from confirmed matches") are broader than the product: since #433 only confirmed matches on the UN Security Council and UAE Local Terrorist lists create one (`sanctions_scope.py`; EOCN position per my 2026-10-06 reading), and the same site's 24-hour guide says OFAC/EU/UK hits are not freeze or CNMR matters.
- **UAE PASS.** `landing.html` ("Verify identity with UAE PASS") and `aml_law.html` ("UAE PASS verification") present UAE PASS as a CDD capability. `amlkit/uaepass.py:16` still says "Staging only, for now" and `CLAUDE.md` still says the organisation has not completed UAE PASS's formal Service Provider onboarding and runs on the published POC sandbox credentials; I cannot see the deploy secrets (`UAEPASS_CLIENT_ID`, `UAEPASS_ENV`), so I cannot tell whether production credentials are now set.

## Findings

| ID | Severity | Status | Finding |
|---|---|---|---|
| CS-24 | MEDIUM | PLAUSIBLE | The public site advertises UAE PASS identity verification as a CDD feature while the repo's own documentation says the integration is sandbox-only until formal onboarding is done. Two linked gaps: (a) no template mentions sandbox or staging (`git grep` over `amlkit/web/templates` and `amlkit/api` finds the words only in code comments and `helpers.py`), and (b) `uaepass_verifications` rows record `match_status` and `user_type` but not which UAE PASS environment produced them, so a sandbox "verification" is indistinguishable in the file from a real one. Relying on it for identity verification would not meet a CDD verification duty (Res 134/2025 CDD articles, unverified). Fix options: show an "UAE PASS sandbox" badge and store the environment on the row while `UAEPASS_ENV` is `staging`, and soften the public wording until onboarding completes. |
| CS-25 | LOW | PLAUSIBLE | Public copy says confirmed sanctions matches create freeze obligations without limiting this to UN Security Council and UAE Local Terrorist list matches. Basis: Res 74/2020 Art 15 and Art 21 as cited by EOCN (unverified). Suggest "confirmed matches on the UN Security Council and UAE Local Terrorist lists". |
| N-7 | none | positive | Self-serve sign-up (Stripe mode) opens `/register-organization` without an invite code, but the new organisation is created `pending_payment`: it cannot create operators or customers until Checkout completes (`billing.limits.check_limit`), while reads, ad-hoc screening, reports and exports are never refused. Email verification still runs the MFA lock first (`routers/auth.py`: the billing redirect applies only when the MFA step returns no target), so the MLRO MFA requirement is not bypassed. The invite code is honoured only when self-serve is off. |
| CS-13 | HIGH | PLAUSIBLE (legal), CONFIRMED (code) — **open** | Unchanged: the 24-hour clock still runs from `freeze_obligations.identified_at`, set at confirmed disposition. Law 10/2025 Art 17, Res 74/2020 Art 15, Res 134/2025 Art 32 (unverified). |
| CS-14 (PNMR) | MEDIUM | CONFIRMED (code) — **open** | `SUPPORTED_REPORT_TYPES` is still `{"STR","SAR","FFR"}`. The new explainer does not promise a PNMR, but the 24-hour guide still describes one. |
| 3.1 | MEDIUM | PLAUSIBLE — **open** | The AED 55,000 cash threshold (Res 134/2025 Art 21) is still organisation-configurable. |
| INFO-7 | INFO | PLAUSIBLE | Open self-serve sign-up means any visitor can create an organisation with an MLRO account and, once the trial starts, onboard real customer data. The software vendor is not itself the reporting entity, so I treat vendor-side KYC of subscribers as a commercial decision, not an AML obligation, but the vendor should expect abuse (testing stolen identity data, sanctions-list probing) and keep the 10/minute auth rate limits and Stripe's payment gate as the controls. |

All other findings in earlier reports that no commit in this range touches stand as written (FATF handling, CS-4 Interpol, CS-18, the 5-versus-8-year retention question).

## BLOCKED / not checked

- **Primary legal text: BLOCKED**, unchanged. Three official hosts (`rulebook.centralbank.ae`, `uaelegislation.gov.ae`, `fatf-gafi.org`) refused this environment's egress on 2026-10-06; not retried or bypassed. To unblock: provide the official PDFs of the four instruments as `corpus/` plus `citation_register.json`.
- **UAE PASS production status:** not checkable; it depends on GitHub secrets and repository variables I do not have (and must not read). Someone with repo settings access should confirm whether `UAEPASS_ENV` is `production` with real credentials.
- Not re-verified individually: CS-5 (refresh cadence), CS-15, CS-16.
- Not read line by line: `scripts/stripe_setup.py` logic, the Stripe webhook handling beyond the `pending_payment` change, CSS, screenshots, the runbook.
- Drafts #411 and #412: not reviewed.
- Production: not checked.

## Files and commit

`reports/daily/2026-11-04/compliance-specialist.md` on `routine/2026-11-04-compliance-specialist`, created from `origin/master` `c5da8aa`. The commit SHA is in the final reply (a commit cannot name its own SHA).
