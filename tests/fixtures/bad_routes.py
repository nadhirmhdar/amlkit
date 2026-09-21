"""Test fixture: Route handlers with tenant-isolation violations.

These are intentional violations to test the security scanner.
"""

from fastapi import FastAPI, Form, Request

app = FastAPI()


@app.post("/customers")
def create_customer_no_csrf(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
):
    """VIOLATION: POST route without CSRF validation."""
    # Missing: require_csrf(request, csrf_token)
    return {"status": "created"}


@app.post("/alerts/{alert_id}/disposition")
def dispose_alert_no_csrf(
    request: Request,
    alert_id: int,
    action: str = Form(...),
):
    """VIOLATION: POST route without CSRF validation."""
    # Missing: require_csrf(request, csrf_token)
    return {"status": "disposed"}


@app.get("/reports")
def list_reports_no_session(request: Request, db):
    """VIOLATION: Accesses tenant data without session check."""
    # Missing: session = require_session(request, db)
    # Directly queries tenant data
    reports = db.execute("SELECT * FROM reports").fetchall()
    return {"reports": reports}


# This route is CORRECT - it should NOT be flagged
@app.get("/health")
def health_check():
    """Public health check - no session required."""
    return {"status": "ok"}
