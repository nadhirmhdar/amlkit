# FATF live parser silently drops unmapped grey-list names (HELD)

Status: HELD for Nadhir's review. Lead 2026-10-05, finding L-20. Raised by compliance-specialist CS-6. Skeptic: CONFIRMED mechanism, High downgraded to Medium. Related: CS-7 / lead L-5 (fallback drift; a committed snapshot is still the preferred fix).

## Defect (master `448a19b`)
`ingest/fatf.py:207-235` `_resolve_country` returns `None` for any name missing from `_COUNTRY_TO_ISO`. `:324-333` then skips that name. The load still stamps `last_refresh` (`loader.py:157-160`), so a partial list looks fresh and complete. The grey-list tier forces EDD (`risk/model.py:185-192`).

Lead run on `448a19b` (`repro_lead/checks_2026_10_05.py`):
```
unmapped by fatf._resolve_country: ['Kuwait', 'Bolivia', 'Nepal', 'Papua New Guinea', 'British Virgin Islands', 'Virgin Islands (UK)']
```
Haiti and Laos resolve. Whether FATF currently lists these countries, and how its page spells them, is UNVERIFIED: the FATF site returns a Cloudflare challenge to cloud egress.

## Proposed diff (not applied)
1. Add the mappings to `_COUNTRY_TO_ISO`: `"kuwait": ("KW", "Kuwait")`, `"bolivia": ("BO", "Bolivia")`, `"plurinational state of bolivia": ("BO", "Bolivia")`, `"nepal": ("NP", "Nepal")`, `"papua new guinea": ("PG", "Papua New Guinea")`, `"british virgin islands": ("VG", "British Virgin Islands")`, `"virgin islands (uk)": ("VG", "British Virgin Islands")`. Match the dict's existing key style; the keys may not be lower-cased.
2. In `_parse_html`, collect the unmapped names. If any exist, raise `AdapterError(f"unmapped FATF jurisdictions: {names}")` so the dataset row shows a failure rather than freshness. The caller then falls back to the fallback data, which is itself stale (L-5). That is why the snapshot fix should land with this change.

Test to add with the fix: a fixture page listing "British Virgin Islands" maps to `VG`, and a fixture listing "Atlantis" makes the load fail.
