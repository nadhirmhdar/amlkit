# Lead consolidated report: 2026-10-20

## 1. Headline: AMBER
Master has not moved for fourteen days. Red-team found a new MEDIUM: a 97 KB image sent to the passport-scan upload pushes the process to about 1.5 to 4.5 GB of memory (L-82). On the single production instance this is a plausible outage. The HIGH lockout DoS (L-46) and every carried Medium still reproduce.

Master is `01298484a7bfed106e9b2bd3a6238f98a4d2514b` (#426), the same as the 10-19 lead report. `git log 0129848..origin/master` is empty. Roles report no PR opened or merged since #426; only draft #411 (docs) was updated. Red-team and mlro-user report new findings, so this is not a no-change run. Run date: 2026-10-20 UTC.

## 2. Per role
| Role (branch head) | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer (`6bd6ba4`) | done (no-change) | GREEN. No new diff. CR-12, CR-4 (#417), CR-13/14/18, CR-1b open | `ls-remote`, PR list | High |
| qa-regression (`c34f8a0`) | done (no-change) | GREEN. Suite not re-run; the 10-07 result stands (2170 passed, 3 skipped) | `ls-remote`, `git log` | High |
| red-team (`deaef7a`) | done | AMBER. B1: decompression-bomb PNG on scan routes. RSS reached 1.96 GB (9000x9000) and 4.48 GB (12000x12000). A 60 MB junk body was accepted | probe script + evidence file + HELD proposal | High on resource use. Its fix leans on `Image.MAX_IMAGE_PIXELS`, which does not reliably cover passporteye's decoder (see §3) |
| compliance-specialist (`ca1bbae`) | done (no-change) | AMBER, unchanged. CS-2 and CS-13 are the most serious; legal text still BLOCKED | `ls-remote` | High |
| mlro-user (`cb77bad`) | done | AMBER. AU1 (500 on a huge `page`), AU2, AU3, PV1 (privacy page cookie list incomplete) | HTTP driver + JSON log | High |
| skeptic (`cf3372d`) | done | AMBER. B1 CONFIRMED by code, Medium. AU1 is a duplicate of its 10-07 offset-overflow finding. AU2/AU3 lowered to Info. PV1 rated Low/Med | file:line + re-run of `offset_overflow.py` | High |

## 3. Consolidated findings
CONFIRMED means I re-ran a repro or read the cited lines on `0129848` today.

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-82** scan uploads: no byte cap, no pixel cap, no rate limit. The web passport route also skips the MIME check (`app.py:1878-1909`, `mobile.py:676-705`; no `MAX_IMAGE_PIXELS` in `amlkit/`) | **MEDIUM** | red-team B1 | CONFIRMED, Medium | CONFIRMED: `B1w web scan 9000x9000 PNG (97 KB) -> 200, peak RSS +1453 MB`; `B1m mobile scan 30 MB junk with PNG magic -> 200` | HELD `scripts/proposals/2026-10-20-upload-image-guard-and-audit-paging.md` §1. **Fix first** after L-46 |
| **L-83** `/audit` (and `/feedback`) `page` is unbounded: a huge value gives a 500, and negative values are accepted (`app.py:3048-3062`, `:2982`) | LOW | mlro AU1+AU2; skeptic (10-07) | CONFIRMED; duplicate | CONFIRMED: `AU1 ... -> 500`, `AU2 /audit?page=-1 -> 200` | HELD same file §2. Merges with the skeptic's 10-07 offset item |
| **L-84** officer gets a bare 403 on `/audit/export` but a redirect on `/audit` | INFO | mlro AU3 | Info | CONFIRMED: `AU3 officer /audit -> 303 '/'; /audit/export -> 403 body=0 bytes` | HELD same file §3 |
| **L-85** privacy page says "three cookies" but omits `amlkit_trusted_device` and `amlkit_uaepass_state` (`privacy.html:19`; `auth.py:61,65`; set at `app.py:664,914`) | LOW | mlro PV1 | Low/Med | CONFIRMED: `PV1 ... 'three cookies'=True; names amlkit_trusted_device=False, amlkit_uaepass_state=False` | HELD same file §4. **Needs Nadhir** (published wording) |
| L-46 lockout counter not reset at expiry | **HIGH** | red-team A1 | High | CONFIRMED again (`A1 ... after ONE wrong=(9, ...) ... reproduces=True`) | HELD 10-11 lead §1. **Needs Nadhir** |
| L-73 unrelated re-assessment clears an overdue periodic review | MEDIUM | lead | n/a | CONFIRMED again (`RV ... next_review=2029-10-04`, `AM ... overdue=False`) | HELD 10-18 lead §2. **Needs Nadhir** |
| L-38 freeze/CNMR raised on non-UAE-list hits | MEDIUM-HIGH | compliance CS-2 | Med | CONFIRMED again (`CS-2 ... 'pending_execution'`) | HELD. **Needs Nadhir** |
| L-53 blank `full_name` onboarded and screens clear | MEDIUM | mlro C1 | Medium | CONFIRMED again (`EN ... clear=True`) | HELD. **Needs Nadhir** |
| L-30 / L-9 rescreen banner, re-raised alerts | MEDIUM | mlro G9/G10, CS-3 | Med | CONFIRMED again (`_06` exit 0; `new open alerts [3, 4]`) | HELD `rescreen-banner-and-realert.md` |
| L-66, L-69, L-76, L-77 one-time secrets consumable concurrently | LOW-MED … INFO | red-team T1, skeptic, lead | Medium | CONFIRMED again (`T1m operators=10`, `T1w operators=10`, `BC [True, True]`, `EV [5,5,5,5,5]`, `US [5,5,5,5,5]`) | HELD. **Needs Nadhir** |
| L-78, L-79, L-80, L-81, L-75 (10-19 items) | LOW / LOW / INFO / LOW / INFO | red-team, mlro | as 10-19 | CONFIRMED again (`S3w`, `S3m`, `PW1`, `PW2`, `SS1`, `L75`) | HELD `2026-10-19-screen-cap-and-password-change.md` |
| L-67, L-47 + L-58, L-57, L-52, L-56, L-63, L-61, L-62, L-54, L-51, L-48, L-40, L-27, L-44 | LOW / INFO | various | as before | CONFIRMED again (`T2`, `OP1 500`, `OP2`, `R1`, `R2`, `P1`, `L-56`, `F6`, `NT2`, `NT3`, `SEC`, `TA1`, `GR`, `M2`, `4E`, `DL`/`DLA` all `reproduces=True`) | HELD / carry |
| L-74, L-70/L-72/L-71, L-43, L-50, L-55, L-68, L-64, L-65, L-59, L-60 and the 10-16 carry list | as before | various | as before | Unchanged: no commit | Carry |

**Severity adjudication**
- L-82 stays MEDIUM. Red-team and the skeptic agree, and so do I. It needs a logged-in operator of any role, so it is not HIGH. One small request with no limiter can still exhaust memory on a shared single instance. The production memory limit is unknown, so the outage itself stays PLAUSIBLE. I add two points the roles missed. First, the web passport route never calls `validate_file_mime`. Second, `extract_passport_data` decodes through passporteye → `skimage.io.imread(plugin='imageio')`, so red-team's `Image.MAX_IMAGE_PIXELS` step is not enough by itself. The proposal checks dimensions from the image header before any extractor runs.
- L-85: I rate it LOW, not the skeptic's Low/Med. Both cookies are strictly necessary, so there is no consent gap. The problem is an inaccurate published statement, and the fix is copy only.
- L-84: I accept the skeptic's INFO. L-83 stays LOW. It needs an MLRO login, and the 500 discloses nothing.
- Duplicates: AU1 is the skeptic's 10-07 `/audit?page=` overflow. It also affects `/feedback`. I filed it once, as L-83. No contradictions between roles today.

**FIXED on master:** none (no commits).

## 4. Combined assessment
1. Fourteen days without a commit. All 12 carried lead scripts exited 0 on `0129848` today, so nothing has been fixed.
2. L-82 is the first new item in a week that belongs on the fix-first list: one request from any operator can plausibly take every tenant down.
3. The upload path, like text inputs (L-78), has no shared limits. One `read_scan_upload` helper closes L-82 and later DOC1/U3/L-64.
4. The other new items (L-83 to L-85) are small fixes to copy or input bounds.
5. The backlog needs decisions and fix PRs, not more probing.

## 5. Corrections I made
- C-1 Created `repro_lead/checks_2026_10_20.py`: B1w, B1m (L-82), AU1, AU2 (L-83), AU3 (L-84), PV1 (L-85). It uses temp DBs and TestClient, with no network. Scratch venv from `requirements.txt` plus `passporteye` (OCR module imports it); no tesseract binary, so the pytesseract fallback was not exercised. pdfminer was skipped, so the PDF bomb variant is not checked. Output on `0129848`:
  ```
  B1w web scan 9000x9000 PNG (97 KB) -> 200, peak RSS +1453 MB -> reproduces=True
  B1m mobile scan 30 MB junk with PNG magic -> 200 (no size cap) -> reproduces=True
  AU1 /audit?page=99999999999999999999 -> 500 -> reproduces=True
  AU2 /audit?page=-1 -> 200 (no lower bound) -> reproduces=True
  AU3 officer /audit -> 303 '/'; /audit/export -> 403 body=0 bytes -> reproduces=True
  PV1 /privacy says 'three cookies'=True; names amlkit_trusted_device=False, amlkit_uaepass_state=False -> reproduces=True
  exit=0
  ```
- C-2 Created `scripts/proposals/2026-10-20-upload-image-guard-and-audit-paging.md` (HELD). It holds the shared scan-upload helper (byte cap, header-only pixel check, MIME check on the web route, limiter), the `page` bounds for `/audit` and `/feedback`, the 403 copy, and the privacy cookie rows. Not applied, because these are route and template changes.
- C-3 Owed by the 10-19 "Next run": re-runs only. `_06` (from inside `repro_lead/`), `_07`, `_10` to `_19`: all exit 0 (results quoted in §3). I copied them from their lead branches and removed them before committing.
- Not re-run: red-team `probe_scan_bomb.py` at 12000x12000 (my 9000x9000 check covers it and keeps this sandbox safe), the mlro driver, and the skeptic scripts.
- No tests added, because each would fail on master (rule 5). No existing file edited.

## 6. Decisions needed from Nadhir
1. **L-46 (HIGH): approve the lockout fix** (10-11 proposal §1), with an admin unlock that covers the MFA lock too (L-74).
2. **L-82 (MEDIUM): approve the shared scan-upload guard** (today's proposal §1). Also decide whether roles below MLRO should be allowed to call the scan routes at all (skeptic's point 2). Please also confirm the production instance memory limit so the outage severity can be settled.
3. Periodic review (L-70/L-72/L-73): event re-ratings may bring the review date forward but never push it back.
4. Atomic consume for all one-time secrets (L-66, L-69, L-76, L-77): one small PR.
5. L-53 blank-name fix; L-38/L-39 freeze scope (a)/(b)/(c); L-81 session cap (a)/(b)/(c).
6. L-85 privacy-page wording (published data-protection statement).
7. Shared helpers: password (L-47, L-58, L-67, L-80), bounded inputs (L-78, L-83, L-56, L-63, L-53, L-54, L-59), uploads (L-82, L-64, U3, L-43).
8. Carried: L-30 one-line banner fix (thirteenth request), L-9, L-79, the Low list, E4, L-44, L-40, L-42, L-31/32/33 adviser confirmation, FATF snapshot, #417 (L-23), the `github-advanced-security` 402 quota, a single de-duplicated finding register (skeptic's point 3).

## 7. Next run: carried over
- Re-run `repro_lead/checks_2026_10_20.py` (this branch) plus `_19`, `_18`, `_17`, `_16`, `_15`, `_14`, `_13`, `_12`, `_11`, `_10`, `_07` and `_06` from their lead branches. Place them in `repro_lead/` and use `PYTHONPATH=.:tests` (run `_06` from inside `repro_lead/`). `_20` needs `pip install passporteye`. Exit 1 means something was fixed; read the printed lines.
- Owed by the lead: nothing new beyond the re-runs.
- Not yet checked, for whichever role picks it up: the PDF variant of L-82 (huge page size rendered at 300 dpi); the trade-licence and legal-person web scan routes (same pattern by code, not run); the L-81 mobile-token question and the mobile password-change message (from 10-19).
- Track landing in this order: L-46 (+L-74), L-82, L-53, L-38, L-70/L-72/L-73, L-66/L-69/L-76/L-77, L-50, L-43, L-30, L-9, L-57, L-47+L-58+L-67+L-80, L-78, L-83, L-52, L-55, L-56, L-64, L-65, L-63, L-79, L-85, L-81, L-54, L-28, L-29, L-51, L-48, L-27, L-40, L-44, L-21, L-75, L-84.
