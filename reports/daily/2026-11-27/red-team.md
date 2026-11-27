# Red team daily, 2026-11-27 (short: master unchanged)

## Instructions I ran under
Daily routine message (DATE 2026-11-27; shortcut applies when master is unchanged: probe one not-checked area, keep short; local only; push to `routine/2026-11-27-red-team`, never master; final reply = this report). Standing rules win: no production, no /system/*, no secrets, additive only, stop after delivery.

## Headline: **GREEN for this area, overall AMBER carried (PC1/PC1b open)**. The `also_listed` lines from #465 are HTML-escaped; a hostile dataset string cannot inject markup.

Master: `f3c8227121fbec1d4c3860c63b4a383a4656f975` (same as 2026-11-24 to 11-26). Newest PR still #468; none opened or merged since.

## What I did
`repro_redteam/probe_also_listed_render.py` (run against a worktree of origin/master; this branch carries no application code): loaded the app's own Jinja environment, confirmed the autoescape rule for `.html` templates, checked that the two #465 template lines (`_alert_panel.html`, `screen.html`) are not wrapped in `|safe` or an autoescape-off block, and rendered those exact expressions with a hostile dataset value (`<img src=x onerror=alert(1)>"'&`). Evidence: `evidence/probe_also_listed_render_on_f3c8227.txt`.

## Findings
- **XSS via `also_listed` (REFUTED):** env autoescape is True for `.html`; both lines come out as `&lt;img src=x onerror=alert(1)&gt;&#34;&#39;&amp;`, no raw `<img`. The values are also server-side adapter names, not user input.
- **Entity-level data not shown (unchanged, PC1):** the UI line prints dataset names only, so a merged second person's caption and entity id are not visible to the reviewer. Held fix in `scripts/proposals/2026-11-20-new-findings.md`.

## BLOCKED / not checked
- A full render of `_alert_panel.html` and `screen.html` through the real routes: the partial needs session and other context I did not build, so I tested the exact expressions through the app's Jinja environment instead.
- `tests/test_entrypoint.py::test_verified_database_starts[ok-ok]` in CI (fails in this sandbox for a missing `rm`, see 2026-11-26); the `/system/grant-trial` route over HTTP (standing rule); Stripe live-mode paths; UAE PASS callback.

## Files / commit
`repro_redteam/probe_also_listed_render.py`, `reports/daily/2026-11-27/`. Branch `routine/2026-11-27-red-team` (built on the 2026-11-26 branch; no application code touched). Commit SHA: see final reply.
