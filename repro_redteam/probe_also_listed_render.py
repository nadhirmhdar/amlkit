"""Red-team 2026-11-27: render the real `also_listed` template lines from #465 with hostile dataset strings. Does Jinja autoescape apply? Run with AMLKIT_SRC=<checkout of origin/master>. LOCAL ONLY."""
import os, sys, logging
from pathlib import Path
ROOT = Path(os.environ.get("AMLKIT_SRC") or Path(__file__).resolve().parent.parent); sys.path.insert(0, str(ROOT)); logging.disable(logging.CRITICAL)
from amlkit.api import helpers
env = helpers.templates.env
print("autoescape for .html templates:", env.autoescape("x.html") if callable(env.autoescape) else env.autoescape)
XSS = '<img src=x onerror=alert(1)>"\'&'
also = [{"dataset": XSS, "entity_id": 2, "caption": XSS, "score": 0.9}, {"dataset": "wikidata_ministers"}, {"dataset": XSS}]
for name, expr_src in (("_alert_panel.html", "{{ a.detail.also_listed|map(attribute='dataset')|unique|join(', ') }}"),
                       ("screen.html", "{{ h.detail.also_listed|map(attribute='dataset')|unique|join(', ') }}")):
    # the real line from the template file, compiled through the app's own env as a named .html template (so the env's autoescape rule applies)
    src = (ROOT/"amlkit/web/templates"/name).read_text()
    assert expr_src in src, f"{name}: expression not found verbatim"
    t = env.from_string("{% autoescape true %}" + expr_src + "{% endautoescape %}")
    out_forced = t.render(a={"detail": {"also_listed": also}}, h={"detail": {"also_listed": also}})
    print(f"{name}: forced-autoescape output = {out_forced!r}; raw '<img' present: {'<img' in out_forced}")
    print(f"   file wraps the expression in |safe or autoescape off? safe={'|safe' in src.split(expr_src)[1][:40]} noescape_block={'{% autoescape false' in src}")
# real file render through the loader (autoescape rule of the env applies to files named *.html)
t = env.get_template("_alert_panel.html")
try:
    html = t.render(a={"detail": {"also_listed": also}, "matched_name": "x", "score": 0.9, "dataset": "d", "caption": "c", "topics": [], "programs": [], "id": 1, "status": "open", "entity_id": 1, "customer_id": None, "created_at": "2026-01-01", "reason": ""}, alert={}, request=None, csrf_token="t")
    print("_alert_panel.html real render: raw '<img' in output:", "<img src=x" in html, "| escaped form present:", "&lt;img src=x" in html)
except Exception as e:
    print("_alert_panel.html real render needs more context:", type(e).__name__, str(e)[:100])
