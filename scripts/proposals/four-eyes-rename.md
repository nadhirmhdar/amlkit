# HELD: four-eyes can be bypassed by renaming the proposer; operator names can be look-alikes
Status: HELD. Evidence: probe_csrf_session.txt (section 1), probe_rename_authz.txt.

`review.py:381` compares `operator.strip() == proposal["operator"].strip()` (display names). The new
`POST /admin/operators/{id}/rename` (#409) lets an MLRO change a name, so: officer proposes, MLRO renames the officer,
the same officer confirms. Reproduced over HTTP: review rows `('BRAVO-officer','propose'), ('Renamed Officer','confirm')`,
alert ends `false_positive`. An MLRO can already enable single-operator mode, so the added risk is an MLRO colluding with,
or being, the proposer while four-eyes is meant to be on, and audit rows that no longer join by name.

Names are also accepted as: `BRAVO-mlro​`, a Cyrillic homoglyph copy of an existing name, a case variant, `system`,
a name containing NUL (`a b\x00c`) and an RLO override. UNIQUE(org_id,name) is exact-string, so none collide.

Proposed change (two parts):
1. Record `operator_id` on the proposal (additive column `alert_reviews.operator_id`, migration in `_MIGRATIONS`) and
   compare ids in `confirm_disposition`; fall back to names only for legacy rows.
2. In `rename_operator`: reject characters in Unicode categories Cc/Cf/Cs/Co, NFKC-normalise, reject a name whose
   NFKC-casefold or confusable-skeleton equals another operator's in the org, and reject reserved actors
   (`system`, `scheduler`, `admin`, `api`).
Tests: rename-then-confirm must still raise ReviewError; look-alike rename must be refused.
