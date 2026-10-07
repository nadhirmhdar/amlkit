# Compliance specialist — daily report 2026-10-07

Scope: `nadhirmhdar/amlkit` `origin/master` = `0129848`
(`01298484a7bfed106e9b2bd3a6238f98a4d2514b`, from `git ls-remote origin
refs/heads/master` at 01:17 UTC). Previous report: 2026-10-06, last named master
`8750f74`.

## Instructions I ran under

**Standing instructions (Nadhir).** Regulatory Compliance Specialist for
Federal Decree-Law 10/2025, Cabinet Resolution 134/2025, Cabinet Decision
109/2023 (UBO) and Cabinet Resolution 74/2020 (TFS). Strict, citation-grounded
interpretation: every finding cites an exact Article from `corpus/` that matches
`citation_register.json`. Six mandatory rules: standalone proliferation
financing, the 24-hour TFS freeze, the AED 55,000 cash threshold, 8-year
retention, the cascading UBO hierarchy, senior-management liability.

**This run's routine prompt (Nadhir's scheduled routine).** Check changes since
the previous report against UAE AML/CFT obligations, then check one item the
previous report listed as not checked. Mark anything not verified against a
primary source PLAUSIBLE. No production access, no `/system/*` calls, no
secrets. Additive only. Push this file to
`routine/2026-10-07-compliance-specialist`, never master. Stop after delivery:
no polling, no CI re-checks, no self-scheduled reminders.

**Changed because of dreamon.** Nothing. No dreamon message arrived this run.

**Assumptions.**
- No `corpus/` or `citation_register.json` exists in the repo. Article numbers
  come from the brief's register, a code comment or an official page, and are
  never CONFIRMED as statute.
- CONFIRMED means reproduced or read in code at cited lines, or stated on an
  official regulator page I fetched. A guidance page is not the legal text, so
  article-level mapping stays PLAUSIBLE.
- Not legal advice.

---

## Headline

**AMBER.** The two commits since the last report are sound, but the EOCN's own
guidance, now checked, says a hit on OFAC, EU or UK lists is outside the UAE
freeze regime, while the product creates a freeze obligation and a CNMR route
for such hits, and every earlier open finding is unchanged.

---

## What I did, with evidence

