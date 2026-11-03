# HELD proposal: UBO1b, self-owner guard misses legal-suffix variants

Status: **HELD for Nadhir** (edits `amlkit/cases/manager.py`; routine rule 3 forbids the lead from changing business logic).
Raised by: mlro-user (UBO1b, 2026-11-03), broadened by skeptic. Lead verdict: CONFIRMED on `938050f`, severity LOW.

## Evidence (`repro_lead/checks_2026_11_03.py`, branch `routine/2026-11-03-lead`)

```
UBO1b owner 'Gulf Holdings LLC'      canonical_key='glf hldngs lc'        -> refused (A customer cannot be recorded as its own bene...)
UBO1b owner 'GULF  holdings llc'     canonical_key='glf hldngs lc'        -> refused (A customer cannot be recorded as its own bene...)
UBO1b owner 'GULF HOLDINGS L.L.C.'   canonical_key='c glf hldngs l l'     -> accepted
UBO1b owner 'Gulf Holdings'          canonical_key='glf hldngs'           -> accepted
UBO1b owner 'Gulf Holdings FZE'      canonical_key='fz glf hldngs'        -> accepted
```

`_check_ubo_structure` (`amlkit/cases/manager.py:532-562`) compares the
casefolded, whitespace-collapsed name and `canonical_key` for exact equality.
`canonical_key` keeps legal-form tokens (and splits dotted ones into single
letters), so any suffix variation passes.

## Impact

No crash and no cycle: `add_ubo` only appends leaves, and #455's depth/row caps
hold. The harm is a wrong disclosed ownership percentage on one customer, which
an examiner would query. LOW.

## Design question (why this is not a straight refusal)

"Gulf Holdings Ltd" (BVI) owning "Gulf Holdings LLC" (UAE) is a common and
legitimate structure. Refusing every owner whose name equals the customer's
after suffix stripping would block real data. Recommended: **refuse** only
when the suffix-stripped names match *and* the owner's suffix is the same legal
form (or the owner has no suffix and no other distinguishing token); otherwise
**accept with a warning flash** ("this owner has the same base name as the
customer; confirm it is a separate legal entity"). Nadhir to choose:
(a) warn only, (b) refuse same-form / warn different-form (recommended),
(c) refuse all suffix-stripped matches.

## Proposed diff (option b, sketch)

```diff
--- a/amlkit/cases/manager.py
+++ b/amlkit/cases/manager.py
@@
+_LEGAL_FORMS = {
+    "llc": "llc", "l.l.c": "llc", "l l c": "llc", "fze": "fze", "fzco": "fzco",
+    "fz-llc": "fzllc", "fzllc": "fzllc", "ltd": "ltd", "limited": "ltd",
+    "pjsc": "pjsc", "psc": "psc", "inc": "inc", "est": "est", "establishment": "est",
+    "ذ.م.م": "llc", "ش.ذ.م.م": "llc", "م.م.ح": "fze",
+}
+
+def _split_legal_form(name: str) -> tuple[str, str | None]:
+    """('gulf holdings', 'llc') for 'GULF HOLDINGS L.L.C.'; form None if absent."""
+    s = " ".join(name.casefold().replace(",", " ").split()).rstrip(".")
+    for raw, form in sorted(_LEGAL_FORMS.items(), key=lambda kv: -len(kv[0])):
+        for variant in (raw, raw.replace(".", "")):
+            if s.endswith(" " + variant):
+                return s[: -len(variant) - 1].strip(), form
+    return s, None
@@ def _check_ubo_structure(...):
+    cust_base, cust_form = _split_legal_form(cust["full_name"] or "")
+    own_base, own_form = _split_legal_form(person_name)
+    if cust_base and own_base == cust_base and (own_form is None or own_form == cust_form):
+        raise ValueError("A customer cannot be recorded as its own beneficial owner. ...")
+    # different legal form, same base name: caller flashes a warning
+    # (return a flag, or raise a dedicated UboSameBaseNameWarning the routes catch)
```

`canonical_key` should be applied to the base names as well, so the Arabic
form keeps working.

## Tests to add with the fix

- `GULF HOLDINGS L.L.C.`, `Gulf Holdings`, `gulf holdings llc.` as owner of `Gulf Holdings LLC` -> refused.
- `Gulf Holdings Ltd` as owner of `Gulf Holdings LLC` -> accepted, warning surfaced (web flash, mobile 200 with `warning`).
- Arabic `شركة الخليج القابضة ذ.م.م` vs `شركة الخليج القابضة` -> refused.
- Existing #455 tests unchanged.

`repro_lead/checks_2026_11_03.py` exits 1 for the UBO1b line once this lands.
