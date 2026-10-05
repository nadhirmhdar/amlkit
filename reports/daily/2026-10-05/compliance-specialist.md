# Compliance specialist — daily report 2026-10-05

Scope: `nadhirmhdar/amlkit` `origin/master` = `448a19ba978ef5c97ee3e955ecad5638c8a94e1e`
(`git ls-remote origin refs/heads/master`, 2026-10-05 01:16 UTC).
Previous report: 2026-10-04, scoped to master `fc80e9f4`.

## Instructions I ran under

**Standing instructions (Nadhir).** Regulatory Compliance Specialist for
Federal Decree-Law 10/2025, Cabinet Resolution 134/2025, Cabinet Decision
109/2023 (UBO) and Cabinet Resolution 74/2020 (TFS). Strict, citation-grounded
interpretation. Every finding must cite an exact Article from `corpus/` that
matches `citation_register.json`. Focus on six mandatory rules: standalone
proliferation financing, the 24-hour TFS freeze, the AED 55,000 cash threshold,
8-year retention, the cascading UBO hierarchy, senior-management liability.

**This run's routine prompt (Nadhir's scheduled routine).** Check changes since
the previous report against UAE AML/CFT obligations, then check one item the
previous report listed as not checked. Mark anything not verifiable against a
primary source PLAUSIBLE. No production access, no `/system/*`, no secrets.
Additive only. Push this file to `routine/2026-10-05-compliance-specialist`,
never master. Stop after delivery: no polling, CI re-checks or reminders.

**Changed because of dreamon.** Nothing this run. No dreamon message arrived;
the routine prompt is the only instruction and does not conflict with my
standing role.

**Assumptions.**
- No `corpus/` or `citation_register.json` exists in the repo, so every Article
  number is from the brief's register or a code comment and is never CONFIRMED
  as law. Statutory content is at best PLAUSIBLE.
- "One not-checked item": I chose which FATF jurisdictions changed since
  February 2025. It was the only one checkable without production access.
- Not legal advice.

---

## Headline

**AMBER.** The two PRs merged since the last report add no new statutory breach,
but the FATF country data is stale and, even when the live page loads, silently
drops five of today's 22 grey-list countries (including the British Virgin
Islands and Kuwait), and open PR #416 would publish a 5-year retention claim
that conflicts with the 8-year register.

---

## What I did, with evidence

1. **Located master and diffed against the previous report's scope.**

   ```
   $ git ls-remote origin refs/heads/master
   448a19ba978ef5c97ee3e955ecad5638c8a94e1e  refs/heads/master
   $ git log --oneline fc80e9f..origin/master
   448a19b Phone fixes: ownership diagram scrolls in its panel; cookie notice no longer covers sign-in (#401)
   3d5594c Mobile API: page the alert queue past 200; dashboard states its cap and keeps score order (#402)
   05e612d Sign-in page: flowing strands, no list names (design 1A-ii) (#406)
   ```

   Eleven files changed (`mobile.py`, `queries.py`, CSS/JS, `base.html`,
   `customer.html`, `login.html`, three test files). None of the files cited by
   my earlier findings changed: a grep of `git diff --name-only fc80e9f
   origin/master` for `fatf`, `loader`, `review`, `pf`, `engine`, `kyt`,
   `manager`, `scheduler`, `source-canary`, `heartbeat`, `eu`, `interpol`,
   `app.py`, `reports`, `goaml` returned nothing. So CS-1 to CS-5 and the
   six-rule items in PR #410 stand unchanged at `448a19b`.

2. **Ran the repo's own tests for the merged work** in a scratch virtualenv
   outside the repo.

   ```
   $ pytest tests/test_mobile_alert_paging.py tests/test_mobile_390_fixes.py \
            tests/test_login_page.py tests/test_pf.py tests/test_t16_fatf_fallback.py \
            tests/test_ingest_fatf.py -q
   63 passed, 1 warning
   ```

3. **Reviewed the three merged diffs for compliance effect** (findings CS-8 and
   CS-12 below).

4. **Checked the not-checked item (FATF changes).** Primary source blocked, see
   BLOCKED. Used one secondary source and compared mechanically (CS-6, CS-7).

5. **Reviewed open PR #416** (four public blog posts that state law) against the
   brief's register (CS-9 to CS-11). Not on master, so this is early warning.
   I did not comment on the PR; this report is the channel.

