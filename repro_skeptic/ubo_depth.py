"""U4: _identified_ownership recurses once per ownership level, so a deep chain raises RecursionError.
Pure function, synthetic rows, no DB. Exit 0 only when the defect reproduces."""
import sys
from amlkit.cases.manager import _identified_ownership

def chain(n):
    return [dict(id=i, ownership_pct=100.0, parent_ubo_id=(i - 1 if i > 1 else None),
                 is_nominee=0, is_ubo=1, canonical_key=f"k{i}") for i in range(1, n + 1)]

for n in (500, 900, 1100, 5000):
    try:
        print(n, "->", _identified_ownership(chain(n)))
    except RecursionError:
        print(n, "-> RecursionError"); last = n
sys.exit(0 if "last" in globals() else 1)
