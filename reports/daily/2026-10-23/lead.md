# Lead consolidated report: 2026-10-23

## 1. Headline: AMBER
Master has not moved. Today's new items are minor and latent: two unlinked auxiliary screeners and a fourth unguarded scan route. All 5 Medium-or-higher items from earlier runs still reproduce on `0d56f72`.

Master is `0d56f72fb85a296c9882903c9552c13a2210a994`, the same SHA as in the 10-22 lead report. `git log 0d56f72..origin/master` is empty. The GitHub PR list sorted by update shows only #411, an open draft docs PR updated 00:47Z; no PR was opened or merged since #427 (merged 2026-10-21). Run date: 2026-10-23 UTC. Red-team and mlro-user reported new findings, so the "no change" shortcut does not apply.

## 2. Per role
| Role (branch head) | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer (`a02203e`) | done (no-change) | GREEN; no new diff; carried CR items unchanged | ls-remote + PR list | High |
| qa-regression (`4a1649d`) | done (no-change) | GREEN; the 10-22 result stands (2173 passed, 3 skipped, 0 tenant leaks) | ls-remote, `git log` empty | High |
| red-team (`d0db291`) | done | AMBER. The web trade-licence scan has the B1/B2 defects: 97 KB PNG decodes in 22.9 s at 430 MB peak, and a junk `.exe` returns 200 | probe script + evidence file | High |
| compliance-specialist (`a67e555`) | done (no-change) | AMBER unchanged; CS-2/CS-13 stand; legal text BLOCKED | ls-remote | High on code; Articles PLAUSIBLE |
| mlro-user (`87dcfa3`) | done | AMBER. AX1-AX3: `kg-screen`/`gdelt-bq` are unlinked, answer 200 "unconfigured", and leave no audit row; auth and tenant checks hold | driver + JSON log | High |
| skeptic (`e0f9db0`) | done | AMBER. Confirms B1/B2 extended and AX1-AX3 by reading code; raises AX3 to Low/Medium (third-party disclosure through a GET, no audit) | file:line, no re-runs | High |

## 3. Consolidated findings
CONFIRMED means I re-ran a repro on `0d56f72` today (all 16 lead scripts exit 0; output in §5).

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-93** (new) `kg-screen`/`gdelt-bq` send the customer's full name to Google (KG API / BigQuery) via unthrottled GETs with no audit row | **LOW (latent)** | mlro AX3, skeptic | Low/Med | CONFIRMED: `AX3 configured: ... name in outbound kg URL=True, in BQ SQL=True; audit_log rows before=11 after=11`. Latent: the deploy's `--set-env-vars` (`source-canary.yml:499`) sets neither `GOOGLE_KG_API_KEY` nor `GOOGLE_CLOUD_PROJECT`, so both are inert in production | HELD `scripts/proposals/2026-10-23-aux-screeners.md`. **Needs Nadhir**: remove or harden |
| **L-94** (new, lead) KG request URL built by f-string with the raw name (`knowledge_graph.py:54`): `&`/`#` inject or truncate params | LOW (latent) | lead | n/a | CONFIRMED: `KQ name 'Acme & Co #1' -> ... query=['Acme '] fragment='1&key=...' (key param lost)` | HELD same file |
| **L-92** (new) unconfigured screeners answer 200 with empty results | LOW | mlro AX2, skeptic | Low | CONFIRMED: `AX2 ... gdelt-bq -> 200 {'status': 'unconfigured', ...}; kg-screen -> 200 {'status': 'unconfigured', 'entities': []}` | HELD same file |
| **L-91** (new) both routes unlinked from any template/JS (`app.py:2103,2123`) | INFO | mlro AX1, skeptic | Info | CONFIRMED by grep | HELD same file (option a: delete) |
| **L-82** scan uploads: no byte, pixel, MIME or rate cap. Now 4 routes, adding web trade-licence (`app.py:1908-1938`) | **MEDIUM** | red-team B1/B2, skeptic | Medium | CONFIRMED: `TL web scan-trade-licence with MZ .exe blob -> 200`; `B1w ... 9000x9000 PNG (97 KB) -> 200, peak RSS +1452 MB`; `B1m ... 30 MB junk ... -> 200` | HELD (10-20 §1; the shared guard covers the licence route). **Needs Nadhir** |
| **L-46** lockout counter not reset at expiry (+L-86 enumeration, L-87 422) | **HIGH** / LOW / INFO | red-team A1, mlro LG1-3, skeptic | High | CONFIRMED: `LG2 9 bad logins: real email -> 'Account locked...'; unknown email -> 'Incorrect email or password.'`, `LG3 empty password -> 422` | HELD. **Needs Nadhir** |
| **L-38** freeze/CNMR raised on non-UAE-list hits | MEDIUM-HIGH | compliance CS-2 | Med | CONFIRMED: `CS-2 EU-only sanction hit, true_positive -> ... 'status': 'pending_execution'` | HELD. **Needs Nadhir** |
| L-73 unrelated alert clears an overdue review | MEDIUM | lead | n/a | CONFIRMED: `RV ... overdue=False, next_review=2029-10-07, review recorded=False` | HELD. **Needs Nadhir** |
| L-53 blank `full_name` screens clear | MEDIUM | mlro C1 | Medium | CONFIRMED: `EN blank full_name onboarded id=3 stored='' clear=True` | HELD. **Needs Nadhir** |
| L-30 / L-9 rescreen re-raises alerts (+G9) | MEDIUM | mlro, compliance | Med | CONFIRMED: `new open alerts [3, 4]`; `G9 rescreen_all keys=['alerts', 'screened'] \| route reads outcome['customers']=True` | HELD |
| L-66, L-69, L-76, L-77 one-time secrets consumed concurrently | LOW-MED to INFO | red-team, lead | Medium | CONFIRMED: `T1m ... operators=10`, `BC ... results=[True, True]` (and the rest of `_15`-`_19`) | HELD. **Needs Nadhir** |
| L-88 / L-89 SEO: customer name in title, no noindex; canonical host hard-coded | LOW / INFO | mlro, cs, cr, skeptic | Info/Low | CONFIRMED: `SE1 ... title='Fatima Testcase — groAML' robots_meta=False canonical='https://groaml.grovisor.ae/customers/1'`; `HC ... canonical='https://groaml.grovisor.ae/about'` | HELD (10-22 proposal) |
| L-83, L-84, L-85 | LOW / INFO / LOW | mlro | as 10-20 | CONFIRMED: `AU1 ... -> 500`, `AU2 ... -> 200`, `AU3 ... body=0 bytes`, `PV1 ... reproduces=True` | HELD |
| L-90, L-78-L-81, L-75, L-67, L-47+L-58, L-57, L-52, L-56, L-63, L-61, L-62, L-54, L-51, L-48, L-40, L-27, L-44 | LOW / INFO | various | as before | CONFIRMED again (scripts `_06`-`_21` all exit 0; L-90 still PLAUSIBLE) | HELD / carry |
| L-74, L-70/L-72/L-71, L-43, L-50, L-55, L-68, L-64, L-65, L-59, L-60 and the 10-16 carry list | as before | various | as before | Unchanged: master did not move | Carry |

