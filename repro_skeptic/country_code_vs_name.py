"""CS-27 / F2b: an exact-name match whose country is an ISO code on one side and an English name on the other.
Before #464 the raw strings were compared, so ("IN" vs "India") counted as a mismatch (-0.20) and an exact name fell
below the 0.85 alert threshold. Pure function, no DB. Exit 0 only when the defect reproduces (score < 0.85)."""
import sys
from amlkit.match.scorer import score_entity

cases = [("IN", "India"), ("IN", "in"), ("AE", "United Arab Emirates"), ("KP", "Korea, North")]
worst = 1.0
for q, c in cases:
    r = score_entity("Amit Shah", ["Amit Shah"], query_countries=[q], cand_countries=[c])
    print(f"customer {q!r:6} vs list {c!r:24} -> score {r.score:.2f}")
    if (q, c) == ("IN", "India"):
        worst = r.score
sys.exit(0 if worst < 0.85 else 1)
