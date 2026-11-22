# 2026-11-20 HELD proposals (not applied; no application code edited)
## PC1: collapse_pep_duplicates merges same-name PEPs without a positive identity signal
Merge only when at least one corroborating signal agrees (shared country, or equal birth year/date) -- not merely "no contradiction". In `engine.collapse_pep_duplicates`, replace `not _countries_contradict(a, b)` with `_countries_share(a, b) or _same_dob(k, h)`, and keep unmerged hits visible. Cost: more duplicate alerts for people with sparse data (the safe direction).
Also reword the UI line "Same person also listed on" to "Probably the same person" and list each also_listed caption + entity id, not only the dataset name.
## DB1: DOB tolerance
Treat a 01-01 day/month in either date as a placeholder (year-only match) so it takes the near-miss penalty, not -0.25. Optional: allow a single-digit month/day typo (same year, day equal, month differs by one character) the -0.10 near-miss.
