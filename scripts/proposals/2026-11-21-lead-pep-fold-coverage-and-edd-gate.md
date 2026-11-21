# HELD proposal (lead, 2026-11-21, master bfb0253): PEP-fold coverage, EDD gate, gender floor, delisting deletes decisions

Status: **HELD for human review.** Every item touches `match/engine.py`, `cases/manager.py`, routes or schema,
which the routine may not edit. Repro: `repro_lead/checks_2026_11_21.py` (exit 0 while any item reproduces).

## 1. PC1b: an absorbed PEP entity can never alert (extends PC1 / proposal 2026-11-20 §3)

Order of operations in `screen()`: `collapse_pep_duplicates` (`engine.py:332`) runs before `_persist`, which calls
`_coverage` only for surviving hits (`engine.py:419`). An entity folded into `also_listed` therefore gets no alert and
no coverage row. Repro output (local DB):

```
PC1b  onboarding alerts: [(1, 1)]  (A=1, B=2)
PC1b  alert 1 disposed -> false_positive
PC1b  re-screen: hits=[(1, 'us_cia_world_leaders')] also_listed=[2] rescreen_all={'screened': 1, 'alerts': 0, ...}; alerts ever on B=0
```

Two fixes, either sufficient for this item; (a) is already proposed on 11-20 §3:

(a) fold only with a corroborating identity signal (non-contradicting DOB **and** at least one side with a country
or DOB), so sparse same-name records stay separate hits;

(b) evaluate coverage per absorbed entity too: in `_persist`, for each kept hit, if the kept entity is covered but
any `also_listed` entity has no decided/open alert for this subject, raise the alert on the kept hit with reason
`fold_member_unreviewed`, or record the absorbed ids on the disposition so a dismissal covers exactly what the
reviewer saw:

```diff
         for h in res.hits:
             covered, why = _coverage(conn, org_id, h.entity_id, customer_id, ubo_id)
+            if covered:
+                for m in h.detail.get("also_listed", []):
+                    m_cov, _ = _coverage(conn, org_id, m["entity_id"], customer_id, ubo_id)
+                    if not m_cov and not _reviewed_as_fold_member(conn, org_id, m["entity_id"],
+                                                                   customer_id, ubo_id):
+                        covered, why = False, "fold_member_unreviewed"
+                        break
             if covered:
                 continue
```

`_reviewed_as_fold_member` looks for a decided alert on this subject whose `score_detail.also_listed` already
contains that entity id (the reviewer saw it). New test: the PC1b scenario must alert once on the re-screen after
a refresh adds a new same-name entity, and must stay quiet when the member was already in the dismissed alert's
`also_listed`. Lead recommends (a) + (b) together: (a) prevents the wrong "same person" label, (b) keeps a
dismissal scoped to what was shown.

## 2. CS-30: primary flip re-alerts (owed from 11-20, now reproduced)

```
CS30  after A delisted: hits=[(2, 'wikidata_ministers')] rescreen_all={... 'alerts': 1 ...}; alerts on B=[(1, 'open')]
```

Extra alert, not a miss; arguably correct (B was never reviewed on its own). With §1(b) the same
`_reviewed_as_fold_member` check would suppress it when B was in the dismissed alert's `also_listed`. LOW.

## 3. DL1: delisting deletes the alert and its disposition (observation)

`alerts.entity_id ... ON DELETE CASCADE` (`db.py:366`) plus `loader.load` deleting delisted entities
(`ingest/loader.py:158-168`, comment calls it "an acceptable edge case"). Repro:

```
DL1   false_positive alert rows left after delisting A: 0; alert.* audit rows: 1
```

The audit log keeps the disposition event, so the decision is not lost entirely, but the alert row (score,
score_detail, narrative, reviewer) disappears from case files and retention purges. Not reproduced for a
`true_positive` with a freeze obligation (not checked whether `freeze_obligations` cascades the same way).
Options: soft-delist (`entities.delisted_at`, excluded from candidates) instead of DELETE, or snapshot the alert
into an archive table before delete. Needs Nadhir's decision on whether this is intended (record-keeping).

## 4. ED1/ED2: EDD fields are enforced only for a *declared* high risk, not the computed rating

`api/routers/customers.py:150-155` refuses an empty source of wealth / funds only when the optional form field
`risk_level == "high"`. The model's computed rating (e.g. PEP + FATF blacklist = 115, "high, EDD required") is
not checked, and `cases/manager.onboard` (shared by web and mobile) has no check at all; `api/mobile.py` has no
`source_of_wealth` / `source_of_funds` / `purpose_of_relationship` inputs (grep finds none).

Proposed (needs Nadhir's policy decision on block vs warn): after the risk rating is computed in `onboard`, if
`requires_edd` and any of source of wealth, source of funds, purpose of relationship is empty, either (warn) set an
`edd_outstanding` flag shown on the case file and dashboard, or (block) keep the customer in `pending_edd` and
refuse `record_transaction` until an MLRO records EDD completion (who approved, when, evidence). The block form
needs a new `edd_approvals` table (append-only, modelled on `signatures`). This belongs in the lifecycle-precondition
table the skeptic proposed (CL1, SO1, MA1, ED1, ED2).

## 5. GEN1: gender mismatch silences an exact name (owed from 11-20, reachable via onboarding)

```
GEN1  G-1 gender=female hits=0 alerts=0
GEN1  G-2 gender=male hits=1 alerts=1
```

Exact name on an EU-style sanctions record with `gender='male'`, customer onboarded with `gender='female'`, no DOB or
country: `P_GENDER_MISMATCH` (-0.20, `scorer.py:316-318`) gives 0.80 < 0.85, no alert. Same class as DB1 (L-166);
the exact-name floor (proposal 2026-11-20 §1 Option B) closes it. Gender is a data-entry field; a wrong selection
is one click.
