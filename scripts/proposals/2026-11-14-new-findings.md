# HELD proposal 2026-11-14 (TD1, TD2) -- not applied, no application code edited
## TD1 `direction` is never validated, and structuring groups by the exact string (amlkit/cases/manager.py record_transaction ~L1040; amlkit/screening/kyt.py ~L226 `AND direction=?`)
Three AED 54,999 cash transactions raise `structuring` with direction `in`,`in`,`in` but NONE when the directions are `in`,`IN`,` in` (or `in`,`in.`,`in2`, or any other mix). Both the web form and the mobile API accept any string (`sideways`, empty, 500 characters).
Fix: in `record_transaction` normalise (`strip().lower()`) and reject anything other than `in` / `out` with a ValueError (web flash / mobile 400); add a one-off migration that normalises stored values and flags rows that cannot be mapped; make the KYT query compare the normalised column.
## TD2 free-text size caps (note body 1 MB, UBO person name 5,000 chars, NUL/bidi characters stored) on both surfaces
Cap notes (e.g. 5,000), names (e.g. 300) and strip control/bidi characters in `add_case_note` and `add_ubo`, as already done for operator names and the screening query.
