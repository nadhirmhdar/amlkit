# HELD: POST /admin/org-profile has no CSRF check
Status: HELD (needs a change to route logic). Evidence: reports/daily/2026-10-04/evidence/probe_csrf_session.txt (section 2).

`amlkit/api/app.py:3245-3251` calls `require_session` and `require_role` but never `require_csrf`. Every other
state-changing POST swept (48 routes, empty and bad token) rejected the request; this one returned 303 and wrote
`organizations.org_address / reporting_person_* / goaml_entity_reference`. Those fields feed goAML STR exports.
Mitigation today: session cookie is SameSite=strict, so a cross-site POST normally carries no session. deps.py's own
docstring says SameSite alone is not sufficient.

Proposed diff:
```diff
     try:
         session = require_session(request, db)
+        require_csrf(request, csrf_token)
         require_role(session, "mlro")
     except PermissionError as exc:
         if current_session(request, db) is None:
             return RedirectResponse("/login", status_code=303)
-        return back("/admin", err=str(exc))
+        from fastapi.responses import JSONResponse
+        return JSONResponse({"error": str(exc)}, status_code=403)
```
Confirm `templates/admin` posts `csrf_token` for this form before merging. Test: POST with a valid MLRO session and no token must not change `organizations`.
