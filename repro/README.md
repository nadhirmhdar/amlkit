# repro/ -- tenant-isolation verification

A finding exists only if a script here reproduces it (exit 0 = defect reproduced, non-zero = not produced).
All scripts copy `fixtures/seed.db` to a scratch dir and point `AMLKIT_DB` at the copy; nothing under `amlkit/` is modified.

| Script | Purpose |
|---|---|
| `make_seed.py` | Rebuilds `fixtures/seed.db` + `fixtures/seed_ids.json` via `db.connect()`: 2 orgs (markers `ALPHA-`/`BRAVO-`), MLRO + officer each, customers, UBO, notes, txn, doc row, deadline, sanctions alerts (one staged for four-eyes), freeze, adverse-media finding, STR report, policy |
| `sweep.py` | As org B, every path-param route (web + `/api/v1`) with org A's IDs, fresh DB per request, control run with B's own IDs. Flags response containing `ALPHA` or any change to org A rows |
| `sweep_lists.py` | As org B (mlro, officer), every param-less GET route with a neutral search term; flags `ALPHA` in responses |
| `sql_scan.py` | Static: SQL on org-scoped tables with no `org_id` in the statement (triage list, not a finding) |

Run with a venv that has `requirements.txt` minus `passporteye`/`pdfminer` (they fail to build here).

`fixtures/seed.db` is gitignored (`*.db`); regenerate it with `python repro/make_seed.py` before running the sweeps.
