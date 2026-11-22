"""Red-team 2026-11-20: PR #466 (DOB near-miss) -- which date-of-birth variants of an EXACT name match still alert (threshold 0.85)? Listed DOB is 1970-03-12. LOCAL ONLY; pure scoring."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
from amlkit.match.scorer import score_entity, DEFAULT_THRESHOLD
LISTED = "1970-03-12"
CASES = [("identical", "1970-03-12"), ("day typo, same month (12->21)", "1970-03-21"), ("day off by one", "1970-03-13"), ("dd/mm swap (03-12 -> 12-03)", "1970-12-03"), ("month typo (03->08), same day", "1970-08-12"),
         ("month+day both different", "1970-07-30"), ("year off by one", "1971-03-12"), ("year digit transposition (1970->1907)", "1907-03-12"), ("different year, same month/day", "1980-03-12"), ("completely different", "1985-11-02"),
         ("year only (no month/day)", "1970"), ("year-month only", "1970-03"), ("Jan 1 placeholder", "1970-01-01"), ("empty", ""), ("invalid month 13", "1970-13-12"), ("dd/mm/yyyy text", "12/03/1970"), ("garbage", "not-a-date")]
print(f"threshold {DEFAULT_THRESHOLD}; listed DOB {LISTED}; exact name match")
for label, dob in CASES:
    r = score_entity("Ravi Kumar Sharma", ["Ravi Kumar Sharma"], query_birth_date=dob or None, cand_birth_date=LISTED)
    adj = r.features.get("adjustments", {})
    print(f" {'ALERT ' if r.score >= DEFAULT_THRESHOLD else 'silent'} {r.score:.2f}  {label:40s} {dob!r:14s} {adj}")
