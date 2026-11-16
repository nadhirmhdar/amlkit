# HELD proposal 2026-10-15 (R1, R2) -- not applied, no application code edited

## R1 org slug collapses non-Latin names to "org" (amlkit/cases/operators.py:38, amlkit/api/mobile.py:~277)
`re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "org"` maps every Arabic/CJK-only org name to the slug `org`;
`organizations.slug` is UNIQUE, so only one such firm can ever register. Suggested: if the slug is empty or taken,
append a short random/ID suffix instead of rejecting; keep rejecting true duplicate display names (case/NFKC-folded).

## R2 registration skips password complexity (operators.py:32, mobile.py ~ "len(body.password) < 10")
Reset/change call `auth.validate_password_complexity`; registration only checks length >= 10. Call it in both register paths.