---

## Findings

Severity: **H** statutory exposure in behaviour or published copy, **M** control
incomplete, **L** citation or wording. Status: **CONFIRMED** mechanism
reproduced or read at cited lines; **PLAUSIBLE** mechanism confirmed but a
legal point or a production fact cannot be verified from here; **REFUTED**
checked and not a gap.

### CS-6 — The live FATF parser silently drops grey-list countries it cannot map (H, CONFIRMED)

Obligation: EDD for customers tied to FATF-identified jurisdictions (Law
10/2025 and Res 134/2025, Articles PLAUSIBLE: no corpus). In this codebase a
`fatf_greylist` tier forces EDD, not just points: `amlkit/risk/model.py:185-192`
sets `requires_edd` for `fatf_blacklist` and `fatf_greylist`, and
`amlkit/risk/ruleset.yaml:33-38` lists `high_risk_jurisdiction` as an EDD trigger.

Evidence, from running the repo's own resolver on the current grey-list names:

```
names tried: 24
silently dropped by the live parser (no ISO mapping):
['Bolivia', 'Kuwait', 'Nepal', 'Papua New Guinea', 'British Virgin Islands', 'Virgin Islands (UK)']
```

- `amlkit/ingest/fatf.py:207-235` — `_resolve_country` returns `None` and logs a
  warning for a name missing from `_COUNTRY_TO_ISO`.
- `amlkit/ingest/fatf.py:326-327`, `:332-333` — `if resolved:` skips it. Nothing records the
  omission on the dataset row.
- `amlkit/ingest/loader.py:157-160` — the load still stamps `last_refresh`, so
  the dashboard, staleness report and audit log show FATF as fresh and complete.

Consequence: even on a day the live FATF page loads, a customer from Kuwait,
Nepal, Bolivia, Papua New Guinea or a British Virgin Islands structure is not
forced into EDD by the jurisdiction trigger, with no visible sign. The BVI is
the most material for UAE DNFBP files, since BVI holding companies are common
in client structures. (Which names the live FATF page uses is UNVERIFIED because
the page could not be fetched; the five names are the standard spellings and
the resolver also fails the "Virgin Islands (UK)" variant.)

Proposal (additive): add the missing names to `_COUNTRY_TO_ISO`, and make
`_parse_html` fail the load (raise `AdapterError`) when any listed name is
unmapped, so the dataset row shows a failure instead of freshness.

### CS-7 — The hardcoded FATF fallback has drifted from the current lists (H, PLAUSIBLE)

The comparison uses a single secondary source (Wikipedia, via a summarising
fetch) reporting the black list as of 13 February 2026 and the grey list as of
19 June 2026. It is not a primary source, so the status is PLAUSIBLE.

| | Countries |
|---|---|
| Black list, repo vs source | Identical: Iran, North Korea, Myanmar |
| Grey list, repo only (over-flagged, EDD forced when it should not be) | Algeria, Croatia, Mali, Mozambique, Nigeria, Philippines, South Africa, Tanzania |
| Grey list, source only (under-flagged, EDD not forced) | Bolivia, British Virgin Islands, Haiti, Kuwait, Laos, Nepal, Papua New Guinea |

Counts: repo fallback 23, source 22. Source's stated changes: October 2025
removed Burkina Faso, Mozambique, Nigeria, South Africa; February 2026 added
Kuwait and Papua New Guinea; June 2026 removed Algeria.

Whether the fallback is in use in production is UNVERIFIED (no production
access). It is likely: from this cloud egress the FATF site answers every
request with Cloudflare's browser challenge (`HTTP/2 403`, header
`cf-mitigated: challenge`), and Cloud Run egress is the same class of address.
The earlier report's peer-supplied fact (live fetch falling back) agrees.

Evidence in code: `amlkit/ingest/fatf.py:18-47` (fallback dictionaries),
`:53` (`_FATF_DATA_AS_OF = "2025-02-01"`), `amlkit/ingest/fatf.py:373-387`
(`load_fatf_data` writes the fallback into `fatf_countries`). Over-flagging is a
cost, not a breach. Under-flagging is the exposure, and it is the same one as
CS-6.

