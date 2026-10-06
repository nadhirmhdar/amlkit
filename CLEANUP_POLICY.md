# Repository Cleanup Policy

**Effective:** 2026-10-04  
**Scope:** All repositories in the groAML ecosystem

## Overview

This policy establishes standards for maintaining clean, efficient, and secure repositories by removing unused code, stale branches, obsolete dependencies, and build artifacts.

## 1. Git Branch Cleanup

### 1.1 Deletion schedule
- **Merged branches**: Delete immediately after PR merge
- **Stale branches**: Delete after 30 days of inactivity, only if no open PR has the branch as its head. Before deleting an unmerged stale branch, confirm its PR is merged or closed.
- **Draft/WIP branches**: Delete after 60 days of inactivity, under the same open-PR rule
- **Release branches**: Retain for one minor version cycle, then delete the branch after confirming the release is tagged. Release branches are not archived anywhere else: the tag is the archive.

Never delete a branch that is the head of an open PR.

None of these automatic deletion rules apply to `routine/*` or `claude/*` branches (see 1.2). Those branches carry the daily team reports (`routine/<DATE>-<role>`) and the work behind open pull requests (`claude/*`); they are removed only by a person, case by case, after the report has been read or the PR closed.

### 1.2 Exceptions
Branches retained permanently:
- `main` / `master`
- `develop` / `staging` (if present)
- Named protection branches (e.g., `hotfix`, `release/*`)
- Any branch that is the head of an open PR (never delete it; this is a hard rule, not a time limit)
- `routine/*` (daily team report branches) and `claude/*` (agent work branches, including those behind open PRs): exempt from every automatic deletion rule in 1.1 and from any branch-cleanup automation in 8.2

### 1.3 Implementation
```bash
# List candidate branches (a starting point for review, NOT a delete list)
git branch -r --merged origin/master    # default branch is `master`

# Delete local branch
git branch -d <branch-name>

# Delete remote branch (one named branch at a time, after review)
git push origin --delete <branch-name>
```

The `--merged` output is not safe to delete from as it stands. It includes `origin/master`, `origin/HEAD`, every `claude/*` branch, and brand-new branches that have no commits of their own yet (for example a `routine/*` report branch before its first push), because those are trivially "merged". Always exclude:
- `master` and `origin/HEAD`
- `routine/*` and `claude/*`
- any branch that is the head of an open PR (check with `gh pr list --state open --json headRefName`)

Review the filtered list by hand. Never pipe `git branch -r --merged` (or any branch listing) into a delete command.

**Responsibility**: Code reviewer at merge time; automation or maintainer via quarterly sweep.

---

## 2. Build Artifacts & Cache Cleanup

### 2.1 Exclude from version control
Files never committed (add to `.gitignore`):
- `node_modules/`, `venv/`, `.venv/`, `__pycache__/`
- `.pyc`, `.pyo`, `*.egg-info/`
- `dist/`, `build/`, `.next/`, `.nuxt/`
- `.env`, `.env.local`, `*.key`, secrets files
- OS-generated files: `.DS_Store`, `Thumbs.db`
- IDE artifacts: `.idea/` and `.vscode/settings.json` are never committed. If the team later wants shared editor settings, commit a separate, deliberately curated file (for example `.vscode/settings.shared.json`) and keep each person's own `settings.json` ignored
- CI logs and temporary files: `.coverage`, `test-results/`

### 2.2 Local development cleanup
```bash
# Python
rm -rf .venv __pycache__ *.egg-info .pytest_cache .coverage

# Node
rm -rf node_modules .next dist
# Lockfiles (package-lock.json, yarn.lock, requirements.lock) are committed; never delete them as cleanup

# Git
git clean -nd  # DRY RUN: list untracked files that would be removed; review the list by hand
# Only after reviewing: git clean -fd  (irrecoverably deletes untracked work; there is no undo)
git gc --aggressive  # Optimize local repository
```

### 2.3 CI/CD artifact retention
- **Logs**: Retain for 30 days; archive to cold storage after 90 days
- **Build artifacts**: Delete CI workspace artifacts (temporary build outputs) after successful deployment. Never delete container images behind live or recent Cloud Run revisions; they are the rollback targets
- **Test reports**: Retain for 6 months; summarize in release notes
- **Security scan results**: Retain indefinitely; lock old issues

