<!--
Source of truth for the "Issue triage" routine (trig_01ETKZRFYHGqii6o5K8WH9wR).
The routine itself lives in claude.ai (Settings -> Routines); its prompt is NOT
read from this file. After changing this file, paste the body below the line
into the routine's prompt at https://claude.ai/code/routines/trig_01ETKZRFYHGqii6o5K8WH9wR
so the two stay in step.

Why this version (issue #252): the previous prompt opened a new dated
"Health: ... — <date>" issue and a new dated "Triage summary: <date>" issue
every day a condition persisted, so one unassigned critical issue (#85)
produced a fresh issue daily with no escalation. This version keeps one issue
per unresolved condition, comments only when something changes, flags an
unassigned critical issue on that issue itself, and escalates once after
3 days.
-->

---

Every 6 hours: run amlkit's full health check, issue triage, and improvement log for nadhirmhdar/amlkit.

**Golden rule (issue #252): never open a new issue for a condition that is already being tracked.** One open issue per unresolved condition, updated in place. Comment only when something changes, or when an escalation step below says so. A repeat of yesterday's finding is not news.

---

## Phase 1 — Health check

### 1a. CI status on master

  gh run list --repo nadhirmhdar/amlkit --branch master --limit 5 --json databaseId,name,status,conclusion,createdAt,headSha

For any failed runs in the last 6 hours, get failure details:
  gh run view <id> --repo nadhirmhdar/amlkit --log-failed 2>&1 | head -100

### 1b. Source canary freshness

  gh run list --repo nadhirmhdar/amlkit --workflow source-canary.yml --limit 3 --json databaseId,status,conclusion,createdAt

Flag as stale if: latest run failed OR latest run is more than 25 hours old.

### 1c. Unassigned critical issues: handled ON the critical issue itself, never as a new issue

  gh issue list --repo nadhirmhdar/amlkit --label critical --state open --json number,title,assignees,createdAt,comments

For each open critical issue with no assignee:
1. Read its comments: gh issue view <n> --repo nadhirmhdar/amlkit --comments --json comments
2. Find the most recent comment from this routine. Its body starts with "**Unassigned critical (health check)**".
3. Then:
   - **No such comment yet:** add one: "**Unassigned critical (health check)** — first flagged <today's date>. This issue is labelled critical and has no assignee. Assign an owner, or relabel it if it is not critical." Do not mention anyone.
   - **First flagged 3 or more days ago, no escalation comment yet:** add ONE escalation comment: "**Unassigned critical (health check) — escalated** after <N> days unassigned. @nadhirmhdar please assign an owner or relabel." Also add the label `escalated`: gh label create escalated --repo nadhirmhdar/amlkit --color b60205 --force; gh issue edit <n> --repo nadhirmhdar/amlkit --add-label escalated
   - **Already escalated:** do nothing. Do not comment again. The escalation stands until a human assigns or relabels.
4. When a previously flagged critical issue now has an assignee or is closed, do nothing; the condition has cleared.

Never create a `health-check` issue for an unassigned critical issue.

### 1d. CI / source-canary problems → one persistent issue per condition

Conditions: "CI failing on master" (1a) and "Source canary stale or failing" (1b).

All clear (CI green in last 6h, sources fresh <25h): log "Health check <date> <time> UTC: all clear". Then, for each OPEN `health-check` issue whose condition has now cleared, comment "Cleared at <date> <time> UTC: <one line of evidence>" and close it: gh issue close <n> --repo nadhirmhdar/amlkit --reason completed. Do not create any issue.

Problem found, for each condition:
  gh label create health-check --repo nadhirmhdar/amlkit --color 6e40c9 --force
  gh issue list --repo nadhirmhdar/amlkit --label health-check --state open --json number,title,body,comments
- **An open `health-check` issue for this condition exists** (match the condition name in the title, ignore any date): comment ONLY if the details changed (a new failing run ID, a different failing job or source, a different error). If it is the same failure as the last comment, do nothing.
- **None exists:** create one, with NO date in the title:
    gh issue create --repo nadhirmhdar/amlkit --title "Health: <condition name>" --label health-check --body "<what failed, run IDs, first seen <date>, recommended action — under 400 words>"

---

## Phase 2 — Issue triage

### 2a. Fetch open issues

  gh issue list --repo nadhirmhdar/amlkit --state open --json number,title,labels,assignees,createdAt,updatedAt --limit 50

Ignore issues labelled `health-check` or `triage-summary` when triaging; those are this routine's own issues.

### 2b. Identify issues needing triage

An issue needs triage if it lacks BOTH a category label (bug, feature, improvement, question) AND a priority label (critical, high, medium, low).

For each such issue:
1. Categorize: bug, feature, improvement, or question
2. Priority: critical, high, medium, or low
3. Flag duplicates among open issues
4. Suggest assignee by area: auth, screening, reporting, mobile, ingest, risk

### 2c. Ensure labels exist then apply

  for label in "bug:d73a4a" "feature:0075ca" "improvement:cfd3d7" "question:e4e669" "critical:b60205" "high:e11d48" "medium:f97316" "low:84cc16"; do
    name=${label%%:*}; color=${label##*:}
    gh label create "$name" --repo nadhirmhdar/amlkit --color "$color" --force
  done

  gh issue edit <number> --repo nadhirmhdar/amlkit --add-label "<category>,<priority>"

### 2d. Comment on critical/high issues

  gh issue view <number> --repo nadhirmhdar/amlkit --comments --json comments

If no comment containing "Triage assessment" exists:
  gh issue comment <number> --repo nadhirmhdar/amlkit --body "**Triage assessment**\n- **Category:** <category>\n- **Priority:** <priority>\n- **Suggested assignee:** <area or unassigned>\n- **Notes:** <one-sentence rationale>"

### 2e. Triage summary: ONE rolling issue, edited in place

If any open Critical or High issues exist:
  gh label create triage-summary --repo nadhirmhdar/amlkit --color 8957e5 --force
  gh issue list --repo nadhirmhdar/amlkit --label triage-summary --state open --json number,title,body
- **None open:** create one with NO date in the title:
    gh issue create --repo nadhirmhdar/amlkit --title "Triage summary (rolling)" --label triage-summary --body "<table below>"
- **One open:** rewrite its body with the current table: gh issue edit <n> --repo nadhirmhdar/amlkit --body "<table below>". Do NOT comment and do NOT create a new one. If the table is unchanged from the current body, do nothing at all.
- **More than one open** (left over from the old daily format): keep the newest, close the others with the comment "Superseded by #<newest> (rolling triage summary)".

Table body:
  "Last updated <date> <time> UTC\n\n| # | Title | Category | Priority | Assignee |\n|---|---|---|---|---|\n<one row per open critical/high issue>"

If no critical/high items: close any open `triage-summary` issue with the comment "No open critical/high issues as of <date>." and log a one-liner.

---

## Phase 3 — Improvement log (Mondays only)

Skip this phase unless today is Monday.

  gh issue list --repo nadhirmhdar/amlkit --state closed --limit 30 --json number,title,labels,closedAt
  gh api repos/nadhirmhdar/amlkit/commits?per_page=20

Identify recurring themes (auth bugs, data quality, performance regressions) with 2+ instances that are not already tracked by an open issue. Do not count this routine's own `health-check` or `triage-summary` issues as incidents.

For each theme:
  gh issue create --repo nadhirmhdar/amlkit \
    --title "Improvement: <theme>" \
    --label improvement \
    --body "<pattern, N incidents, suggested approach — under 400 words>"

---

## Notes
- Do NOT modify any files or commit anything
- Prefer adding a comment to an existing issue over creating a duplicate, and prefer doing nothing over repeating an unchanged finding
- If nothing needed action, log a brief confirmation
