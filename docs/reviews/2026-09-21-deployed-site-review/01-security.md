# amlkit — SECURITY lane findings

Method: gstack CSO audit (Pass-1 + auth/authz/crypto/red-team specialists).
Target: deployed code at http://127.0.0.1:8000 (AMLKIT_BEHIND_PROXY=1, production mode). Read-only. Probes: scratchpad/sec/probe*.py.

## 1. Severity-ranked findings

| # | Sev | Location | Claim | Evidence | Fix |
|---|-----|----------|-------|----------|-----|
| 1 | HIGH | amlkit/api/deps.py client_ip() (~L120-150); used by rate_limit_key_func/login_rate_limit_key (app.py:185,196) and record_signature IP (app.py:1563) | X-Forwarded-For is attacker-controllable: client_ip() returns the FIRST non-private hop. Behind Cloud Run the client prepends arbitrary hops, so it controls the value. Breaks rate limiting AND corrupts the forensic IP on legally-significant records. | Live: /login with rotating X-Forwarded-For: 9.9.9.N never hit 10/min — all 200 across 14 tries, vs [200,200,200,429,...] from single IP (probe.py G). Live: signature POST with XFF 203.0.113.66,10.0.0.5 → DB signatures.ip_address=203.0.113.66 (probe3.py). | Trust only right-most XFF entry (Cloud Run appends real client IP last), or count fixed trusted-proxy hops from the right. Never first/left-most non-private hop. |
| 2 | MEDIUM | amlkit/api/mobile.py api_login (/api/v1/auth/login) | Mobile login has NO rate limiting (no @limiter.limit), unlike web /login (10/min IP + 3/min account). Enables faster cred-stuffing and account-lockout DoS: 8 failed logins locks any account 15 min, so attacker can lock every operator. | Live: 14 consecutive bad /api/v1/auth/login → all 401, no 429 (probe3.py). api_register_organization IS rate-limited (5/min); api_login is not. | Add @limiter.limit + per-account key to api_login mirroring web; consider IP-scoped lockout. |
| 3 | LOW | amlkit/api/limits.py + app.py (no SlowAPIMiddleware) | default_limits=["100/minute"] never applies: slowapi application limits need SlowAPIMiddleware, not registered. Only @limiter.limit-decorated routes throttle; many write POSTs unthrottled. | grep add_middleware/SlowAPIMiddleware → none. Session+CSRF still gate these routes. | Register SlowAPIMiddleware or add explicit per-route limits to expensive/write routes. |
| 4 | LOW | amlkit/api/app.py admin_refresh_stream (/admin/refresh-stream L2270) | Unauth request returns HTTP 200 (streams error SSE) instead of 401. No data/action leaked but misleads monitors. | Live: curl unauth → 200, body only data: {"type":"error","error":"unauthorized"} (probe3.py). | Return status_code=401 for the unauthenticated case. |
| 5 | LOW | .github/workflows/source-canary.yml deploy (--set-env-vars) | SCHEDULER_SECRET, ADMIN_API_SECRET, SendGrid key injected as plaintext Cloud Run env vars (not Secret Manager); readable via run.services.get and echoed via describe each deploy. | Workflow reads secrets back via gcloud run services describe --format json and re-sets as env; SMTP pw from secrets into --set-env-vars. | Use Secret Manager + --set-secrets. |
| 6 | INFO | amlkit/auth.py mfa_* (L~360-460) | MFA/TOTP functions exist but NOT wired into login or any route; login() never checks TOTP. TOTP secret stored plaintext in mfa_secrets. Dead code / false assurance; needs encryption if enabled. | grep mfa_/totp in api/ → none. mfa_enroll INSERTs raw base32 secret. CLAUDE.md: "No MFA yet". | Remove until wired, or gate login on it and encrypt secret at rest. |
| 7 | INFO | amlkit/screening/knowledge_graph.py:54 | KG URL f-string with unencoded name/key in query. Host hard-coded (not SSRF), but name with &/# could inject params. Input is own-org customer name. | Code read; no urlencode. | Use httpx params= for auto-encoding. |
| 8 | INFO | amlkit/screening/gdelt_bq.py:60 | BigQuery SQL f-string with safe_name in LIKE and window_days in INTERVAL. Reviewed SAFE: _sanitize_name strips quotes (keeps [A-Za-z0-9 -]+Arabic), window_days is int(). Documented for future changes. | Code read. | Prefer BigQuery query parameters. |

## 2. Scanner verdicts (scripts/security_scan.py — all 16 flags FALSE POSITIVES)

Line-regex scanner can't parse multi-line SQL, correlated subqueries, or route-vs-library roles. Tenant isolation verified live (see 4).

