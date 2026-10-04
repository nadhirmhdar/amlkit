# Repository Cleanup Policy

**Effective:** 2026-10-04  
**Scope:** All repositories in the groAML ecosystem

## Overview

This policy establishes standards for maintaining clean, efficient, and secure repositories by removing unused code, stale branches, obsolete dependencies, and build artifacts.

## 1. Git Branch Cleanup

### 1.1 Deletion schedule
- **Merged branches**: Delete immediately after PR merge
- **Stale branches**: Delete after 30 days of inactivity with no open PRs
- **Draft/WIP branches**: Delete after 60 days of inactivity
- **Release branches**: Retain for one minor version cycle, then archive

### 1.2 Exceptions
Branches retained permanently:
- `main` / `master`
- `develop` / `staging` (if present)
- Named protection branches (e.g., `hotfix`, `release/*`)
- Active feature branches with open PRs

### 1.3 Implementation
```bash
# List merged branches (safe to delete)
git branch -r --merged origin/main

# Delete local branch
git branch -d <branch-name>

# Delete remote branch
git push origin --delete <branch-name>
```

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
- IDE artifacts: `.idea/`, `.vscode/settings.json` (shared config ✓, local overrides ✗)
- CI logs and temporary files: `.coverage`, `test-results/`

### 2.2 Local development cleanup
```bash
# Python
rm -rf .venv __pycache__ *.egg-info .pytest_cache .coverage

# Node
rm -rf node_modules package-lock.json yarn.lock .next dist

# Git
git clean -fd  # Remove untracked files
git gc --aggressive  # Optimize local repository
```

### 2.3 CI/CD artifact retention
- **Logs**: Retain for 30 days; archive to cold storage after 90 days
- **Build artifacts**: Delete after successful deployment
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
- **Minor/patch**: Automatic via dependabot or similar; fast-track reviews
- **Major**: Bundle in planned releases; test thoroughly; document breaking changes
- **Security patches**: Apply immediately; push independently of feature work

### 3.3 Policy
- No `*` or `>=` in version pins; use semantic ranges: `^1.2.0` (npm), `>=1.2,<2` (Python)
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
- Remove skipped tests (`@skip`, `.skip()`, `xit`) after 30 days; document reason in ticket if blockage
- Consolidate overlapping test cases
- Remove tests for removed features immediately

---

## 5. Database Cleanup (amlkit-specific)

### 5.1 Audit trail retention
- **Operational records** (cases, transactions, customers): Permanent
- **Audit logs**: Retain for 7 years (UAE regulatory requirement)
- **Session/token logs**: Rotate after 90 days
- **Temporary test data**: Delete after test suite passes

### 5.2 Schema migrations
- Archive `_MIGRATIONS` entries for releases older than 2 major versions
- Document rollback procedures before archiving
- Never reuse migration numbers

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
1. Rotate/revoke the credential immediately
2. Use `git-filter-repo` or `bfg` to remove from history
3. Force-push (with team notification)
4. Audit logs for misuse

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
- GitHub Actions: `desprit/delete-old-branches` or similar
- Dependabot: auto-merge minor/patch updates
- Pre-commit hooks: secret scanning, unused import detection
- CI: block merge if tests or linting is skipped

### 8.3 Responsibility
- **Individual developers**: Avoid creating tech debt; commit small, focused changes
- **Code reviewers**: Catch dead code, flag redundancy, request test cleanup
- **Maintainers**: Run quarterly automation, archive releases, update docs
- **CI/CD**: Enforce `.gitignore`, block secrets, delete old artifacts

---

## 9. Exceptions & Escalations

Document and track:
- Packages kept for compatibility (note the reason in `requirements.txt` or `package.json` comment)
- Test files with known flakiness (open GitHub issue, track separately)
- Branches retained beyond policy (e.g., for customer support) — add to `BRANCHES_RETAINED.txt`
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
- [ ] All feature branches merged or explicitly archived
- [ ] Dependencies audited; security patches applied
- [ ] Unused imports removed
- [ ] Skipped tests cleaned up or tracked as issues
- [ ] Documentation refreshed
- [ ] `CHANGELOG.md` up to date
- [ ] Database schema validated

### Post-release checklist
- [ ] Release branch tagged and documented
- [ ] Stale branches deleted
- [ ] CI artifacts older than retention policy deleted
- [ ] Archive old logs

---

**Last reviewed**: 2026-10-04  
**Next review**: 2027-01-04
