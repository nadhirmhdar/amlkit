"""Lead checks 2026-11-19 (master cdf3801, after #463/#464).

Run from repo root with PYTHONPATH=. (or point PYTHONPATH at another checkout to
compare). Exit 0 while ANY residual item below reproduces on the code under test;
exit 1 when all are fixed. CS-27 itself is reported (old vs new) but not counted,
because it is FIXED on cdf3801.

Items:
  CS27  exact name, same country, ISO code vs list name -> score (info only)
  CT1   bare ambiguous list country resolves to one side -> false mismatch
        (Korea->KR, Congo->CG, Virgin Islands->VI), exact name drops < 0.85
  CT2   non-string country in a list record raises instead of skipping penalty
  L158  DOB +1 day still 0.75 with country now agreeing (exact name)
"""
import sys

from amlkit.match.scorer import score_entity

THRESH = 0.85
N = "Amit Kumar Shah"


def sc(qc, cc, **kw):
    r = score_entity(N, [N], query_countries=qc, cand_countries=cc, **kw)
    return round(r.score, 2)


hits = 0
print("CS27  IN/India=%s  IR/'Iran, Islamic Republic of'=%s  RU/'Russian Federation'=%s  AE/'United Arab Emirates'=%s  IN/Pakistan=%s (info; FIXED when the first four are 1.0)"
      % (sc(["IN"], ["India"]), sc(["IR"], ["Iran, Islamic Republic of"]),
         sc(["RU"], ["Russian Federation"]), sc(["AE"], ["United Arab Emirates"]),
         sc(["IN"], ["Pakistan"])))

ct1 = {
    "KP vs 'Korea'": sc(["KP"], ["Korea"]),
    "CD vs 'Congo'": sc(["CD"], ["Congo"]),
    "VG vs 'Virgin Islands'": sc(["VG"], ["Virgin Islands"]),
}
print("CT1  ", "  ".join(f"{k}={v}" for k, v in ct1.items()))
ct1_rep = any(v < THRESH for v in ct1.values())
print("CT1   reproduces=%s" % ct1_rep)
hits += ct1_rep

try:
    sc(["IN"], [5])
    ct2_rep = False
    print("CT2   int country in list record: no exception")
except Exception as e:  # noqa: BLE001
    ct2_rep = True
    print("CT2   int country in list record raises %s: %s" % (type(e).__name__, e))
print("CT2   reproduces=%s" % ct2_rep)
hits += ct2_rep

d1 = sc(["IN"], ["India"], query_birth_date="1975-03-13", cand_birth_date="1975-03-12")
d6 = sc(["IN"], ["India"], query_birth_date="1981-03-12", cand_birth_date="1975-03-12")
l158 = d1 < THRESH <= d6
print("L158  same country (IN/India): DOB +1 day=%s, DOB +6 years=%s, threshold=%s" % (d1, d6, THRESH))
print("L158  reproduces=%s" % l158)
hits += l158

print("%d/3 reproduce" % hits)
sys.exit(0 if hits else 1)