**Automation**: Configure via CI platform (GitHub Actions, Cloud Build, etc.)

---

## 3. Dependency Cleanup

### 3.1 Unused dependencies
Quarterly audit:
```bash
# Python
pip list  # Review against requirements.txt

# Node
npx depcheck

# General
grep -r "import.*X" . | wc -l  # Manual spot-check
```

Remove packages with zero imports. Document reasons for unusual/experimental dependencies in code comments.

### 3.2 Version upgrades
- **Minor/patch**: Dependabot or similar opens PRs automatically (no `dependabot.yml` exists yet, so this is to be set up); a person merges after CI passes; fast-track reviews
- **Major**: Bundle in planned releases; test thoroughly; document breaking changes
- **Security patches**: Apply immediately; push independently of feature work

### 3.3 Policy
- No `*` and no unbounded `>=` in version pins; use a bounded range: `^1.2.0` (npm), `>=1.2,<2` (Python, the lower bound with an upper cap is allowed). `requirements.txt` on master still uses unbounded `>=` on most lines; moving them to bounded ranges is a follow-up, not a precondition for this policy
- Review deprecation warnings quarterly
- Remove pre-release/beta dependencies before release branches

---

## 4. Code Cleanup

### 4.1 Dead code removal
Remove when identified:
- Unused functions, classes, imports (no "commented-out" placeholders)
- Unreachable branches (dead if-statements, after returns)
- Obsolete feature flags and shims (remove once rollout is complete)
- Stub implementations left from refactors

**No**: empty commit messages, commits reverting only comments, "cleanup" commits without substance.

### 4.2 Redundant code
Consolidate before merging:
- Duplicate functions → extract helper or shared module
- Repeated patterns → identify the abstraction
- Copy-pasted logic → shared utility

Threshold: Three identical lines = opportunity to simplify. Prefer merging PR that removes duplication.

### 4.3 Test cleanup
- Skipped tests (`@skip`, `.skip()`, `xit`) older than 30 days: fix them or file an issue with the reason. Do not delete conditional `skipif` tests (for example platform- or dependency-conditional ones such as the `skipif` marks in `tests/test_entrypoint.py` and `tests/test_evidence_pdf.py`); they provide coverage on the platforms where the condition holds
- Consolidate overlapping test cases
- Remove tests for removed features immediately

---

## 5. Database Cleanup (amlkit-specific)

### 5.1 Audit trail retention
- **Operational records** (cases, transactions, customers): Kept for the firm's retention plan of 10 years, counted as in `amlkit/cases/manager.py` (`RETENTION_YEARS`); the statutory minimum is set by law and is not restated here. Deletion happens only through `cases.manager.purge_expired()`, which is disabled unless `AMLKIT_PURGE_ENABLED=true` (exactly the lowercase string `true`; any other value, including `1`, leaves it disabled). `amlkit/cases/applications.py` has a separate `purge_expired` for expired public application requests; it is called by Cloud Scheduler and has no env gate. Do not enable customer-record purge in production until PR #422 (retention/purge safety net) is merged
- **Audit logs**: Follow the same 10-year retention plan. The `audit_log` table is append-only (database triggers block UPDATE and DELETE), so no cleanup job may prune it; any change to that needs a separate decision
- **Session and auth logs**: Rotate `auth_log` rows (login attempts, logouts, password resets) and expired `sessions` rows after 90 days. `auth_log` is a separate table from the append-only `audit_log` and is not covered by the audit retention rule above
- **Temporary test data**: Delete after test suite passes

### 5.2 Schema migrations
- Do not archive, remove or edit existing `_MIGRATIONS` entries. `_MIGRATIONS` is an unnumbered tuple of `ALTER TABLE ... ADD COLUMN` statements, each guarded by a column-presence check. As of master, 46 of its 72 entries add columns that the `SCHEMA` `CREATE TABLE` text does not contain, so removing entries would break the upgrade of any database created before them. Add new entries at the end only.
- Table rebuilds for constraint changes stay in their dedicated functions in `db.py`; document the rollback procedure in the PR that adds one.

