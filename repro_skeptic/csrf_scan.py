"""Skeptic check: which state-changing routes in app.py have no CSRF validation in their body."""
import re, os, sys
src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "amlkit/api/app.py")).read()
parts = re.split(r'\n(?=@app\.(?:post|put|delete|patch)\()', src)
missing = []
for p in parts[1:]:
    body = re.split(r'\n(?=@app\.)', p)[0]
    if "require_csrf" not in body and "csrf_valid" not in body:
        missing.append(p.split("\n")[0])
print("\n".join(missing)); print(len(parts) - 1, "state-changing routes;", len(missing), "without CSRF check")
sys.exit(0 if "/admin/org-profile" in "".join(missing) else 1)
