"""N3c: the Urdu heh (U+06C1) is not folded to the Arabic heh (U+0647), so a name typed with it loses letters.
Pure function, no DB. Exit 0 only when the defect reproduces (canonical forms differ)."""
import sys
from amlkit.names.arabic import canonical_key

base = "عبدالله"
doachashmee = base.replace("ه", "ھ")   # already folded (names/arabic.py:60)
urdu_heh = base.replace("ه", "ہ")      # not folded
for label, s in (("base", base), ("heh doachashmee U+06BE", doachashmee), ("urdu heh U+06C1", urdu_heh)):
    print(f"{label:26s} -> {canonical_key(s)!r}")
sys.exit(0 if canonical_key(urdu_heh) != canonical_key(base) else 1)
