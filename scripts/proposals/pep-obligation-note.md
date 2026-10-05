# PEP alerts carry the sanctions "freeze, do not tip off" note (HELD)

Status: HELD for Nadhir's review. Lead 2026-10-05, finding L-19. Raised by mlro-user G1. Skeptic: CONFIRMED by code. Same mechanism as compliance CS-2 (2026-10-04, lead L-10).

## Defect (master `448a19b`)
`queries.py:557` sets `"obligation": obligation_note(classify_programs(programs))`. `screening/pf.py:87-117` returns the PF note, the TF note, or else "SANCTIONS match. Freeze without delay ...". A PEP-list entity (topic `role.pep`, no programs) gets an empty category set and so receives the sanctions freeze note. The alert's own `category` (`_category`, `queries.py:185`) is `pep`. A PEP hit calls for EDD and senior-management approval, not a freeze.

The skeptic's 2026-10-04 reading is that no auto-freeze follows, because auto-freeze runs only on `true_positive` sanction-topic alerts. That keeps this a wording defect, but the wording is an instruction to the operator.

Repro: `repro_lead/checks_2026_10_05.py` (exit 0 = reproduces):
```
PEP alert category='pep' obligation='SANCTIONS match. Freeze without delay and without prior notice; report to the supervisory authority. Do not tip off.'
```

## Proposed diff (not applied)
```diff
--- a/amlkit/queries.py
-                "obligation": obligation_note(classify_programs(programs)),
+                "obligation": (PEP_OBLIGATION if cat == "pep"
+                               else OTHER_OBLIGATION if cat == "other"
+                               else obligation_note(classify_programs(programs))),
```
The constants would go in `screening/pf.py`. The wording needs the compliance adviser to sign it off:
- `PEP_OBLIGATION = "PEP match. Not a freeze obligation. Apply enhanced due diligence, establish source of wealth and funds, and obtain senior-management approval before establishing or continuing the relationship."`
- `OTHER_OBLIGATION = "Possible match on a non-sanctions list. Review before acting; no freeze obligation follows from this list alone."`

Open question for Nadhir: should EU/UK-only hits (L-10) also get a non-freeze note? That is a legal call.

Test to add with the fix: a PEP-only entity's alert has no "Freeze" in `obligation`, and an EOCN/UN sanctions entity's alert still has it.
