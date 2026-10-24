# mlro-user daily report — 2026-10-24

**Headline: AMBER** — master moved to 401da32 (four public-site commits, #428-#431); none of them touched MLRO business logic and the selective gzip behaves as designed, but earlier open items stand.

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside. LOCAL seeded instance only; no production, no /system/*, no secrets; additive only. Source read only to see what the new commits changed (compress.py, app.py, templates) and to locate routes.
- Report to branch `routine/2026-10-24-mlro-user` (never master) and as final reply. No dreamon messages today.
- Master changed: `git ls-remote origin refs/heads/master` = `401da3298f97bc94710e4b7171ec43a2ce4162b2` (previous report: 0d56f72). New commits: #428 gzip static assets and anonymous public pages, #429 public-page links/nofollow SSO link, #430 legal name LLC to FZE, #431 branded share image. Highest PR ref now 431. Not the shortcut.

## What I did (evidence: `mlro-user-evidence/log_gzip_check.json`; driver `mlro_user_drive.py`, `ONLY=gz`)
1. Read the diff. The risky one for a compliance product is #428: it adds a gzip middleware, and compressing pages that carry CSRF tokens or customer data next to attacker-influenced text would open a BREACH-style side channel.
2. Fetched pages with `Accept-Encoding: gzip`, anonymous and signed in as the MLRO. Anonymous `/about`, `/blog`, `/sitemap.xml`: gzip. Anonymous `/privacy`, `/login`, `/register-organization`, `/robots.txt`, the share image: not compressed. Signed in: `/about`, `/blog`, `/dashboard`, `/customers`, `/customers/1`, `/audit`, `/reports`, evidence page, `customers.csv`, `alerts.csv`, `audit/export`, evidence PDF: all uncompressed. A bogus session cookie on `/about` also disables compression (conservative).
3. Anonymous `/about` carries no CSRF token in its body; `/blog?q=<script>` is not reflected. CSV still parses and the evidence PDF still starts with `%PDF-` when the client asks for gzip.
4. Legal name: `/about`, the footer and the login page say "Grovisor Business Consultants FZE"; no served page I fetched says LLC.
5. Re-ran earlier modes: `web` and `mobile` completed with exit 0 on 401da32 (regression only).

## Findings
- **GZ1 (info, CONFIRMED):** #428 does what its comment says: compression only on static files and anonymous marketing pages, never on case files, exports or forms. No MLRO-facing exposure found. **BREACH concern: REFUTED.**
- **GZ2 (info, CONFIRMED):** `/robots.txt` and the PNG are not compressed (below the 500-byte minimum / already compressed). Harmless.
- **LN1 (low, CONFIRMED):** `str_builder.html` still falls back to the entity name "Grovisor Business Consultants" for the STR "reporting entity" if the session has no organisation name, and `db.py` seeds an organisation by that name. Not affected by #430 (the string has no LLC/FZE suffix), but it means a report built under that fallback would name Grovisor, not the filing DNFBP. Only reachable when the session's organisation name is empty; I did not reproduce it.
- Still open from earlier reports: G9, G10, F4, OP1/OP2, TA1, C1/C3, E1, H2, S1, PR1-PR3, M1, M2, PW1, PW2, SS1, AU1-AU3, PV1, LG1-LG4, SE1-SE2, AX1-AX3 and the lows. Not re-verified today (no business-logic change in the diff).

## BLOCKED / not checked
- Rendered share card and link previews (no social fetcher in the sandbox).
- Behaviour behind a real reverse proxy/CDN that may add its own compression.
- Only `web` and `mobile` driver modes re-run on 401da32.
- goAML XSD validation, adverse media (GDELT), tesseract OCR success path, SMTP delivery.

## Files and commit
- `reports/daily/2026-10-24/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*.json`
- Branch `routine/2026-10-24-mlro-user`; commit SHA in the final reply.