1. **Master and delta.** Master moved `8750f74` to `0129848`, two commits:

   ```
   0129848 fix(review): anchor four-eyes self-confirm check to operator id, not name (#426)
   1d1ef39 Type scale: five text sizes (11/12/13/14/16) and three button heights (32/40/48) (#404)
   ```

   One PR was opened and merged since the last report (#426); #404 also merged.
   Still open and not reviewed: #411 (draft database audit) and #417 (loading animation).

2. **Full suite on `0129848`**, in a scratch virtualenv outside the repo:

   ```
   2170 passed, 3 skipped, 53 warnings in 550.30s (0:09:10)
   ```

3. **Read both commits.** #426 changes `amlkit/cases/review.py`, `app.py`,
   `mobile.py` and adds a migration; 122 related tests pass. #404 is a CSS and
   markup change; its template diffs contain no legal wording.

4. **Checked the not-checked item: whether OFAC is binding for UAE DNFBPs.**
   Answered by the Executive Office for Control and Non-Proliferation (EOCN)
   TFS guidance, `https://www.uaeiec.gov.ae/en-us/un-page`, fetched today
   (HTTP 200). Findings CS-2 and CS-19 below.

5. **Reproduced what the code does** for an OFAC-only and an EU-only confirmed
   match, on real SQLite with the real review code path.

---

## Status of earlier findings

Files touched by master since the last report: `api/app.py` (5 lines),
`api/mobile.py` (4 lines), `cases/review.py`, `db.py` (one column), CSS and
templates. None of `fatf.py`, `loader.py`, `heartbeat.py`, `manager.py`,
`goaml.py`, `mail.py`, `pf.py`, `engine.py`, `queries.py` changed
(`git diff 8750f74 origin/master --name-only`). So these stand unchanged:

| Id | Finding | State |
|---|---|---|
| CS-13 | 24-hour clock keyed to disposition, not designation | Open. `amlkit/cases/manager.py:2005`, `:2010` |
| CS-14 | A PNMR cannot be created; `reports.html:12` says it can | Open. `amlkit/reporting/goaml.py:62` |
| CS-15 | No five-business-day CNMR/PNMR deadline tracking | Open |
| CS-16 | Overdue-freeze alert fires only after 24 hours | Open. Scheduler job existence UNVERIFIED |
| CS-1, CS-6, CS-7 | FATF fallback shown as fresh; five unmapped grey-list names; list drift | Open |
| CS-3, CS-4, CS-5 | Re-alerting on dismissed matches; Interpol edge block; daily refresh cadence | Open |
| 3.1, 4.2, 5.x | Cash threshold up to 1,000,000; retention anchor for occasional transactions; UBO tiers and chain | Open |
| 4.1 | Statutory retention figure | Removed from code and copy. The correct period (5 or 8 years) is still unverified. |

---

## Findings

Severity: **H** statutory exposure in behaviour or published copy, **M** control
incomplete, **L** citation or wording. Status: **CONFIRMED**, **PLAUSIBLE**,
**REFUTED** as defined above.

### CS-2 — The freeze and CNMR workflow applies to lists the UAE freeze regime does not cover (H, CONFIRMED against EOCN guidance; article mapping PLAUSIBLE)

**What the regulator says.** Upgraded from PLAUSIBLE: this was my open "is OFAC
binding?" question. The EOCN guidance page states, verbatim:

> "Which Sanctions Lists are covered under Cabinet Decision No. 74 of 2020 in
> terms of the requirement to implement TFS? The scope of Cabinet Decision No. 74
> of 2020 in implementing TFS covers the UAE Local Terrorist List and UNSC
> Consolidated List only. Other unilateral and multilateral sanctions lists are
> out of the scope of the Cabinet Decision."

> "In case any Confirmed or Partial Name Match is identified to a unilateral /
> multilateral sanctions list or other criminal lists (i.e. OFAC, EU, HMT,
> INTERPOL, etc.), the Reporting Entity should not use the CNMR/PNMR reports in
> goAML to report such cases ... however, you should consult with your relevant
> SA [supervisory authority] on the appropriate course of action and may consider
> raising an STR/SAR with the FIU".

The legal basis named is Cabinet Decision No. 74 of 2020. I could not read that
instrument, so the Article mapping is PLAUSIBLE. This is the regulator's own
FAQ, not the Decision's text, and it tells reporting entities to consult their
supervisory authority.

**What the code does.** Reproduction on real SQLite, single-operator mode, each
alert dispositioned `true_positive`:

```
ofac_sdn         topics=['sanction'] programs=['NPWMD'] -> alert true_positive; freeze obligation: {'id': 1, 'obligation_type': 'proliferation', 'risk_category': 'critical', 'status': 'pending_execution'}
eu_sanctions     topics=['sanction'] programs=[]        -> alert true_positive; freeze obligation: {'id': 2, 'obligation_type': 'sanctions', 'risk_category': 'high', 'status': 'pending_execution'}
un_consolidated  topics=['sanction'] programs=['1718']  -> alert true_positive; freeze obligation: {'id': 3, 'obligation_type': 'sanctions', 'risk_category': 'high', 'status': 'pending_execution'}
```

(The third row's programme label is a made-up string; it shows only that the
path does not look at the list.)

- `amlkit/cases/review.py:163` — `is_freeze_worthy = bool(categories) or "sanction" in topics`.
  Nothing checks which dataset the entity came from.
- The freeze table has no dataset or list column (`amlkit/db.py`, `freeze_obligations`).
- `amlkit/mail.py:292-296` — the MLRO is told "IMMEDIATE ACTION REQUIRED ...
  Execute asset freeze without delay ... File a CNMR ... within 5 business days".
  Since #419 the same email is also sent when an obligation has been pending for 24 hours.
- `amlkit/api/app.py:1542` — `freeze_obligation_file_ffr` files the CNMR for any
  executed freeze obligation.
- The product's own blog says the opposite: "A hit on OFAC or the EU list is not
  a CNMR, even if you decide to stop the business"
  (`amlkit/web/templates/blog/uae-sanctions-screening-24-hour-rule.html:87`, and
  the FAQ at `:35`).

**Exposure.** A confirmed OFAC- or EU-only match produces an instruction to
freeze the customer's assets and to file a CNMR with the EOCN, both of which the
regulator says do not apply. That risks an unlawful freeze, a wrong filing, and
a 24-hour clock and overdue alerts for an obligation that does not exist.
Proliferation-programme OFAC designees are sent down the "critical" path.

**Proposal (additive).** Carry the source dataset into the freeze decision and
text. Only `ae_local_terrorists` and `un_consolidated` hits create a freeze
obligation and the CNMR route. Other lists get EDD, a "no UAE freeze duty; consult
your supervisory authority; consider an STR/SAR" note, and no CNMR. The #421 change
already separates PEP wording this way and leaves this question open by name.

### CS-19 — OFAC is flagged "mandatory" although the guidance puts it outside the TFS regime (L, PLAUSIBLE)

`amlkit/ingest/ofac.py:23` sets `is_mandatory = True`, defined in
`amlkit/ingest/base.py` as "required by UAE law rather than merely useful". EOCN
guidance lists only the UAE Local Terrorist List and the UNSC Consolidated List
under Cabinet Decision 74 of 2020. Whether another UAE instrument or a
supervisor's expectation makes OFAC mandatory for a DNFBP is not shown by
anything I could read. Effect of the flag: an OFAC staleness breach is reported
as a mandatory-list breach and OFAC can satisfy the screening-freshness gate.
Proposal: confirm with the supervisory authority, then change the flag or the
comment.

### CS-18 — #426 fixes the four-eyes rename bypass (REFUTED as a remaining gap; L residual, PLAUSIBLE)

`confirm_disposition` now compares operator ids, not display names
(`amlkit/cases/review.py:395`), with a name fallback only when either side has no
id (`:397`). The migration adds `alert_reviews.operator_id`. 122 related tests pass, including the new
`tests/test_foureyes_rename_bypass.py`. This closes the case the red-team found after #409 let an MLRO
rename themselves. Residual: a disposition proposed before the migration has no
id, so confirming it falls back to the name comparison and the rename bypass
still works for those rows. Window: reviews pending at deploy time.

### Reviewed with no compliance gap (REFUTED)

- **#404 type scale.** Style and markup only; no change to legal or retention
  wording in the templates.

---

## BLOCKED / not checked

- **BLOCKED: primary legal text** for Law 10/2025, Cabinet Resolution 134/2025
  and Cabinet Decision 74/2020 (retention period, AED 55,000 scope, UBO
  percentage, the Article behind each TFS duty). Three official hosts refused
  this egress on 2026-10-06 (`rulebook.centralbank.ae` HTTP 403,
  `uaelegislation.gov.ae` HTTP 403 Cloudflare, `fatf-gafi.org` Cloudflare
  challenge). I did not re-attempt them today and did not try to bypass them.
  Action needed: someone drops the instruments into the repo as `corpus/`.
- **Not checked, no means:** the Cloud Scheduler jobs' real state; production
  alert and freeze counts; whether production's FATF fetch fails; whether a
  supervisory authority or another UAE instrument requires OFAC screening for
  DNFBPs (the EOCN page says to consult your supervisory authority); the
  retention period (5 or 8 years).
- **Not done by design:** no PR comment, no edit to an existing file, no
  production or `/system/*` call, no secret used. The scratch virtualenv, the
  reproduction script and the fetched page are in the session scratchpad and are
  not committed. No test or other process is left running.

## Files created and commit

| File | Branch | Commit |
|---|---|---|
| `reports/daily/2026-10-07/compliance-specialist.md` (this file) | `routine/2026-10-07-compliance-specialist` | see the final reply (a commit cannot name its own SHA) |
