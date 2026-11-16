# HELD: closure preconditions (CL1/CL2) and input normalisation for KYT and name matching (TD1, TX1/TX2, N3c)

Status: **HELD for human review** (route/business logic, lead rule 3). Master `9219e26`.
Repro: `PYTHONPATH=. python repro_lead/checks_2026_11_16.py` (exit 0 = still reproduces, 6/6 on 2026-11-16).
Raised by: mlro-user (CL1/CL2 11-16, TX1-TX3 11-14), red-team (TD1/TD2 11-14, N3c 11-16); verdicts by skeptic 11-16.

## 1. CL1/CL2: closing a customer with open TFS work (L-149, L-150)

`amlkit/cases/manager.py:784-822` `close_relationship()` checks only the exit reason, existence and not-already-closed. It reads no alerts and no `freeze_obligations`. Both callers (`api/routers/customers.py:569`, `api/mobile.py:800`) go through it, so one change covers web and mobile.

Mitigation already on master: `purge_expired()` skips customers with an unresolved freeze or an open alert, so nothing is lost. The defect is the absence of a control at exit time, not data loss.

Proposed diff (sketch):

```python
# manager.py, inside close_relationship, after the 'already closed' check
blockers = []
n_alerts = conn.execute(
    "SELECT COUNT(*) FROM alerts a JOIN screenings s ON s.id=a.screening_id"
    " WHERE s.customer_id=? AND a.org_id=? AND a.status IN ('open','escalated')",
    (customer_id, org_id)).fetchone()[0]
if n_alerts:
    blockers.append(f"{n_alerts} screening alert(s) not yet dispositioned")
n_freeze = conn.execute(
    "SELECT COUNT(*) FROM freeze_obligations WHERE customer_id=? AND org_id=?"
    " AND status IN ('pending_execution','executed_pending_report')",
    (customer_id, org_id)).fetchone()[0]
if n_freeze:
    blockers.append(f"{n_freeze} freeze obligation(s) not executed and reported")
if blockers and not override_reason:
    raise ValueError("Cannot close: " + "; ".join(blockers))
# with override: MLRO-only at the route, audit 'customer.close_override' with blockers + reason
```

Transaction alerts (`kyt`) should likely be included too; decision for Nadhir. CL2 (alerts left in the open queue) is resolved by the same block; if an override is used, leave alerts open (they still need a decision) and show a "closed customer" badge in the queue.

Tests to add with the fix: close refused with open sanctions alert (web 302+flash, mobile 422); refused with `executed_pending_report` freeze; allowed after disposition; override path MLRO-only and audited.

## 2. TD1: `direction` is free text (L-151)

`api/routers/alerts.py:54` and `api/mobile.py:1052` accept any string; `record_transaction` (`manager.py:1035ff`) stores it verbatim; `screening/kyt.py:226-230` groups structuring by `direction=?`. In/IN/" in" split the group (repro: structuring True vs False).

```python
# manager.py record_transaction, beside the method check
direction = (direction or "").strip().lower()
if direction not in ("in", "out"):
    raise ValueError("direction must be 'in' or 'out'")
```

Plus a one-off data fix (separate script, dry-run first) normalising existing rows with `lower(trim(direction))`, and reporting rows that are neither. Mobile: `direction: Literal["in", "out"]` after normalisation.

## 3. TX1/TX2: operator-typed AED equivalent and currency code (L-152, L-153)

`manager.py:1052-1089`: no FX by design; `amount_aed` only range-checked. USD 100,000 recorded as AED 1 gives 0 flags (repro). Currency `XXX` stored.

Options (decision needed): (a) validate `currency` against ISO 4217 (small static set in `datamodel.py`), and (b) a plausibility band: an org-configurable reference rate table (or a static indicative table for the top 20 currencies) and refuse or flag (`fx_implausible` alert) when `amount_aed / amount` deviates by more than, say, 25 %. (b) as a flag rather than a refusal keeps the operator able to record unusual deals while making the evasion visible.

## 4. N3c: Urdu heh and other non-Arabic letters not folded (L-154)

`names/arabic.py:44-60` folds `ک ی ے ۓ ھ` but not Urdu heh `ہ` (U+06C1). `canonical_key('عبدالله')='abdullah'`, with U+06C1 `'abdl'`; `خالد بن هاشم القحطاني` with one Urdu heh scores 0.60 vs its Latin listing (threshold 0.85).

```python
    "ہ": "ه",  # heh goal (Urdu keyboard heh) -> heh
    "ۂ": "ه",  # heh goal + hamza -> heh
    "ە": "ه",  # ae (Kurdish) -> heh
    "ڪ": "ك",  # swash kaf (Sindhi) -> kaf
    "ڕ": "ر",  # reh with small v below (Kurdish) -> reh
    "ڵ": "ل",  # lam with small v (Kurdish) -> lam
```

These are unambiguous one-to-one equivalents. `پ ژ ڤ` (peh, zheh, veh) represent different sounds (p, zh, v) and folding them to `ب ز ف` may raise false positives; red-team did not measure that. Recommend landing the six above now and taking `پ ژ ڤ` only after a false-positive run against the full list. The `tah->teh` and `teh marbuta->teh` "misses" are misspellings, not script variants, and are out of scope.

Tests: parametrised `canonical_key` equality for each new fold; the red-team probe as a regression (misses for the folded letters must go to 0).

## Landing
One PR per section; sections 2 and 4 are small and low-risk and could land first. Section 1 needs Nadhir's decision on the override and whether KYT alerts block closure.
