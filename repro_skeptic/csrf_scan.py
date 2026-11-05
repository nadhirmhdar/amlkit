"""Skeptic check: which state-changing routes have no CSRF validation in their body.
Scans app.py and every api/routers/*.py (the 2026-11 split moved the routes out of app.py;
the old single-file version of this script silently reported 0 routes afterwards).
Mobile (bearer) and billing webhook routes are excluded by design."""
import glob, os, re, sys
root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "amlkit/api")
files = [os.path.join(root, "app.py")] + sorted(glob.glob(os.path.join(root, "routers", "*.py")))
pat = re.compile(r'\n(?=@(?:app|router)\.(?:post|put|delete|patch)\()')
missing, total = [], 0
for f in files:
    src = open(f).read()
    for p in pat.split(src)[1:]:
        body = re.split(r'\n(?=@(?:app|router)\.)', p)[0]
        total += 1
        if "require_csrf" not in body and "csrf_valid" not in body:
            missing.append(f"{os.path.relpath(f, root)}: {p.splitlines()[0]}")
print("\n".join(missing)); print(f"{len(files)} files; {total} state-changing routes; {len(missing)} without a CSRF check in the body")
sys.exit(0 if missing and total > 20 else 1)
