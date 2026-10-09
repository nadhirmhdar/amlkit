"""Exploratory: list SQL statements touching org-scoped tables with no org_id."""
import ast, re, sqlite3, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
c = sqlite3.connect(ROOT / "fixtures" / "seed.db")
tenant = {t for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'")
          if "org_id" in [r[1] for r in c.execute(f"PRAGMA table_info({t})")]}
tenant -= {"sessions", "audit_log", "auth_log"}
def text(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str): return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        l, r = text(node.left), text(node.right)
        return (l or "") + (r or "") if (l or r) else None
    return None
out = []
for f in sorted((ROOT / "amlkit").rglob("*.py")):
    tree = ast.parse(f.read_text(encoding="utf-8-sig"))
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and getattr(n.func, "attr", "") in ("execute", "executemany", "executescript") and n.args:
            s = text(n.args[0])
            if not s: continue
            low = " ".join(s.split())
            if not re.match(r"(?i)\s*(select|update|delete|with)", low): continue
            tabs = {t for t in tenant if re.search(rf"(?i)\b(from|join|update)\s+{t}\b", low)}
            if tabs and "org_id" not in low:
                out.append((str(f.relative_to(ROOT)), n.lineno, sorted(tabs), low[:170]))
for o in out: print(f"{o[0]}:{o[1]} {o[2]}\n    {o[3]}")
print(len(out))
