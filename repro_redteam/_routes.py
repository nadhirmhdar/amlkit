"""Flatten app.routes (handles Starlette/FastAPI _IncludedRouter wrappers used after the #456 router split). Returns [(method, path)]."""
def flat_routes(app):
    out = []
    def emit(r, path):
        for m in (getattr(r, "methods", None) or []): out.append((m, path))
    for r in app.routes:
        if type(r).__name__ == "_IncludedRouter":
            for ctx in r.effective_route_contexts():
                rt = getattr(ctx, "route", ctx); emit(rt, getattr(ctx, "path", None) or getattr(rt, "path", "?"))
        elif hasattr(r, "path"): emit(r, r.path)
    return out