**Severity adjudication**
- L-93: the skeptic proposes Low/Medium and mlro-user Low. I put it at **LOW (latent)**. The skeptic's reasoning holds for a configured deployment: a third-party disclosure with no audit trail, reachable by GET and so by prefetchers. The skeptic marked production config BLOCKED, but the deploy workflow answers that: `--set-env-vars` replaces the whole env list and contains neither variable. I have not checked whether Cloud Run injects `GOOGLE_CLOUD_PROJECT` itself, so this is PLAUSIBLE-inert rather than proven. If either variable is ever set, this becomes MEDIUM, together with the PLAUSIBLE BigQuery cost (an unbounded 90-day `gkg_partitioned` LIKE scan per GET).
- Red-team B1 on the licence route: red-team rates it Low-Medium and the skeptic Medium. It is the same defect as L-82, so it takes L-82's **MEDIUM**. I made it one finding, not a new id.
- Duplicates: AX1-AX3 match the skeptic's three rows; B1/B2 extended = L-82. Contradictions: none.

**FIXED on master:** none.

## 4. Combined assessment
1. Master has not changed for 2 days and nothing from the backlog has landed. All 16 lead repro scripts still exit 0.
2. Today's new items (L-91 to L-94) are latent in production because neither Google variable is deployed. Deleting the two routes clears all four.
3. L-82 now spans 4 scan routes. One shared guard fixes all of them.
4. The 5 Medium-or-higher items (L-46, L-82, L-38, L-73, L-53) each wait on a decision, not on more evidence.
5. As yesterday, more probing mostly adds duplicates. The bottleneck is Nadhir's approvals.

## 5. Corrections I made
- C-1 Created `repro_lead/checks_2026_10_23.py` (AX2, AX3, KQ, TL). Outbound calls are monkeypatched; temp DB; no network. Output on `0d56f72`:
  ```
  AX2 unconfigured: gdelt-bq -> 200 {'status': 'unconfigured', 'theme_counts': {}, 'avg_tone': 0.0, 'article_count': 0, 'sample_sources': [], 'sample_headlines': []}; kg-screen -> 200 {'status': 'unconfigured', 'entities': []} -> reproduces=True
  AX3 configured: kg -> 200, bq -> 200; name in outbound kg URL=True, in BQ SQL=True; audit_log rows before=11 after=11 -> reproduces=True
  KQ  name 'Acme & Co #1' -> kg URL query params=['query'] query=['Acme '] fragment='1&key=dummy-not-a-key&limit=5&languages=en' (key param lost) -> reproduces=True
  TL  web scan-trade-licence with MZ .exe blob -> 200 body='{"full_name":null,"id_number":null,...' -> reproduces=True
  4/4 reproduce
  exit=0
  ```
