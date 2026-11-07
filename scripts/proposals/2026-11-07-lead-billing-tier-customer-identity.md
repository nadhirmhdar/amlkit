# HELD proposal, lead 2026-11-07: BL1 tier fail-open, CR1/CR2/CR3 customer identity

Status: **HELD for Nadhir**. Nothing here is applied. Each item edits existing business logic
(rule 3). Reproduced on master `6560fb0` by `repro_lead/checks_2026_11_07.py` (exit 0 = still open).
Red-team's `scripts/proposals/2026-11-07-new-findings.md` (branch `routine/2026-11-07-red-team`)
covers BL1/BL2 in prose. This file adds a concrete diff for BL1 and covers the mlro-user items.

## 1. BL1: an unknown `metadata.tier` becomes the plan and is then unlimited (LOW)

`amlkit/billing/service.py:100-102`: `tier = config.tier_for_price(...) or metadata.tier` is stored
without checking it against `PLANS`. The checkout path in the same file (`:136`) does check
(`tier in PLANS`). `amlkit/billing/limits.py:138-139` treats a plan key that is not in `PLANS` as
"retired from the code: do not punish the org" and returns legacy (unlimited) state.

Proposed diff (service.py only, smallest change):

```diff
-    tier = config.tier_for_price(_sub_price_id(sub)) or (sub.get("metadata") or {}).get("tier")
+    tier = config.tier_for_price(_sub_price_id(sub))
+    if tier is None:
+        meta_tier = (sub.get("metadata") or {}).get("tier")
+        tier = meta_tier if meta_tier in PLANS else None  # unknown: keep the stored plan
```

Second, separate decision: should `limits.org_state` fail closed on an unknown plan key (apply
Starter limits) instead of unlimited? Only a true legacy org (`plan='trial'` and no
`trial_ends_at`) should be unlimited. Changing that fallback could affect an org whose plan was
renamed in code, so it is a policy call.

Test (add once the fix lands; it fails on master today):

```python
def test_unknown_metadata_tier_keeps_plan(conn, org_starter_active, stripe_cfg):
    sub = {"id": "sub_1", "status": "active", "customer": "cus_1",
           "metadata": {"tier": "enterprise-free"},
           "items": {"data": [{"price": {"id": "price_unknown"}}]}}
    apply_subscription(conn, org_starter_active, sub, stripe_cfg, event_type="customer.subscription.updated")
    assert plan_of(conn, org_starter_active) == "starter"
```

BL2 (INFO): guard `_sub_price_id` / `_period_end` with `isinstance(items, list) and items and
isinstance(items[0], dict)`. This is red-team's proposal; no separate diff here.

## 2. CR1: customer identity cannot be corrected after onboarding (MEDIUM)

Evidence: every `UPDATE customers SET` outside `db.py` changes retention, status, risk factors,
or (UAE PASS, `manager.py:1509`) fills fields that are **empty**. No web or mobile route edits
`full_name`, `name_arabic`, `birth_date`, `nationality`, `id_number` (route scan in the repro).
A misspelt name stays on the file, and the onboarding screening ran against the misspelt string.

This is a feature, not a patch. Before code is written, Nadhir needs to decide:
- which fields are correctable (proposed: full_name, name_arabic, birth_date, gender, nationality/
  nationalities, id_type+id_number, trade_licence);
- whether a sanctions-relevant change (names, DOB, nationality) needs a second person (four-eyes),
  like dispositions do;
- that a reason is mandatory.

Proposed shape, to follow `complete_periodic_review`:
- `cases.manager.correct_identity(conn, *, org_id, customer_id, changes, reason, actor)`:
  validate (same validators as `onboard`), refuse on a closed customer, recompute
  `canonical_key`, write `UPDATE customers ... WHERE id=? AND org_id=?`, audit
  `customer.identity_corrected` with `{"before": {...}, "after": {...}, "reason": ...}`, then
  call `screen(..., trigger="identity_correction", customer_id=...)` on the new name (and Arabic
  name). Earlier screening rows are kept, because they are the record of what was screened when.
- Web `POST /customers/{id}/identity` (MLRO only, CSRF) and mobile
  `PATCH /api/v1/customers/{id}/identity` (422 on ValueError), both thin.
- Carry `next_review` forward (do not reset the periodic-review clock; CLAUDE.md convention).

## 3. CR2: no duplicate-person warning at onboarding (LOW/MEDIUM)

Proposed: in the web `/customers/new` and mobile onboard handlers, before `onboard()`, look up
`SELECT id, reference FROM customers WHERE org_id=? AND canonical_key=? AND birth_date IS ?
AND status='active'`. If a row exists and the form does not carry `confirm_duplicate=1`, re-render
with a warning naming the existing reference(s). A warning, not a block: real namesakes exist.
Audit `customer.duplicate_override` when the officer confirms. This also gives KYT cross-record
aggregation (K1) a link to build on later.

## 4. CR3: references are unique case-sensitively (LOW)

`db.py:305` `UNIQUE (org_id, reference)` has no `COLLATE NOCASE`. Changing the constraint needs a
table rebuild, and existing data may already hold case-only pairs. Proposed instead: an
application check in `onboard()` (both web and mobile reach it):

```python
if conn.execute("SELECT 1 FROM customers WHERE org_id=? AND lower(reference)=lower(?)",
                (org_id, reference)).fetchone():
    raise ValueError(f"Reference {reference!r} already exists (references are not case-sensitive).")
```

Run a one-off read-only query on production first to list existing case-only pairs.
