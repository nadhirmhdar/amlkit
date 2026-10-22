# Lead consolidated report: 2026-10-22

## 1. Headline: AMBER
Master moved for the first time in 16 days, but only through an SEO metadata change (#427). That change is clean apart from two new Low/Info hygiene items. Every carried defect, including HIGH L-46, still reproduces on the new head.

Master is `0d56f72fb85a296c9882903c9552c13a2210a994` (#427). It was `01298484` in the 10-21 lead report. `git log 0129848..origin/master` shows one commit, touching 9 files (+70/-7): templates, `blog.py`, the sitemap list in `app.py:sitemap_xml` and `tests/test_blog.py`. Run date: 2026-10-22 UTC.

## 2. Per role
| Role (branch head) | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer (`bc13b8f`) | done | GREEN. #427 clean; CR-19 (canonical on authenticated pages), CR-20 (citation in metadata) are Info. Full suite 2173 passed, 3 skipped | diff read, suite count | High |
| qa-regression (`bce3837`) | done | GREEN. `2173 passed, 3 skipped` in 680 s; tenant sweeps `HITS: []`, 0 leaks; rescreen isolation 30/30 | pasted pytest and sweep output | High |
| red-team (`86b6360`) | done | GREEN for #427. Hostile paths 404 before render; query string not echoed; noindex correct. Earlier items unchanged | probe script + evidence file | High |
| compliance-specialist (`27e679d`) | done | AMBER, unchanged. The public 24-hour guide says OFAC/EU/UK hits are not CNMR, which sharpens CS-2 (L-38). CS-17 is Info. Legal text still BLOCKED | file:line, 2 test files run (35 passed) | High on code; Articles PLAUSIBLE |
| mlro-user (`537abc4`) | done | AMBER. SE1 customer name in `<title>` with no noindex (Low); SE2/SE3 Info. web and mobile driver modes re-run clean | driver + JSON logs | High |
| skeptic (`6b37542`) | done | AMBER. Confirms #427 clean; moves SE1 down to Info/Low; finds the hard-coded canonical host and the unenforced `seo_title` limit | file:line, no re-runs | High |

## 3. Consolidated findings
CONFIRMED means I re-ran a repro or read the cited lines on `0d56f72` today.

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-88** (new) signed-in pages: customer name in `<title>` (`customer.html:5`), canonical/og:url now present (`base.html:9,16`), no robots noindex, `robots.txt` `Allow: /` (`app.py:2921`) | LOW | mlro SE1, compliance CS-17, code-reviewer CR-19, skeptic | Info/Low | CONFIRMED: `SE1 GET /customers/1 -> 200 title='Fatima Testcase — groAML' robots_meta=False canonical='https://groaml.grovisor.ae/customers/1'` | HELD `2026-10-22-seo-private-pages-and-canonical-host.md` |
| **L-89** (new) canonical/og host hard-coded to production for every environment | INFO | skeptic | n/a (own) | CONFIRMED: `HC served from staging.example.test: canonical='https://groaml.grovisor.ae/about'` | HELD same file |
| **L-90** (new) `/blog?topic=` vs `?q=` canonical inconsistency | INFO | mlro SE2 | Info | PLAUSIBLE (not re-run; both `noindex`) | HELD same file |
| SE3 one og:image; `seo_title` "<=42 chars" only in a comment (`blog.py:53`) | INFO | mlro, skeptic | Info | CONFIRMED by read | No action |
| CR-20 "Cabinet Resolution No. 134 of 2025" in new metadata | INFO | code-reviewer | PLAUSIBLE | PLAUSIBLE; consistent with the post body | Folds into the legal-text sign-off (BLOCKED) |
| **L-46** lockout counter not reset at expiry (+L-86 enumeration, L-87 422) | **HIGH** / LOW / INFO | red-team A1, mlro LG1-3, skeptic | High | CONFIRMED by code, not touched by #427. `_21` re-run: `LG2 ... reproduces=True`, `LG3 ... reproduces=True` | HELD (10-11 §1, 10-21). **Needs Nadhir** |
| **L-82** scan uploads: no byte, pixel or rate cap | **MEDIUM** | red-team B1/B2 | Medium | CONFIRMED again: `B1w web scan 9000x9000 PNG (97 KB) -> 200, peak RSS +1452 MB`, `B1m ... 30 MB junk ... -> 200` | HELD (10-20 §1). **Needs Nadhir** |
| **L-38** freeze/CNMR raised on non-UAE-list hits | MEDIUM-HIGH | compliance CS-2 | Med | CONFIRMED again: `CS-2 EU-only sanction hit, true_positive -> ... 'pending_execution'`. The product now contradicts its own public guide | HELD. **Needs Nadhir** |
| L-73 unrelated alert clears an overdue review | MEDIUM | lead | n/a | CONFIRMED again: `RV ... overdue=False, next_review=2029-10-06, review recorded=False` | HELD. **Needs Nadhir** |
| L-53 blank `full_name` screens clear | MEDIUM | mlro C1 | Medium | CONFIRMED again: `EN blank full_name onboarded ... clear=True` | HELD. **Needs Nadhir** |
| L-30 / L-9 rescreen re-raises alerts | MEDIUM | mlro, compliance | Med | CONFIRMED again: `new open alerts [3, 4]` | HELD |
| L-66, L-69, L-76, L-77 one-time secrets consumed concurrently | LOW-MED to INFO | red-team, lead | Medium | CONFIRMED again: `T1m ... operators=10`, `T1w ... operators=10`, `BC results=[True, True]`, `EV [5, 5, 5, 5, 5]`, `US [5, 5, 5, 5, 5]` | HELD. **Needs Nadhir** |
| L-83, L-84, L-85 | LOW / INFO / LOW | mlro | as 10-20 | CONFIRMED again: `AU1 ... -> 500`, `AU2 -> 200`, `AU3 ... body=0 bytes`, `PV1 ... reproduces=True` | HELD (10-20 §2-4) |
| L-78, L-79, L-80, L-81, L-75 | LOW / LOW / INFO / LOW / INFO | red-team, mlro | as before | CONFIRMED again: `S3w`, `S3m`, `PW1`, `PW2`, `L75` all `reproduces=True` | HELD |
| L-67, L-47+L-58, L-57, L-52, L-56, L-63, L-61, L-62, L-54, L-51, L-48, L-40, L-27, L-44 | LOW / INFO | various | as before | CONFIRMED again: `T2`, `OP1 ... 500`, `R1`, `R2`, `P1`, `F6`, `NT2`, `NT3`, `SEC`, `TA1`, `GR`, `M2`, `4E`, `DL`, `DLA` | HELD / carry |
| L-74, L-70/L-72/L-71, L-43, L-50, L-55, L-68, L-64, L-65, L-59, L-60 and the 10-16 carry list | as before | various | as before | Unchanged: #427 does not touch their code | Carry |

**Severity adjudication**
- L-88: mlro-user rates it Low and the skeptic Info/Low. I put it at **LOW**. The skeptic is right that a crawler gets the login redirect and that #427 did not add the customer-name title. Even so, a customer's name in an indexable-by-default response is a confidentiality exposure for an AML product. The fix is about 2 lines, so the rating should not depend on #427. CR-19, CS-17 and SE1 are one finding.
- L-89 INFO: SEO-only, with no data exposure.
- Duplicates: CR-19 = CS-17 = SE1 = L-88. Contradictions: none of substance. Compliance says the full suite was not run on `0d56f72`; QA and code-reviewer both ran it (`2173 passed, 3 skipped`), so that gap is closed.

**FIXED on master:** none. #427 touches no carried item; all 14 lead scripts still exit 0.

## 4. Combined assessment
1. The first commit in 16 days is marketing metadata. It is clean (suite 2173/3 skipped, tenant sweeps 0 leaks, injection probes refuted).
2. It adds two hygiene items (L-88 Low, L-89 Info). Both have one small HELD proposal.
3. The public 24-hour guide now openly contradicts the product's freeze behaviour (L-38). That raises the priority of the scope decision, not its severity.
4. None of the 5 Medium-or-higher items (L-46, L-82, L-38, L-73, L-53) has moved; each is waiting on a decision.
5. More probing adds little. The backlog needs Nadhir's approvals.

## 5. Corrections I made
- C-1 Created `repro_lead/checks_2026_10_22.py` (SE1/L-88, HC/L-89). Temp DB and TestClient, no network. Output on `0d56f72`:
  ```
  SE1 GET /customers/1 -> 200 title='Fatima Testcase — groAML' robots_meta=False canonical='https://groaml.grovisor.ae/customers/1'; robots.txt='User-agent: *\nAllow: /\nSitemap: https://groaml.grovisor.ae/sitemap.xml\n' -> reproduces=True
  HC  served from staging.example.test: canonical='https://groaml.grovisor.ae/about' og:url='https://groaml.grovisor.ae/about' -> reproduces=True
  2/2 reproduce
  exit=0
  ```
- C-2 Created `scripts/proposals/2026-10-22-seo-private-pages-and-canonical-host.md` (HELD). It proposes noindex/`X-Robots-Tag` on authenticated responses, `Disallow` for private paths and a configurable public base URL. Not applied, because it edits existing templates and a route.
- C-3 Owed by the 10-21 "Next run": I re-ran `_21`, `_20`, `_19`, `_18`, `_17`, `_16`, `_15`, `_14`, `_13`, `_12`, `_11`, `_10`, `_07` and `_06` (`_06` from inside `repro_lead/`) on `0d56f72`. I used a scratch venv built from `requirements.txt` plus `passporteye`, with no tesseract and no pdfminer. **All 14 exit 0.** §3 quotes their lines. I copied the scripts from their lead branches and removed them before committing.
- Not re-run: red-team `probe_seo_canonical.py` (my HC/SE1 check covers the same template), the mlro driver, the skeptic scripts, the full suite (QA and code-reviewer runs stand).
- No tests added, because each would fail on master (rule 5). No existing file edited.

## 6. Decisions needed from Nadhir
1. **L-46 (HIGH) + L-86 + L-74: approve one lockout PR** (10-11 §1, 10-21 proposal).
2. **L-82 (MEDIUM): approve the shared scan-upload guard** (10-20 §1). Also confirm the production memory limit and instance count.
3. **L-38: choose the freeze scope**, (a)/(b)/(c). The public guide already states option "UAE/UN lists only", so either the product or the guide must change.
4. Periodic review (L-70/L-72/L-73): event re-ratings may bring the review date forward but never push it back.
5. Atomic consume for one-time secrets (L-66, L-69, L-76, L-77).
6. L-53 blank name; L-81 session cap; L-85 privacy wording.
7. New: L-88/L-89 SEO hygiene. One small PR, and it can ride the next template change.
8. Carried: L-30 banner fix, L-9, L-79, the Low list, shared helpers (password, bounded inputs, uploads), L-31/32/33 adviser confirmation, legal-text `corpus/` (also CR-20), FATF snapshot, #417 (L-23), the `github-advanced-security` 402 quota, a single de-duplicated finding register.

## 7. Next run: carried over
- Re-run `repro_lead/checks_2026_10_22.py` (this branch) plus `_21`, `_20`, `_19`, `_18`, `_17`, `_16`, `_15`, `_14`, `_13`, `_12`, `_11`, `_10`, `_07` and `_06` from their lead branches. Put them in `repro_lead/` and use `PYTHONPATH=.:tests` (run `_06` from inside `repro_lead/`). `_20` needs `passporteye`. An exit of 1 means something was fixed; read the printed lines.
- Owed by the lead: nothing new beyond the re-runs.
- Not yet checked, for whichever role picks it up: web trade-licence and legal-person scan routes; other PDF shapes for L-82; L-81 mobile tokens; lock expiry and admin unlock end to end over HTTP; whether JSON/CSV exports need `X-Robots-Tag`.
- Landing order: L-46 (+L-74, L-86), L-82, L-38, L-53, L-70/L-72/L-73, L-66/L-69/L-76/L-77, L-50, L-43, L-30, L-9, L-57, L-47+L-58+L-67+L-80, L-78, L-83, L-88, L-52, L-55, L-56, L-64, L-65, L-63, L-79, L-85, L-81, L-54, L-28, L-29, L-51, L-48, L-27, L-40, L-44, L-21, L-75, L-84, L-87, L-89, L-90.
