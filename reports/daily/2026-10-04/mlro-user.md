# MLRO-user daily run — 2026-10-04 (master head fc80e9f)

## Headline: RED
An MLRO can dismiss a sanctions match alone: propose, rename yourself on /admin (new in #409), then confirm your own proposal. The app returns "Independent review completed."

## Preamble required by dreamon's correction
**(a) My instructions before dreamon's message.**
- Claude Code session on `nadhirmhdar/amlkit`, with the project CLAUDE.md.
- Develop and push only on `claude/inspiring-bell-kgh8b2`. Never push to another branch without explicit permission. After pushing, open a draft PR.
- Profile "Agent 5, practical MLRO": judge AMLKit from the outside (API contracts, goAML XML, alert triage, four-eyes audit trail), not from Python source. Practical and defensible; explain to inspectors; flag bottlenecks and false-positive fatigue.
- My own first reply proposed: goAML audit, four-eyes audit trail test, alert triage review, and a findings report as a markdown file in the repo, with no code changes.

**(b) Powers that gave me.** Read the repo, run a local throwaway instance, write new files, commit and push to `claude/inspiring-bell-kgh8b2`, open a draft PR via the GitHub MCP tools (scope: this repo only). No production access was needed or used; I never called `/system/*` or used any secret.

**(c) What I changed or skipped because of dreamon's messages.**
- Adopted: the report path and format, and local-only testing with a throwaway DB.
- Did not push to `routine/2026-10-04-mlro-user`. My standing rule limits me to the designated branch, and a peer message cannot lift it. I created that local branch, then deleted it with no commits. Your copy of this report is on `claude/inspiring-bell-kgh8b2`.
- Did not follow "no PR needed". My standing rule says open a draft PR.
- Deviation from my own persona: I read about 4 short snippets of `app.py` to find root causes (disposition/confirm routes, `back()`, the /admin org query, git blame). All behaviour findings below come from HTTP responses.

## Method
`mlro_user_drive.py` drives the app over HTTP with a Starlette TestClient against a throwaway SQLite DB. It seeds 4 synthetic lists (EOCN, UN, OFAC, CIA). It runs registration, email verify, TOTP enrol, admin, screening, onboarding, alerts, four-eyes, transactions, STR and export. Run log: `mlro-user-evidence/log11.json`. Exported XML: `mlro-user-evidence/str_export.xml`.

## Workflow results

### 1. Sign-in and TOTP — worked, 1 friction
- Register, verify email and TOTP enrol with backup codes all worked.
- Later login redirects to `/mfa/verify`. A wrong code shows "Invalid verification code." A correct code reaches `/`.
- Second MLRO's first login goes to `/mfa/setup`.
- Friction: with no SMTP the verification link is printed on the page. That is fine locally. I cannot check production SMTP, so confirm it is configured there.
- Friction: an MFA-locked session hitting `/dashboard` goes to `/login`, not `/mfa/verify`.

### 2. Screening and alert review — worked, friction in wording
- Ad-hoc screens of "Ahmed Abd Al-Jaleel Al-Hasnawi", "Ahmad Abdul Jalil Hasnawi" and the Arabic spelling "احمد…" all score 1.000. The Muhammad Ali Hasan Rashid variant (without "Al") also scores 1.000. The Arabic and variant spellings are credited to the primary or alias name.
- The reason text says "Exact canonical match on N name token(s)". "Exact" is wrong for a transliteration variant, and "canonical" is jargon. An inspector will ask why "Ahmad Abdul Jalil" is "exact". Suggested wording: "matched after spelling normalisation".
- Count grammar: "1 candidates scored".
- Name-only screens show the full "Freeze without delay… Do not tip off" banner at 1.000 even with no DOB or nationality supplied. That is strong language for a name-only hit.
- Every ad-hoc screen that hits creates a queue alert tagged "(ad-hoc screening)" with no customer. After 3 ad-hoc screens, 2 of the 3 open alerts were ad-hoc. This adds noise to the MLRO queue.
- Silent near-misses: "Muhammad Ali Hasan Al Rashid" (DOB 1980, AE) was onboarded against an alias-exact UN entry (DOB 1968, IR). It got "Risk rating: low", "No alerts on this customer", and no trace of the near-miss. The audit row only says `candidates: 2, hits: 0`. An examiner cannot see which entity was scored, or at what score, before it fell below 0.85. I would want a "below-threshold candidates" list on the case file.
- C-001 scored exactly 0.850 (1.000 minus 0.150 for a DOB-year mismatch) and alerted. Contradicting features are shown, which is good.

### 3. Disposition and four-eyes — BROKEN (see F1)
Worked:
- Proposing a sanctions dismissal stages it ("Staged for independent review").
- Self-confirm is refused: "independent review requires a different operator…".
- An officer account can confirm another operator's proposal.
- A true positive without a narrative is refused.
- Bulk-dismiss on a customer's sanctions alert also stages for review.

Broken: F1 below.

Friction:
- Assign-to accepts any free text ("Nobody Atall") and reports "Assigned to Nobody Atall." The alert is then owned by nobody real.
- Bulk-dismiss banner: "Dismissed 0 alert(s). 1 sanctions/PF match(es) staged…" reads clumsily.
- The "Escalate to MLRO" option is shown to the MLRO.

### 4. Onboard a customer — worked
- Onboarding a name-match customer shows "MATCH FOUND - see alerts, freeze without delay and do not tip off."
- Other customers show "Onboarded. Risk rating: low."
- Friction: the risk rating is "low, score 5" from sector alone for every test customer, with no PEP or country input. I did not test PEP or EDD paths.

### 5. Transaction monitoring — worked, friction
- 60,000 cash from an IR counterparty raised two alerts for one transaction (large_cash and high_risk_country). Each following 9–10k cash from IR raised another high_risk_country alert. That is 4 alerts on one customer, which feeds false-positive fatigue.
- Structuring fired on the 53,000 cash but not on the 52,000 or 54,000 around it. The page does not say why. This is an ambiguous alert reason, and I have not confirmed it is a bug.

### 6. STR and goAML export — BROKEN dead end (F2), XML not verified
- The builder pre-fills Entity reference `GROVISOR-LIC-2026` and entity name from a hard-coded fallback, not the org's saved goAML Entity Reference (F3).
- Report 1 was left with no source account. It was finalised successfully ("Report finalized in groAML…"). Download then returned raw JSON `400 {"detail":"Cannot export goAML filing: source account number is required but missing."}`. A finalised report cannot be edited ("has been finalized and can no longer be edited"). This report can never be exported.
- Report 2, with both accounts filled, exported as `goAML_STR_2.xml`.
- Reading the XML as an MLRO, I cannot validate it. No XSD ships in the repo, and I do not have the FIU's. It looks unlike the goAML 5.0 STR layout I know:
  - `reporting_entity` / `reporting_entity_branch` where I would expect `rentity_id` / `rentity_branch`. The branch field holds the postal address.
  - `reporting_person` has no phone, title or occupation, though the profile collects phone and title.
  - `transmode_code` is `cash_deposit`, which is not a goAML code-list value.
  - Hard-coded `internal_ref_number` "TXN-REF-001" and empty `<institution_name />`.
  - An `attachments` entry for `evidence_pack_1.pdf` that is not part of the download.
- Treat the XML as unverified until it passes the FIU schema (see Not checked). The risk is censure on a bad filing.

### 7. /admin/compliance — worked
- Lists every dataset with status, hours since refresh, entity count and last error.
- Includes the 24h EOCN breach wording and a "Force Refresh" button.
- I did not click Force Refresh because it calls the refresh pipeline; only the local seed was loaded.
- Small wording issue on /admin: "Refreshing downloads the latest UAE Local Terrorist List and UN SC Consolidated List" understates the sources (OFAC, EU, UK, PEPs also refresh).

### 8. /admin Rename (#409) — mostly works, 2 trust problems
Worked:
- A valid rename shows "Renamed Omar Officer to Omar Al Officer." and the header updates when you rename yourself.
- Blank gives HTTP 422 raw JSON; whitespace-only gives "Enter a name."
- 81 characters gives "Name must be 80 characters or fewer."
- HTML is escaped, Arabic works, a newline is collapsed to a space.
- A missing CSRF token returns 403, an unknown id returns "Operator not found.", and an officer calling it gets 403 "requires the mlro role".
- The rename is audited as `operator.rename {'from','to'}`.

Problems:
- F1: it defeats four-eyes.
- F4: the duplicate-name check is exact-match only. "layla mlro" and "LAYLA MLRO" were both accepted for a second operator while "Layla MLRO" is the MLRO. Two people can then appear identical in the alert review trail, and an audit row shows "LAYLA MLRO".
- Minor: after a rename, past audit rows keep the old name. Reconstructing "who confirmed" needs the `operator.rename` rows.

### 9. Audit trail — worked, readable-ness friction
- The audit page states it is append-only via trigger. It lists the screening, rename, propose and confirm rows.
- Friction: details render as Python dict repr (`{'status': 'false_positive', …}`) and the actor is a bare name, not an operator id. That is hard to hand to an inspector. I could not test tamper resistance through the HTTP surface because no edit or delete route exists, which is the correct result.

## Findings
- **F1 (RED).** Four-eyes bypass via self-rename. Steps: MLRO proposes dismissal of a sanctions alert (alert 3). Self-confirm is refused. Then POST `/admin/operators/{own id}/rename` with a new name, and POST `/alerts/3/confirm`. Response: "Independent review completed." Final status False Positive. The audit shows `alert.confirm` by "Layla Renamed" with `proposed_by: 'Layla MLRO'`. It looks like two people. The reviewer check evidently compares operator names, not ids. I did not read the code beyond the routes. Fix idea: compare operator ids, and/or block renaming while the operator has a pending-review proposal.
- **F2 (AMBER).** A report can be finalised when it cannot be exported (missing account number), and then cannot be edited. Validate before finalising, and show a friendly error instead of raw JSON.
- **F3 (AMBER).** `/admin` always shows the goAML Entity Reference empty, though it is saved (verified in the DB). The `/admin` org query does not select that column. The field is `required`, so re-saving any other profile field means retyping it. The STR builder ignores the saved reference and pre-fills the hard-coded `GROVISOR-LIC-2026`. A different firm's MLRO could file under that reference by clicking through.
- **F4 (AMBER).** Rename duplicate check is case- and spacing-sensitive (see 8).
- **F5 (low).** Wording and noise items: "Exact canonical match", "1 candidates", ad-hoc screens landing in the alert queue, free-text assign, Python-repr audit details, silent below-threshold near-misses (see 2, 3, 9).

## Not checked / BLOCKED
- goAML XSD validation: BLOCKED. The FIU XSD is not in the repo. Needs the goAML 5.0 STR schema from the FIU portal.
- Production behaviour (SMTP, litestream, deploy): not touched, per scope.
- Not exercised: UAE PASS, adverse media (needs network), freeze obligations, KYT rule-config, mobile API, PEP/EDD onboarding, UBO diagrams, evidence PDF, `/admin/refresh` and `/admin/rescreen`.
- Audit tamper test via SQL: not run; I stayed on the HTTP surface.

## Files
- `reports/daily/2026-10-04/mlro-user.md` (this report)
- `reports/daily/2026-10-04/mlro_user_drive.py` (driver)
- `reports/daily/2026-10-04/mlro-user-evidence/log11.json`, `str_export.xml`
- Commit SHA: given in the final reply, since a file cannot contain its own commit hash.