### 5.3 Database maintenance
```bash
# SQLite (amlkit)
PRAGMA optimize;  # Run monthly after heavy write periods
PRAGMA integrity_check;  # Validate before backups
```

---

## 6. Documentation Cleanup

### 6.1 Stale documentation
Review and update every 6 months:
- README files (API endpoints, setup steps)
- Architecture docs (diagrams, data flow)
- Troubleshooting guides (reproduce issues; remove if no longer valid)
- Inline code comments (remove if documenting obvious code; keep non-obvious logic)

**Mark as outdated**: Add `[STALE]` prefix to section heading; create issue to refresh.

### 6.2 Temporary notes
- Remove `TODO`, `FIXME`, `HACK` comments after resolution
- If a workaround predates 2 releases, document it formally or remove it
- Never commit placeholder text or WIP notes

---

## 7. Security & Secrets Cleanup

### 7.1 Pre-commit checks
All commits must pass:
```bash
git-secrets --scan  # or similar secret detection
```

If a secret was committed:
1. Rotate/revoke the credential immediately. Rotation is the real fix: once a secret has been pushed, treat it as compromised whatever happens to history
2. Audit logs for misuse
3. Rewriting history (`git-filter-repo` or `bfg`) is optional hygiene, not a substitute for rotation, and needs the owner's explicit approval first. `master` is not branch-protected and every push to `master` auto-deploys to Cloud Run, so before any history rewrite or force-push: pause deploys, and afterwards check that GitHub's cached PR refs and any forks are purged (GitHub keeps the old commits reachable through `refs/pull/*` until they are removed)

### 7.2 Archived branches
Before deleting a branch, confirm no secrets were logged:
```bash
git log <branch> | grep -i "password\|token\|key\|secret"
```

---

## 8. Execution

### 8.1 Quarterly cleanup schedule
- **Week 1**: Branch audit (stale branches, merge cleanup)
- **Week 2**: Dependency audit and upgrades
- **Week 3**: Dead code sweep (Explore tool, grep for unreachable code)
- **Week 4**: Documentation review

### 8.2 Automation
Enable where possible:
- GitHub Actions: `desprit/delete-old-branches` or similar, configured to skip `routine/*` and `claude/*` (see 1.2)
- Dependabot: open update PRs automatically; a person merges after CI passes (no auto-merge)
- Pre-commit hooks: secret scanning, unused import detection
- CI: block merge if tests or linting is skipped

### 8.3 Responsibility
- **Individual developers**: Avoid creating tech debt; commit small, focused changes
- **Code reviewers**: Catch dead code, flag redundancy, request test cleanup
- **Maintainers**: Run quarterly automation, tag and close out release branches, update docs
- **CI/CD**: Enforce `.gitignore`, block secrets, delete old artifacts

---

## 9. Exceptions & Escalations

Document and track:
- Packages kept for compatibility (note the reason in `requirements.txt` or `package.json` comment)
- Test files with known flakiness (open GitHub issue, track separately)
- Branches retained beyond policy (e.g., for customer support) — record in `BRANCHES_RETAINED.txt` (to be created; does not exist yet)
- Dead code kept deliberately (document in adjacent comment)

**Review exceptions quarterly**; escalate to team lead if any exceed 90 days.

---

## 10. Enforcement

- **Policy violations**: Non-blocking in code review (educate, not block)
- **Merge conflicts from stale branches**: Blocker; encourage frequent rebases
- **Secrets in committed history**: Blocker; escalate to security team
- **Failing tests kept merged**: Blocker on next PR from that author

---

## Appendix: Cleanup Checklists

### Pre-release checklist
- [ ] All feature branches merged, or explicitly retained (see `BRANCHES_RETAINED.txt`, to be created)
- [ ] Dependencies audited; security patches applied
- [ ] Unused imports removed
- [ ] Skipped tests cleaned up or tracked as issues
- [ ] Documentation refreshed
- [ ] `CHANGELOG.md` up to date (to be created; does not exist yet, skip until it does)
- [ ] Database schema validated

### Post-release checklist
- [ ] Release branch tagged and documented
- [ ] Stale branches deleted
- [ ] CI artifacts older than retention policy deleted
- [ ] Archive old logs

---

**Last reviewed**: 2026-10-04  
**Next review**: 2027-01-04
