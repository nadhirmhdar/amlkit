"""Red-team 2026-11-19: PR #464 (countries.to_alpha2 + scorer._countries_contradict). Is the new comparison crash-free for odd input types, does it still penalise provable
mismatches, and can the aliases be used to dodge or force the -0.20 country penalty? Scores via score_entity with an exact-name match so only the country term moves. LOCAL ONLY."""
import itertools, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
from amlkit.countries import to_alpha2
from amlkit.match.scorer import score_entity, _countries_contradict, DEFAULT_THRESHOLD, P_COUNTRY_MISMATCH
def sc(q, c): return round(score_entity("Ravi Kumar Sharma", ["Ravi Kumar Sharma"], query_country=q, cand_countries=c).score, 2)
print("== 1. crash resistance of _countries_contradict / to_alpha2 ==")
odd = [None, "", " ", 0, 12, 1.5, True, b"IN", ["IN"], ("IN",), {"IN"}, {}, object(), "İndia", "ＩＮ", "İN", "‮IN", "IN\x00", "x" * 100_000, "\ud800", "India;Pakistan", "India, Pakistan", "IN,PK"]
bad = []
for q, c in itertools.product(odd, odd):
    try: _countries_contradict([q] if not isinstance(q, list) else q, [c] if not isinstance(c, list) else c)
    except Exception as e: bad.append((repr(q)[:20], repr(c)[:20], type(e).__name__))
print(f" {len(odd)**2} combinations; exceptions: {len(bad)}", bad[:6])
print("== 2. behaviour (exact name match; threshold %.2f, penalty %.2f) ==" % (DEFAULT_THRESHOLD, P_COUNTRY_MISMATCH))
for q, c, label in [("IN", ["India"], "customer IN vs list 'India' (the fixed case)"), ("IN", ["Pakistan"], "IN vs Pakistan (true mismatch)"), ("AE", ["United Arab Emirates"], "AE vs full name"), ("RU", ["Russian Federation"], "RU vs OFAC name"),
                    ("KP", ["Korea, North"], "KP vs 'Korea, North'"), ("KP", ["Korea"], "KP vs bare 'Korea' (ambiguous alias -> KR)"), ("KR", ["Korea"], "KR vs bare 'Korea'"), ("IN", ["Hindustan"], "unresolvable list value"),
                    ("IN", ["India", "Pakistan"], "list with both"), ("IN", ["Pakistan, India"], "joined string in one value"), ("Indai", ["India"], "customer typo"), ("IN", ["Bharat"], "native name"), ("GE", ["Georgia"], "GE vs Georgia"),
                    ("US", ["Georgia"], "US vs Georgia (state vs country)"), ("ZZ", ["India"], "invalid code ZZ"), ("", ["India"], "empty customer country"), ("IR", ["Iran"], "IR vs Iran"), ("SY", ["Syrian Arab Republic"], "SY"), ("MM", ["Burma"], "MM vs Burma")]:
    s = sc(q, c); print(f" {'ALERT' if s >= DEFAULT_THRESHOLD else 'below'} {s:.2f}  {label}")
print("== 3. table sanity: every alias resolves uniquely; no alias collides across codes ==")
from amlkit import countries as C
seen = {}; dup = []
for code, names in C._TABLE.items():
    for n in names.split("|"):
        k = C._norm(n)
        if k in seen and seen[k] != code: dup.append((n, seen[k], code))
        seen.setdefault(k, code)
print(" collisions across codes:", dup or "none"); print(" codes in table:", len(C._TABLE), "| aliases:", len(seen))