Proposal (additive): a committed FATF snapshot with an `as_of` date and a
max-age refusal, copying the Wikidata PEP pattern merged in #400, refreshed
by hand after each plenary (February, June, October). The next plenary is
October 2026.

### CS-8 — Mobile alert paging does not keep category priority across pages (M, CONFIRMED mechanism; impact PLAUSIBLE)

Obligation: act on a confirmed proliferation or terrorism match without delay
and within 24 hours (Law 10/2025 Art 17, Res 74/2020 Art 15, Res 134/2025 Art 32
per the register; Articles PLAUSIBLE).

Change under review: `#402` adds `limit` and `offset` to `GET /api/v1/alerts`
(`amlkit/api/mobile.py` `api_alerts`, `amlkit/queries.py` `alert_queue`). SQL
orders by score only, then Python sorts each page by category rank
(`queries.py:34`, `:569-572`). Category priority therefore holds inside a page,
not across pages. Real-SQLite reproduction, 204 PEP alerts scored 0.95 to 0.85
plus one proliferation alert scored 0.80:

```
page 1 (what a mobile client sees first): 200 alerts {'proliferation': 0, 'pep': 200} | first row category: pep
page 2: 5 alerts {'proliferation': 1, 'pep': 4} | row categories: ['proliferation', 'pep', 'pep', 'pep', 'pep']
exact category counts on the dashboard: {'pep': {'open': 204, ...}, 'proliferation': {'open': 1, ...}}
```

The mobile `GET /alerts` has no `category` filter, so a client cannot ask for
proliferation alerts directly. Mitigations that exist: the dashboard category
counts are exact, and before #402 such an alert was unreachable on mobile, so
#402 is a net improvement. The residual risk is a freeze-relevant alert sitting
on a later page while the list opens on higher-scoring PEP rows. A queue past
200 is realistic after a list load that raises many fuzzy alerts. The web queue
keeps its own category filter.

Proposal (additive): expose `category` on the mobile route and sort by category
rank before slicing a page.

### CS-9 — Open PR #416 would publish "at least five years" retention (M, PLAUSIBLE)

