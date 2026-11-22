"""Red-team 2026-11-20: PR #465 collapse_pep_duplicates -- can a sanctioned/other-person hit be absorbed into a PEP hit, are distinct people merged, is also_listed escaped? LOCAL ONLY; pure function + jinja render."""
import sys, html
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
from amlkit.match import engine
H = engine.Hit if hasattr(engine, "Hit") else None
import inspect; print("Hit fields:", [f for f in inspect.signature(H).parameters] if H else "n/a")
def mk(eid, cap, ds, pep=True, san=False, score=0.95):
    topics = (["role.pep"] if pep else []) + (["sanction"] if san else [])
    return H(entity_id=eid, dataset=ds, caption=cap, schema_type="Person", score=score, matched_name=cap, topics=topics, detail={})
def run(label, hits, c):
    out = engine.collapse_pep_duplicates(hits, c); print(f" {label:55s} in={len(hits)} out={len(out)} also={[a['entity_id'] for h in out for a in h.detail.get('also_listed', [])]}")
    return out
run("same name, both PEP, no countries (distinct people?)", [mk("a", "John Smith", "cia"), mk("b", "John Smith", "wikidata")], {})
run("same name, different countries (should not merge)", [mk("a", "John Smith", "cia"), mk("b", "John Smith", "wikidata")], {"a": ["us"], "b": ["gb"]})
run("same name, one country known, other unknown", [mk("a", "John Smith", "cia"), mk("b", "John Smith", "wikidata")], {"a": ["us"], "b": []})
run("PEP + sanctioned same name (sanction must stay)", [mk("a", "John Smith", "cia"), mk("b", "John Smith", "ofac", pep=True, san=True)], {})
run("sanction first then PEP", [mk("b", "John Smith", "ofac", pep=True, san=True), mk("a", "John Smith", "cia")], {})
run("token order swap 'Smith John'", [mk("a", "John Smith", "cia"), mk("b", "Smith John", "wikidata")], {})
run("Arabic variants Mohamed/Muhammad Al Nahyan", [mk("a", "Mohamed bin Zayed Al Nahyan", "cia"), mk("b", "Muhammad bin Zayed Al Nahyan", "wikidata")], {})
run("father/son 'X bin Y' vs 'X bin Z' (differ in a token)", [mk("a", "Ahmed bin Khalid Al Said", "cia"), mk("b", "Ahmed bin Saeed Al Said", "wikidata")], {})
run("generation suffix 'John Smith Jr' vs 'John Smith'", [mk("a", "John Smith", "cia"), mk("b", "John Smith Jr", "wikidata")], {})
run("empty captions", [mk("a", "", "cia"), mk("b", "", "wikidata")], {})
big = [mk(f"e{i}", "John Smith", "wikidata") for i in range(5000)]
import time; t = time.time(); run("5000 identical PEP hits (perf)", big, {}); print(f"   elapsed {time.time()-t:.2f}s")
h = run("markup caption", [mk("a", "John Smith", "cia"), mk("b", "<img src=x onerror=alert(1)>", "wikidata")], {})
for t in ("_alert_panel.html", "screen.html"):
    src = (ROOT/"amlkit/web/templates"/t).read_text(); i = src.find("also_listed"); print(f" {t}: also_listed autoescape-safe? context:", repr(src[max(0,i-60):i+260]))