| Flag | Verdict | Reasoning (verified) |
|---|---|---|
| queries.py:731 console_overview() missing org_id param | FALSE POSITIVE | Super-admin multi-org aggregation; gated by require_super_admin. Live: normal MLRO → /console 303→/ (denied). Per-org subqueries pass org_id. |
| queries.py:892 customer_completeness() missing org_id | FALSE POSITIVE | Pure dict function; no SQL. |
| queries.py:121 dashboard() risk_assessments no org_id (x2) | FALSE POSITIVE | Correlated subquery WHERE r.customer_id=c.id under customers c WHERE c.org_id=?. |
| queries.py:731 console_overview() risk_assessments no org_id (x2) | FALSE POSITIVE | Same correlated scoping inside super-admin view. |
| app.py:1306 customer_add_ubo() missing org_id param | FALSE POSITIVE | Route; passes session.org_id to add_ubo; H-01 check uses org_id. |
| app.py:507 logout_submit() POST without require_csrf | FALSE POSITIVE (accepted) | Only revokes caller's own session + deletes cookie; no cross-user state change. |
| app.py:2517 system_refresh() POST without require_csrf | FALSE POSITIVE | Not cookie route; SCHEDULER_SECRET bearer via compare_digest. Live: no-secret 403, wrong bearer 403. CSRF N/A. |
| manager.py:258 add_ubo() missing org_id param | FALSE POSITIVE | Keyword-only org_id; verifies customer WHERE id=? AND org_id=? before write. |
| manager.py:258 add_ubo() DELETE ubo_links no org_id | FALSE POSITIVE | DELETE WHERE id=? removes only the just-inserted lastrowid in same txn (self-parent guard); ownership pre-checked. |
| manager.py:388 close_relationship() UPDATE no WHERE | FALSE POSITIVE | Actual: UPDATE customers ... WHERE id=? AND org_id=?. |
| manager.py:409 reactivate_customer() UPDATE no WHERE | FALSE POSITIVE | WHERE id=? AND org_id=?; pre-checks status with org_id. |
| review.py:234 propose_disposition() missing org_id param | FALSE POSITIVE | Keyword-only org_id; every UPDATE/SELECT AND org_id=? + rowcount check. |
| review.py:324 confirm_disposition() missing org_id param | FALSE POSITIVE | Same; proposal lookup + UPDATE filter org_id. |
| review.py:437 bulk_dismiss_alerts() UPDATE alerts no WHERE | FALSE POSITIVE | UPDATE alerts ... WHERE id=? AND org_id=?; sources via JOIN screenings WHERE a.org_id=?. |

## 3. Route census (unauthenticated, observed live — probe3.py)

| Route | Method | Auth req? | CSRF? | Unauth status |
|---|---|---|---|---|
| /health | GET | no (public) | n/a | 200 (status only) |
| /login | GET/POST | no | POST yes | 200 |
| / /dashboard /screen /customers* /alerts* /audit* /reports* /policies* /admin* /compliance/* /profile /freeze-obligations* | GET | yes | n/a | 303 → /login |
| /customers/{id}/gdelt-bq, /reports/{id}/export, /api/alerts-summary | GET | yes | n/a | 401 |
| /console /console/org/{id}/* | GET | super-admin | n/a | unauth 303→/login; normal MLRO 303→/ (denied) |
| /admin/refresh-stream | GET | mlro | n/a | 200 (error SSE only — finding 4) |
| /setup /register-organization /verify-email /about | GET | no (public by design) | POST yes | 200 |
| POST /customers /reports /customers/{id}/* /alerts/* /adverse-media/* /admin/* | POST | yes | yes (require_csrf) | auth-gated; CSRF verified |
| POST /system/refresh /system/create-operator | POST | bearer secret | n/a | 403 (secret unset) / 401 (bad bearer) |
| /api/v1/* (mobile) | GET/POST | bearer | n/a | 401 (no/bad bearer) |
| /openapi.json /docs /redoc | GET | — | — | 404 (disabled) |
| /static/../… traversal | GET | — | — | 404 (normalized) |

CSRF live (probe2.py, org-A session): POST /customers no-token → 303 /customers/new (rejected); bad token → rejected; notes no-token → rejected. Success only with valid token.

## 4. What is solid

- Tenant isolation holds (verified web + mobile). Customer created in org A (id 2); org-B session AND org-B bearer both got 404/redirect on /customers/2, /evidence, /gdelt-bq, /kg-screen, /documents; org-B POST notes/close on A had no effect. Cross-tenant reads indistinguishable from not-found. Every query/write takes mandatory org_id; writes use WHERE id=? AND org_id=? + rowcount.
- CSRF synchronizer token (cookie+field), compare_digest, rotated on login/verify; enforced (verified).
- Session cookies HttpOnly; Secure; SameSite=Strict (session) and SameSite=Lax; Secure; HttpOnly (csrf), observed. Tokens stored SHA-256 only; idle+absolute expiry; revoke_sessions_for on pw change/deactivate; concurrent-session cap.
- argon2id t=3 m=64MiB p=4 (meets OWASP). Constant-time login w/ dummy hash on unknown email; generic error blocks enumeration.
- RBAC require_role/require_super_admin enforced (normal MLRO denied /console live).
- Bearer auth reuses hashed session tokens → inherits expiry/revocation/lockout; CSRF N/A.
- Security headers on all responses: CSP (script-src 'self', no unsafe-inline for scripts), HSTS, X-Frame-Options DENY, nosniff, frame-ancestors none.
- XSS: Jinja autoescape on; only |safe is ubo_diagram (server SVG with html.escape on names).
- Open redirect: _safe_url rejects scheme/netloc, re-quotes path. CSV injection: _escape_csv_formula on all cells (web+mobile).
- File upload: magic-byte MIME, basename-only, size cap, traversal rejection; downloads authorized by id+customer_id+org_id.
- Audit append-only via triggers; audit() requires explicit org_id.
- Repo secrets: no live creds committed (only a test password); .env/*.db/documents gitignored; /system/* fail-closed; WIF deploy (no SA key); no pull_request_target; deploy gated to master push.
