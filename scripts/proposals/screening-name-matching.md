# HELD: screening misses (names, scoring, UBO rescreen)
Status: HELD (changes names/arabic.py, match/scorer.py, match/engine.py). Evidence: probe_e2e.txt, probe_e2e2.txt, probe_ubo.txt, probe_names.txt.

| Id | Cause | Proposed fix |
|----|-------|--------------|
| S1 | `_ARABIC_RANGE` (arabic.py:59) lacks U+FB50-FDFF and U+FE70-FEFF, so PDF-copied presentation forms skip transliteration; tokens end empty; `screen()` returns clear | Add those ranges (and U+0750-077F already present); NFKC-normalise every input first; in `screen()` and the onboarding/UBO routes, refuse or flag "no screenable tokens" rather than "clear" |
| S2 | `_PUNCT` (arabic.py:393) turns Cf characters (ZWSP/ZWJ/WJ/BOM/soft hyphen) into spaces and splits tokens | Delete category Cf and Mn (after NFKD) before `_PUNCT` |
| S3 | `name_score` weights the LAST query token 1.3x and counts unmatched query tokens against recall, so one extra token ("... HASSAN", "... JR") drops an exact listing to ~0.70 | Score the listed name against the best contiguous/subset alignment of the query, or add a superset-query path that does not penalise extra query tokens when every listed token matched |
| S4 | Country, gender and DOB mismatches (-0.20/-0.20/-0.25) applied to an exact canonical match put it under 0.85 | Do not apply attribute penalties when `exact_canonical` is true, or floor an exact match at the threshold and surface the mismatch in the alert detail |
| S5 | Unmapped Arabic-block letters (ے ہ ڕ ں ...) are dropped by `_ARABIC_TRANSLIT.get(ch, "")`; Latin homoglyphs on consonants change the skeleton | Fold via NFKD plus a small confusables/Urdu map; log unknown characters |
| S6 | `rescreen_all` (engine.py:420) only re-screens `is_ubo=1 AND is_nominee=0` | Re-screen every `ubo_links` row (owners under 25%, nominees, directors, controllers) |
Tests to add with each fix: the strings in probe_e2e.py / probe_e2e2.py as a parametrised regression suite; S4 must keep the existing false-positive suite in tests/test_matching.py green (re-run it).
