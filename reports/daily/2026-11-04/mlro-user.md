# mlro-user daily report — 2026-11-04

**Headline: AMBER** — master moved to c5da8aa (two commits: new public landing/AML-law/pricing pages and Stripe go-live wiring, #457–#458); every MLRO workflow I walk still passes, and the one thing I would challenge is a marketing claim about UAE PASS.

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside. LOCAL seeded instance only; no production, no /system/*, no secrets; additive only. Source read only to see what the new commits changed and to locate routes.
- Report to branch `routine/2026-11-04-mlro-user` (never master) and as final reply. No dreamon messages today.
- Master changed: `git ls-remote origin refs/heads/master` = `c5da8aa06f192ec6ec3f90534b6c9264e4088da1` (previous report: 938050f). Highest PR ref now 458. Commits: #457 WP-26 public landing, AML-law explainer, always-on pricing, payment-gated self-serve sign-up (14-day trial); #458 WP-27 Stripe go-live preparation. Not the shortcut.
- Environment note: the session container was replaced overnight, so I rebuilt my local Python virtualenv before running; no effect on results.

## What I did (evidence: `mlro-user-evidence/log_public04.json`, `landing.txt`, `aml_law.txt`, `pricing.txt`, `register.txt`; driver `mlro_user_drive.py`, mode `pub04` plus all earlier modes)
1. **Regression:** re-ran all 34 earlier driver modes on c5da8aa. All exit 0, no tracebacks. Registration with the invite code still works (the register page still asks for an invite code).
2. **Public pages as anonymous visitor:** `/`, `/pricing`, `/aml-law`, `/about`, `/blog`, `/apply` return 200 and are indexable; `/login` and `/register-organization` are `noindex, nofollow`; `/billing` is 404 when billing is not configured.
3. **Sign-up gate:** posting the registration form without the invite code returns "Invalid invite code." There is no visible payment or trial step on the page in this configuration (Stripe is not configured here), so the 14-day-trial flow itself was not reachable.
4. **Signed-in MLRO:** `/`, `/pricing`, `/aml-law` render with the normal signed-in navigation; nothing in the working screens changed.
5. **Read the new marketing and explainer text as a practising MLRO** and compared each claim with what I have exercised.

## Findings
- **MK1 (low-medium, PLAUSIBLE):** The landing page says "Verify identity with UAE PASS" and the AML-law page lists "UAE PASS verification" under CDD. The repository notes (CLAUDE.md) state that UAE PASS runs only against UAE PASS's staging sandbox with proof-of-concept credentials until the formal service-provider onboarding is complete. If that is still true in production, a customer would be promised an identity check that cannot be used on real customers. I cannot see production, so I mark this PLAUSIBLE.
- **MK2 (low, CONFIRMED):** The AML-law page's "Sanctions screening" row says screening covers "UAE, UN, OFAC, EU and UK lists", and the targeted-financial-sanctions row says freeze obligations are created from confirmed matches. In the product, only UN and UAE Local Terrorist List matches create a freeze obligation (OFAC, EU, UK matches stay alerts). A reader could assume a confirmed OFAC match freezes assets.
- **MK3 (info, CONFIRMED):** Pricing shows plan limits (operators, customers, workspaces) but no prices ("Contact us"); sign-up remains by request or invite in this configuration.
- Regulatory references on the explainer (Federal Decree-Law 10 of 2025, Cabinet Resolution 134 of 2025, Cabinet Decision 109 of 2023, Cabinet Resolution 74 of 2020) match the instruments I would expect; the page says it is general information, not legal advice. The freeze page no longer cites a resolution in its heading.
- Still open from earlier reports: UBO1b (dotted "L.L.C." suffix passes the self-owner check), F4, TA2, TA3, high-risk-country field accepting non-country text, E2-E5, LN1, SE2, PR5, and the other lows. Not re-checked today.

## BLOCKED / not checked
- The payment-gated sign-up and 14-day trial (Stripe not configured here; no payment test possible).
- Visual layout of the new pages on a phone width (no browser run today).
- Rate limiting (my driver disables the limiter), HSTS (needs an HTTPS run behind a proxy).
- goAML XSD validation, adverse media (GDELT), tesseract OCR success path, SMTP delivery.

## Files and commit
- `reports/daily/2026-11-04/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*.json` and `*.txt`
- Branch `routine/2026-11-04-mlro-user`; commit SHA in the final reply.
