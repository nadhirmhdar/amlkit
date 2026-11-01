<!--
Source of truth for the findings-register paragraph of the daily LEAD routine.
The lead prompt itself lives in claude.ai (Settings -> Routines); it is NOT read
from this file. After changing this file, paste the body below the line into the
lead routine's prompt so the two stay in step.
-->

---

**Findings register: `reports/findings.csv` (on master).**

The register is the one machine-readable list of every L-id the lead has ever issued. Each run, after the consolidated report is written and before finishing:

1. Read `reports/findings.csv`. Columns: `id, title, severity, first_seen, roles, repro_script, proposal_file, status, fixed_by_pr`.
2. **Append a row for every new L-id** in today's report (next free number; never reuse or renumber an id). `first_seen` is today's date (YYYY-MM-DD), `severity` and `roles` are as in the report's table, `title` is one line (no file:line needed), `repro_script` and `proposal_file` are the file names only (blank if none).
3. **Flip `status` for existing rows** whose state changed. Allowed values: `OPEN` (confirmed, needs a fix or a decision), `CARRY` (known, deliberately not worked this run), `FIXED` (a merged PR closed it), `REFUTED` (not a defect). When a row becomes `FIXED`, fill `fixed_by_pr` with the PR number(s), `;`-separated, no `#`. Take FIXED only from a repro that now prints `reproduces=False`, or from `git log` showing the merged PR.
4. Do not delete rows, and do not edit `first_seen`. A regression of a FIXED id flips it back to `OPEN` and gets a note in the report; it does not get a new id unless the cause differs.
5. Keep the file sorted by numeric id, UTF-8, LF line endings, standard CSV quoting (quote any field containing a comma, quote or newline).
6. Commit the file on the routine branch with the report. State in the report how many rows were appended and how many flipped.