- C-2 Created `scripts/proposals/2026-10-23-aux-screeners.md` (HELD). It gives two options: (a) delete both routes, which I recommend; or (b) switch them to POST with CSRF and a rate limit, return 503 when unconfigured, add an audit row and pass `params=` encoding, plus a `maximum_bytes_billed` cap on the BigQuery job. Not applied, because it edits route and screening logic.
- C-3 Owed by the 10-22 "Next run": I re-ran `_22`, `_21`, `_20`, `_19`, `_18`, `_17`, `_16`, `_15`, `_14`, `_13`, `_12`, `_11`, `_10`, `_07` and `_06` (`_06` from inside `repro_lead/`) on `0d56f72` in a scratch venv (`requirements.txt` + `passporteye` + pytest; no tesseract, no pdfminer). **All exit 0** (`_23 exit=0 ... _07 exit=0`, `_06 exit=0`). I copied the older scripts from their lead branches and removed them before committing.
- Process note: my first pass ran against a stale local `origin/master` ref (`0129848`). It was caught when `_22` exited 1 because canonical tags were absent, which predates #427. I fetched master, checked out `0d56f72` and re-ran everything; every result above is from `0d56f72`.
- Not re-run: red-team's `probe_scan_variants.py` (my TL check covers B2; B1 on the licence route rests on red-team's evidence file), the MLRO driver, the full suite (master unchanged since the 10-22 runs).
- No tests added, because each would fail on master (rule 5). No existing file edited.

## 6. Decisions needed from Nadhir
1. **L-46 (HIGH) + L-86 + L-74: approve one lockout PR** (10-11 §1, 10-21 proposal).
2. **L-82 (MEDIUM): approve the shared scan-upload guard.** It now has to cover 4 routes, including web trade-licence. Also confirm the production memory limit.
3. **L-38: choose the freeze scope.** The public guide already says "UAE/UN lists only".
4. **New: L-91 to L-94, remove or harden `kg-screen`/`gdelt-bq`** (proposal 2026-10-23). Also confirm that production never sets `GOOGLE_KG_API_KEY` or `GOOGLE_CLOUD_PROJECT`.
5. Periodic review (L-70/L-72/L-73): re-ratings may bring the review date forward but never push it back.
6. Atomic consume for one-time secrets (L-66, L-69, L-76, L-77).
7. L-53 blank name; L-81 session cap; L-85 privacy wording (also name the Google processors if option (b) is chosen).
8. Carried: L-88/L-89 SEO, L-30 banner fix, L-9, L-79, the Low list, shared helpers, L-31/32/33 adviser confirmation, legal-text `corpus/`, FATF snapshot, #417 (L-23), the `github-advanced-security` 402 quota, a single de-duplicated finding register.

## 7. Next run: carried over
- Re-run `repro_lead/checks_2026_10_23.py` (this branch) plus `_22`, `_21`, `_20`, `_19`, `_18`, `_17`, `_16`, `_15`, `_14`, `_13`, `_12`, `_11`, `_10`, `_07` and `_06` from their lead branches. Put them in `repro_lead/` with `PYTHONPATH=.:tests` (run `_06` from inside `repro_lead/`; `_20` needs `passporteye`). **Run `git fetch origin master` and check out the SHA first.** Exit 1 means fixed; read the printed lines.
- Owed by the lead: nothing new beyond the re-runs.
- For whichever role picks it up: grep `@app.get` handlers with outbound or write side effects (skeptic "missed" #1); an inventory of "feature present, not wired" code (E1/E2, aux screeners, the web periodic-review action); whether Cloud Run injects `GOOGLE_CLOUD_PROJECT`; the legal-person scan route; other PDF shapes for L-82; L-81 mobile tokens; lock expiry end to end over HTTP.
- Landing order: L-46 (+L-74, L-86), L-82, L-38, L-53, L-70/L-72/L-73, L-66/L-69/L-76/L-77, L-91-L-94 (delete routes), L-50, L-43, L-30, L-9, L-57, L-47+L-58+L-67+L-80, L-78, L-83, L-88, L-52, L-55, L-56, L-64, L-65, L-63, L-79, L-85, L-81, L-54, L-28, L-29, L-51, L-48, L-27, L-40, L-44, L-21, L-75, L-84, L-87, L-89, L-90.
