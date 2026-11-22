"""Red-team 2026-11-15: Arabic-script spellings of the patronymic/definite-article particles vs the Latin listing. fuzz_names.py showed 'ابن' -> ['abn'] while 'بن' and 'ibn' vanish.
Does a query that differs only by that particle still reach the 0.85 alert threshold against the Latin listed name? LOCAL ONLY."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
from amlkit.names.arabic import canonical_tokens
from amlkit.match.scorer import name_score, DEFAULT_THRESHOLD
LISTED = ["Mohammed bin Salman Al Saud", "Mohammed ibn Salman Al Saud", "Muhammad Ibn Salman Al-Saud", "Abdullah bin Zayed Al Nahyan"]
QUERIES = {"محمد بن سلمان آل سعود": "bin (بن)", "محمد ابن سلمان آل سعود": "ibn (ابن)", "محمد إبن سلمان آل سعود": "ibn (إبن)", "محمد بنْ سلمان آل سعود": "bin + sukun", "محمد بِن سلمان آل سعود": "bin + kasra",
           "محمد  بن  سلمان  ال سعود": "al spaced", "محمد بن سلمان السعود": "al- fused", "محمد بن سلمان سعود": "no Al", "محمد سلمان آل سعود": "no particle", "محمد ولد سلمان آل سعود": "walad",
           "محمد بن سلمان بن عبد العزيز آل سعود": "full chain", "Mohammad bin Salman": "latin short", "Muhammed Bin Selman Al Saud": "latin variant"}
print(f"threshold {DEFAULT_THRESHOLD}")
worst = {}
for q, lab in QUERIES.items():
    toks = canonical_tokens(q); best = max((name_score(q, l)[0], l) for l in LISTED[:3])
    flag = "HIT " if best[0] >= DEFAULT_THRESHOLD else "MISS"
    print(f" {flag} {best[0]:.2f}  {lab:14s} {q!r:46s} tokens={toks}")
