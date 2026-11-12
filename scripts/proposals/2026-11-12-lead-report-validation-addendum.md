# Addendum to 2026-11-11-lead-goaml-report-validation.md (HELD)

Status: HELD for human review. Adds two items to the 11-11 proposal; it does not replace it.

## 1. Web builder reaches the same gaps (confirmed by mlro-user 11-12, `webrep12`)
The web `POST /reports` path goes through the same `save_report` / `report_finalize_error`, so the
11-11 proposal fixes web and mobile together. The web `<select>` only offers `male`/`female`, but a
hand-crafted POST with `gender=attack helicopter` was saved, finalised and exported (mlro-user log step 7).
`reporting/goaml.py:325` writes it as `F` (lead `checks_2026_11_11.py` RP1g). No change to the proposed diff.

## 2. L-143: no upper plausibility bound on report amount
`cases/reports.py:105-111` rejects non-numeric, negative, `inf` and `nan`, but accepts `1e30`
(mlro-user step "web: amount 1e30": saved, finalised, exported). Proposed, inside the same validation step:

```python
MAX_REPORT_AMOUNT = 1e12  # AED; above this is a typing error, not a transaction
if parsed_amount is not None and parsed_amount > MAX_REPORT_AMOUNT:
    return ReportResult(success=False, error=f"Amount {amount!r} is implausibly large; check the figure.")
```
Mirror in `api/mobile.py:~1733`. The cap value is a product decision for Nadhir (LOW severity).
