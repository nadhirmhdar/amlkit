# Four-eyes identity bound to a display name (HELD for human review)

Status: HELD (changes business logic + schema). Raised 2026-10-04 by code-reviewer CR-1,
red-team F4, mlro-user F1; adjudicated HIGH by lead.

## Defect
`amlkit/cases/review.py` `confirm_disposition` refuses self-confirmation by comparing the
confirming operator's *name* with `alert_reviews.operator` (a name string, `db.py:406`).
Since #409 (`fc80e9f`) an MLRO can rename any operator in their org from `/admin`
(`amlkit/cases/operators.py:232-281`). Propose -> rename -> confirm yields
`independent_review='completed'` and "Independent review completed." for a dismissal
reviewed by one person.

Reproduced by lead on master `05e612d` with the skeptic's
`repro_skeptic/four_eyes_rename.py` (branch `routine/2026-10-04-skeptic`):

```
confirm after rename -> ReviewOutcome(alert_id=1, status='false_positive', awaiting_second_review=False, independent_review='completed', message='Independent review completed.') | alert status: false_positive
same operator_id proposed and confirmed; alert_reviews stores only names: [('propose', 'Proposer'), ('confirm', 'Proposer Renamed')]
```

Why HIGH, not Medium: single-operator mode (`POST /admin/single-operator`) is an honest
switch that records `independent_review='single_operator'` and the note "no independent
review" (`review.py:305-312`). The rename path instead writes a record that *asserts* an
independent review that did not happen, on a sanctions false-positive dismissal. Why not
RED: requires an MLRO acting in bad faith, and the `operator.rename` audit row survives.

## Proposed fix (two layers; author: code-reviewer CR-1, red-team proposal concurs)
1. Interim, no schema change: in `rename_operator`, refuse a rename while that operator
   has a `propose` row on an alert still in `pending_review`:
   ```python
   pending = conn.execute(
       """SELECT 1 FROM alert_reviews r JOIN alerts a ON a.id = r.alert_id
          WHERE r.org_id=? AND r.operator=? AND r.action='propose'
            AND a.status='pending_review' LIMIT 1""",
       (org_id, row["name"])).fetchone()
   if pending:
       raise ValueError("This operator has a disposition awaiting independent review; "
                        "rename after it is confirmed.")
   ```
2. Root fix: additive migration
   `("alert_reviews", "operator_id", "ALTER TABLE alert_reviews ADD COLUMN operator_id INTEGER REFERENCES operators(id) ON DELETE SET NULL")`;
   `propose_disposition`/`confirm_disposition` accept `operator_id`, routes (`api/app.py`,
   `api/mobile.py`) pass `session.operator_id`; compare ids when both present, fall back
   to names only for legacy rows.
3. Related (mlro-user F4, red-team F10): make the rename duplicate check case-/whitespace-
   insensitive and NFKC-normalised.

Regression test to add with the fix (fails on master today, so not committed):
propose as A, `rename_operator(A)`, confirm as A's new name -> expect `ReviewError`.
