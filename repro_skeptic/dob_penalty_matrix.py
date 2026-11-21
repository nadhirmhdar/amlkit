"""CS-28 / DB1: an exact name with a one-digit birth-date typo can score below the alert threshold while a
completely different birth year alerts. Pure function, no DB. Exit 0 only when that inversion reproduces."""
import sys
from amlkit.match.scorer import score_entity, DEFAULT_THRESHOLD

LISTED = "1975-03-04"
cases = [
    ("same date", "1975-03-04"),
    ("day typo, same month (04->07)", "1975-03-07"),
    ("day and month swapped (03-04 -> 04-03)", "1975-04-03"),
    ("MONTH typo, same day (03->08)", "1975-08-04"),
    ("month and day both different", "1975-08-21"),
    ("YEAR different by one", "1976-03-04"),
    ("YEAR different by 20", "1995-03-04"),
    ("completely different date", "1992-11-02"),
]
res = {}
for label, dob in cases:
    r = score_entity("Ahmed Hassan Ali", ["Ahmed Hassan Ali"], query_birth_date=dob, cand_birth_date=LISTED)
    res[label] = r.score
    print(f"{label:46s} {dob}  score {r.score:.2f}  {'ALERT' if r.score >= DEFAULT_THRESHOLD else 'silent'}")
inverted = res["MONTH typo, same day (03->08)"] < DEFAULT_THRESHOLD <= res["YEAR different by 20"]
sys.exit(0 if inverted else 1)
