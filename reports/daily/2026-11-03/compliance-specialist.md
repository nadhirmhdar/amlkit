# Compliance specialist — daily report 2026-11-03

**Instructions I ran under.** Standing role from Nadhir: Regulatory Compliance Specialist for Law 10/2025, Cabinet Resolution 134/2025, Cabinet Decision 109/2023 and Cabinet Resolution 74/2020, citation-grounded, additive only, no production access, no `/system/*` calls, no secrets. This run's routine prompt: review changes since the previous report against UAE AML/CFT obligations, then one previously not-checked item; push the report to `routine/<DATE>-compliance-specialist`, never master. The no-change shortcut did not apply because master moved. No message from dreamon arrived. `corpus/` and `citation_register.json` do not exist in the repo, so every Article is unverified (PLAUSIBLE). Not legal advice.

**Headline: AMBER (improving).** Five more commits close CS-23 and answer my open UBO-cycle question, and the 5,000-line `app.py` split is mechanically faithful, but the 24-hour clock (CS-13) and PNMR (CS-14) are still open.

## What I did, with evidence

- `git ls-remote origin refs/heads/master` at 01:16 UTC on 2026-11-03: `938050fda10fe248b2cc327ea5d0770b5cb08f01` (`938050f`). Previous report SHA was `e8ddf262a73c1f0fda99a174871d879e35fcbbcf`.
- `git log e8ddf26..origin/master`: five commits merged 2026-11-02, PRs #452 to #456: #454 dataset-first obligation wording, two-step self-unlock, dev requirements; #452 name-screening residuals; #453 identity and auth residuals; #455 UBO structure guard; #456 split of `api/app.py` into `routers/` and `helpers.py`. 84 files, +9,320/-4,822; 42 source files (24 new router/helper files).
- Compliance-relevant source I read in full: `screening/pf.py`, `cases/review.py`, `cases/manager.py` (UBO guard, UAE PASS reuse), `match/scorer.py`, `names/arabic.py`, `names/confusables.py` (new), `db.py` migration, `queries.py`, `mail.py`.
- **Not-checked item taken this run: is #456 really a pure move?** The PR title says so and the diff is too large to read. I checked it mechanically instead: parsed the old `app.py` (`e8ddf26`, 162 top-level functions) and every new `app.py`/`routers/*.py`/`helpers.py` file with `ast`, and compared function bodies with decorators removed and relative-import depth normalised.
  - 157 of 162 functions are identical. No function is missing and none is defined twice.
  - The 5 that differ are exactly the intended WP-25 changes: `uaepass_operator_callback` (adds a password-lock refusal for SSO), `self_unlock` (now requires CSRF; new `self_unlock_confirm` and `_unlock_invalid_page`), `uaepass_customer_callback` (identity-reuse notice), `console_view` and `admin_view` (extra template values).
  - Routes: 130 before, 131 after; the only addition is `POST /unlock/{token}`. Decorator arguments (rate limits, response classes) are identical for every function except `self_unlock`, whose limiter became `shared_limit('10/minute', scope='unlock')`.
  - App-level wiring is intact in the new `app.py` (377 lines): `SelectiveGZipMiddleware`, the `RateLimitExceeded` handler, the three `@app.middleware("http")` hooks (including the CSP / X-Frame-Options headers), the static mount, the mobile and billing routers, and 20 `include_router` calls for the new routers.
  - The freeze/CNMR scope gate is unchanged: `freeze_obligation_file_ffr` in `routers/freeze.py` still imports `freeze_obligation_in_scope`, and `system_check_freeze_obligations`, `admin_rule_config_get/post`, `report_submit`, and `alert_confirm` are byte-identical apart from import depth.
- **Full test suite on `938050f`** (detached worktree, scratch venv with `hypothesis` installed): **2810 passed, 2 skipped in 1,567 s, exit 0.** Supersedes `2651 passed, 2 skipped` on `e8ddf26`.
- PR list: draft #411 and draft #412 remain open; #412 updated at 01:04 UTC today. Neither reviewed.

## Findings