Register: retention is 8 years after the relationship ends or the occasional
transaction (Law 10/2025 Art 25, Res 134/2025 Art 24). PR #416
(branch `feat/groaml-blog-expansion`, head
`e2a2d95553d1eed42eabc94b23dd1a08e84eab0c`) adds, in
`uae-goaml-str-sar-filing-guide.html`, "Keep a copy of the report as filed, the
supporting evidence, and the internal decision trail ... for at least five
years" and a checklist line "We keep every filed report, its evidence and the
decision trail for at least five years." This is the same 5-versus-8 conflict
already in master (PR #410 finding 4.1), now spreading into four new public
posts. Neither figure is checked against primary text, so PLAUSIBLE. Merging as
is would put an unverified, possibly short, statutory minimum into public
guidance.

### CS-10 — #416 frames AED 55,000 only as a CDD trigger, with no cash-report duty (L, PLAUSIBLE)

The brief's register ties AED 55,000 to the DNFBP cash reporting threshold
(Res 134/2025 Art 21). The new CDD and regulatory-update posts present AED
55,000 (and AED 3,500 for wire transfers) only as occasional-transaction CDD
triggers, sourced to a vendor blog (Zigram), and never mention a cash
transaction report. The code comment at `amlkit/screening/kyt.py:25` makes the
same CDD-only framing. A reader could conclude there is no cash-report duty.
Both readings may be right for different entity types; confirming needs the
corpus. Ties to PR #410 finding 3.2 (no cash report type exists).

### CS-11 — #416 attributes figures to FIU guidance and penalties to law-firm blogs (L, PLAUSIBLE)

- STR guide: "practice and FIU guidance treat same-day to 24–48 hours ... as the
  outer edge". No FIU document is cited. Presented as guidance, it can read as a
  safe harbour for a duty the same post says has no fixed day-count.
- Penalty "AED 100,000 to AED 1,000,000" for late or missing reports is stated
  as "current UAE law" and corroborated only by Farahat & Co.
- The FIU powers (10 working days suspension, 30 days freeze) and "Circular No.
  (1) of 2026" in the regulatory-updates post cite Lexology and an unverified
  circular.
- The CDD post says a groAML case file is "examiner-ready the day an inspector
  asks for it". `research/compliance-traceability.md` §1 still records no
  independent identity-document verification (partly addressed since by the
  UAE PASS and OCR work), so the claim is stronger than the evidence.
- The posts name the 2020 instrument "Cabinet Decision No. 74" while the brief
  uses "Cabinet Resolution 74/2020". One name is wrong.

Proposal: attach primary-source Article numbers or remove the figure, and
soften the two claims that go beyond the evidence.

### CS-12 — Merged #406 and #401 (REFUTED as compliance gaps)

- `#406` removed a visually hidden sentence that claimed screening "against the
  UN, OFAC, EU, UK, UAE, FATF, PEP and adverse media lists"
  (`amlkit/web/templates/login.html`). With EU non-mandatory and FATF often on
  fallback data, dropping the claim lowers misrepresentation risk. No action.
- `#401` adds `role="region"`, an `aria-label` and `tabindex` to the UBO
  diagram panel (`amlkit/web/templates/customer.html:188-194`). Accessibility
  only. It does not touch UBO logic.

### Carried forward unchanged (no cited file changed on master)

CS-1 to CS-5 from yesterday and the six-rule items in PR #410 (freeze clock at
disposition, overdue check not wired on Cloud Run, cash threshold configurable
to 1,000,000, 5-versus-8-year retention copy, UBO tier 2 missing, chain not
resolved). Full table: `reports/daily/2026-10-04/compliance-specialist.md` on
`claude/sweet-ramanujan-qr7u94` (PR #410, draft). No open or merged PR since
yesterday addresses them.

---

## BLOCKED / not checked

- **BLOCKED: primary-source FATF check.** `www.fatf-gafi.org` returns `HTTP/2
  403` with `cf-mitigated: challenge` (Cloudflare browser challenge) to this
  session's egress. I did not try to defeat the challenge. Action needed:
  someone fetches the current "Black and grey lists" page from an unblocked
  network (or pastes the plenary statement) so CS-7 can move from PLAUSIBLE to
  CONFIRMED. The same step would produce the snapshot proposed in CS-7.
- **Not checked, no means:** primary legal text for every Article (no corpus);
  Cloud Scheduler job state and refresh audit rows; whether production's FATF
  fetch actually fails; the actual alert counts and which datasets produced
  them; the Interpol 403 body; whether OFAC is binding for UAE DNFBPs; whether
  the FATF page spells the five dropped names as the resolver expects.
- **Not done by design:** no comment on PR #416, no edit to any existing file, no
  production or `/system/*` call, no secret used.

## Files created and commit

| File | Branch | Commit |
|---|---|---|
| `reports/daily/2026-10-05/compliance-specialist.md` (this file) | `routine/2026-10-05-compliance-specialist` | see the final reply (a commit cannot name its own SHA) |

Scratch material (virtualenv, `paging_check.py`, the FATF block pages) lives in
the session scratchpad and is not committed.

---

## Addendum, 2026-10-05 04:41 UTC (unscheduled re-run; no change in findings)

This re-run was fired by mistake and was stopped on the lead's instruction, so nothing above was re-checked. Since the report above (master `448a19b`), master moved only to `28e4b51` (PR #416, the four blog posts). The merged blog files are identical to the PR head `e2a2d95` that CS-9 to CS-11 reviewed, so those three findings now describe published copy on the public `/blog` routes (`amlkit/api/app.py:2844`, `:2861`), still PLAUSIBLE; nothing else changed in the files behind CS-1 to CS-8. Two facts from the part of the run completed before the stop: the Interpol Red Notices endpoint answers this session's egress with an Akamai edge denial (`HTTP/2 403`, "Access Denied", `server: AkamaiGHost`), which matches the CS-4 reading that it is an edge block and not an application error (production's response body remains UNVERIFIED); and both primary legal sources refused this egress with `HTTP/2 403` (the Central Bank Rulebook page for Cabinet Resolution 134/2025 and `uaelegislation.gov.ae`), so the retention question behind CS-9 (the PR and a web-search summary say "at least five years", the brief's register says 8 years under Law 10/2025 Art 25 and Res 134/2025 Art 24) is still unresolved and BLOCKED on primary text. Lead for the next run: a search result named `https://uaelegislation.gov.ae/en/legislations/3857/download` as the Cabinet Resolution 134/2025 download; I did not fetch it.
