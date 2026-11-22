"""Red-team 2026-11-17: cost and safety of the UBO diagram (cases.diagram.generate_ubo_diagram, Graphviz) at the new structure limits (depth 10, 200 rows per customer),
with hostile owner names (quotes, backslashes, HTML/DOT metacharacters, huge, RLO), and repeated page loads. LOCAL ONLY (needs fixtures/ from PR #412 make_seed)."""
import json, os, re, shutil, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
ids = json.loads((ROOT/"fixtures"/"seed_ids.json").read_text()); B = ids["B"]; CID = B["customer_id"]
db = Path(tempfile.mkdtemp())/"s.db"; os.environ["AMLKIT_DB"] = str(db); shutil.copy(ROOT/"fixtures"/"seed.db", db)
import logging; logging.disable(logging.CRITICAL)
from amlkit.cases import manager as M
from amlkit.cases.diagram import generate_ubo_diagram
from amlkit.db import connect, _reset_init_cache
_reset_init_cache(); c = connect(db)
HOSTILE = ['A" -> "B"; "evil', "x\\", "<script>alert(1)</script>", 'name"];digraph{', "N" * 2000, "‮exe", "a\nb", "\x00nul", "{rank=same}", "ا" * 300]
added = 0
for i, n in enumerate(HOSTILE):
    try: M.add_ubo(c, CID, org_id=B["org_id"], person_name=n, ownership_pct=None, control_type="senior_official" if i % 2 else "other"); added += 1
    except Exception as e: print(f" add_ubo refused {n[:20]!r}: {type(e).__name__}: {str(e)[:50]}")
print("hostile owners stored:", added)
parent = None
for d in range(10):
    try: parent = M.add_ubo(c, CID, org_id=B["org_id"], person_name=f"Chain {d}", ownership_pct=(30 if parent is None else 100), parent_ubo_id=parent)
    except Exception as e: print(f" chain stopped at {d}: {e}"); break
n = c.execute("select count(*) from ubo_links where customer_id=?", (CID,)).fetchone()[0]
while n < 200:
    try: M.add_ubo(c, CID, org_id=B["org_id"], person_name=f"Bulk {n}", ownership_pct=None, control_type="senior_official", parent_ubo_id=None); n += 1
    except Exception as e: print(f" row cap reached at {n}: {e}"); break
print("ubo rows now:", n)
t0 = time.time(); svg = generate_ubo_diagram(c, CID, B["org_id"]); dt = time.time() - t0
s = svg if isinstance(svg, str) else str(svg)
print(f"diagram render: {dt:.2f}s, {len(s)//1024} KB, starts with: {s[:60]!r}")
print("raw <script> in svg:", "<script" in s.lower(), "| onload/onerror attrs:", bool(re.search(r"\bon(load|error)\s*=", s, re.I)), "| external hrefs:", re.findall(r'(?:xlink:)?href="(https?://[^"]+)"', s)[:3])
t0 = time.time(); [generate_ubo_diagram(c, CID, B["org_id"]) for _ in range(5)]; print(f"5 more renders: {time.time()-t0:.1f}s")