| ID | Severity | Status | Finding |
|---|---|---|---|
| CS-23 | LOW | **Closed in code** | #454: `obligation_note()` now tests the dataset first, so an entry from a non-UN / non-UAE-local list never reads "freeze", whatever its proliferation or terrorism category; `obligation_for_category()` does the same for the `proliferation`, `terrorism` and `sanction` categories. With no dataset the freeze wording is kept (fail-safe, since a UN listing cannot be ruled out). This completes CS-19. |
| UBO cycle prevention | MEDIUM | **Confirmed present** (legal basis PLAUSIBLE) | #455 adds `_check_ubo_structure`, called by `add_ubo` before any insert: refuses a customer recorded as its own beneficial owner (casefolded and canonical-name match, English and Arabic), refuses a parent that does not belong to the customer, walks the parent chain and refuses a circular chain, caps depth at 10 levels and rows at 200 per customer. `_identified_ownership` is now iterative, with the same cycle-contributes-zero behaviour. This answers the open question in my 2026-11-02 report (Dec 109/2023, articles unverified). Caveat: `add_ubo` only appends leaves under an existing parent, so a fresh cycle cannot be made through it anyway; the walk protects legacy rows and bounds depth. |
| Name matching | MEDIUM | **Improved** (PLAUSIBLE) | #452 closes several screening-evasion routes for lists where a miss means a missed freeze: Cyrillic/Greek homoglyph folding (`names/confusables.py`, applied only to tokens that are Latin in intent, so genuine Cyrillic names are left alone and stay flagged `unscreenable`), Urdu yeh barree mapping, repair of a name split by a separator (`BI LAL`) using blocking-key concatenation and a short-fragment merge, and token containment (a listed name fully contained in a longer query now scores up to 0.97, never 1.0). Containment only ever raises a score. Residual: a longer query can now match a listed name at a higher score, so false-positive volume may rise; tuning is `tests/test_matching.py`'s job. Screening effectiveness basis: Res 74/2020 and Law 10/2025 TFS articles (unverified). |
| Four-eyes | MEDIUM | **Tightened; one residual** | #453/`cases/review.py`: confirmation now requires an operator id (a call without one is refused) and compares ids only; the old display-name fallback is gone. Residual (INFO): a legacy proposal with NULL `operator_id` counts as "proposed by unknown", so any confirming operator with an id, including the proposer, can confirm it. Only proposals written before the id column existed (before #426, 2026-10-06) and still pending are affected; `scripts/backfill_proposal_operator.py` and `check_legacy_proposals.py` exist to clear them. Run the check before relying on four-eyes for old pending proposals. |
| Identity reuse | INFO | CONFIRMED (code) | #453: the same UAE PASS identity verified against two customers of one organisation opens an `identity_reuse_alerts` row (org-scoped; the alert names the other customer id, never the Emirates ID), suppresses the customer-file backfill, and shows a notice. SSO sign-in now honours the password lockout. |
| CS-13 | HIGH | PLAUSIBLE (legal), CONFIRMED (code) — **open** | Unchanged: the 24-hour clock still runs from `freeze_obligations.identified_at` (set at confirmed disposition); nothing in this range touches it. Law 10/2025 Art 17, Res 74/2020 Art 15, Res 134/2025 Art 32 (unverified). |
| CS-14 (PNMR) | MEDIUM | CONFIRMED (code) — **open** | `SUPPORTED_REPORT_TYPES` is still `{"STR","SAR","FFR"}`; the public guide still describes a PNMR. |
| 3.1 | MEDIUM | PLAUSIBLE — **open** | The AED 55,000 cash threshold (Res 134/2025 Art 21) is still organisation-configurable; the routes only moved (`admin_rule_config_get/post` byte-identical). |
| INFO-6 | INFO | CONFIRMED (code) | Unlock is now two-step: the emailed link opens a confirmation page and a CSRF-protected POST redeems it, so a mail scanner or link preview that fetches the URL cannot burn or use the token. It clears the password lock only, never the MFA lock. |

All other findings in earlier reports that no commit in this range touches stand as written (FATF handling, CS-4 Interpol, CS-18, retention 5-versus-8 years).

## BLOCKED / not checked

- **Primary legal text: BLOCKED**, unchanged. Three official hosts (`rulebook.centralbank.ae`, `uaelegislation.gov.ae`, `fatf-gafi.org`) refused this environment's egress on 2026-10-06; not retried or bypassed. To unblock: provide the official PDFs of the four instruments as `corpus/` plus `citation_register.json`.
- Not re-verified individually: CS-5 (refresh cadence), CS-15, CS-16.
- Not read line by line: `auth.py` (operator-name look-alike key, unlock flow), `ops.py`, `cases/operators.py`, the 24 new router files beyond the AST comparison above, templates.
- The AST comparison covers top-level functions and their decorators; it does not cover module-level code ordering inside the routers (for example a dependency declared at router level). I saw no `dependencies=` on any `APIRouter` in the files I listed, but did not exhaustively verify.
- Drafts #411 and #412: not reviewed.
- Production: not checked.

## Files and commit

`reports/daily/2026-11-03/compliance-specialist.md` on `routine/2026-11-03-compliance-specialist`, created from `origin/master` `938050f`. The commit SHA is in the final reply (a commit cannot name its own SHA).
