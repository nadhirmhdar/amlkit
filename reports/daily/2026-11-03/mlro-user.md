# mlro-user daily report — 2026-11-03

**Headline: AMBER** — master moved to 938050f (five commits, #452–#456, including a 5,000-line router split); all 33 of my earlier workflow walks still pass and the targeted fixes work, with one small gap left in the self-owner check.

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside. LOCAL seeded instance only; no production, no /system/*, no secrets; additive only. Source read only to see what the new commits changed (commit messages, unlock handler) and to locate routes.
- Report to branch `routine/2026-11-03-mlro-user` (never master) and as final reply. No dreamon messages today.
- Master changed: `git ls-remote origin refs/heads/master` = `938050fda10fe248b2cc327ea5d0770b5cb08f01` (previous report: e8ddf26). Highest PR ref now 456. Commits: #456 WP-18 split `api/app.py` into `routers/` (pure move), #455 WP-22 UBO structure guard, #453 WP-25 identity/auth residuals, #452 WP-24 name-screening residuals, #454 WP-23 obligation wording, ops replica state, two-step self-unlock, operator-name hardening. Not the shortcut.

## What I did (evidence: `mlro-user-evidence/log_wave3.json` and the other logs; driver `mlro_user_drive.py`, mode `wave3`, plus all earlier modes)
1. **Regression of the router split (#456):** re-ran all 33 earlier driver modes against 938050f. All exit 0, no tracebacks. I compared their output line by line with yesterday's run: the only differences are (a) `unicode`: "extra middle token" now matches (a fix, below), (b) `loginlock`: locked accounts now show a message about the unlock email (below), (c) `docs`: a cross-organisation check returned 403 `mfa_required` instead of 404 because my driver reused a TOTP code within the same 30-second window; the app correctly refuses a reused code. After waiting for a fresh window the check returns 404 as before.
2. **Name screening (#452):** Latin names with Cyrillic look-alike letters, "Al Hasnawi" split or joined, an extra middle name, Urdu yeh (ی) and Persian kaf (ک) in Arabic names all match the listed person. An unrelated name does not.
3. **Operator names (#454):** a name containing HTML is stored escaped; control characters, empty and over-120-character names are refused with clear messages.
4. **UBO structure guard (#455):** adding the customer itself as its own owner is refused ("A customer cannot be recorded as its own beneficial owner"), including with extra spaces.
5. **Two-step self-unlock (#454):** opening the emailed link (GET) only shows a confirmation page and does not use the token (it stays live; the account stays locked, as an email scanner would leave it). Posting the confirmation unlocks; posting again is refused; login then works.
6. **Unlock mail not deliverable (#453):** with no SMTP configured the 8th wrong password now says the account is locked and the unlock email could not be sent, instead of leaving the user guessing.

## Findings
- **UBO1b (low, CONFIRMED):** The self-owner check misses a dotted legal-suffix variant. "GULF HOLDINGS L.L.C." was accepted as a 20% owner of "Gulf Holdings LLC". Spacing and case variants are caught; punctuation inside the suffix is not.
- **UBO2 (info, CONFIRMED):** 60 consecutive owner rows were accepted on one customer; I did not reach the row cap, so its value is unverified (BLOCKED for the limit itself).
- **Fixed since last report:** N3/F2 name variants (homoglyphs, Urdu letters, split/joined/extra tokens), UBO1 (plain self-owner), UL1 (undeliverable unlock mail now explained), CR-30 (link scanners can no longer burn the unlock token), O1 (operator-name injection).
- **Behaviour change to note (not a defect):** the TOTP replay guard means the code used at enrolment cannot be reused for the first mobile verify within the same 30 seconds; a test or script that does so is refused with "Invalid verification code".
- Still open from earlier reports: F4, TA2, TA3, high-risk-country field accepts non-country text, E2-E5, LN1, SE2, PR5 (officer may complete a periodic review), and the other lows. Not re-checked today unless listed above.

## BLOCKED / not checked
- Rate limiting (my driver disables the limiter), HSTS (needs an HTTPS run behind a proxy).
- UAE PASS identity-reuse flag and SSO lock handling (#453): inert without UAE PASS credentials.
- UBO row cap and depth/cycle limits beyond a single self-owner (needs multi-level entity data); retention (#444), billing (#448), monitoring scripts (#450), goAML placeholder removal (#447): not walked in depth.
- goAML XSD validation, adverse media (GDELT), tesseract OCR success path, SMTP delivery.

## Files and commit
- `reports/daily/2026-11-03/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*.json`
- Branch `routine/2026-11-03-mlro-user`; commit SHA in the final reply.
