"""Admin console: org profile, operators, thresholds, compliance health and platform applications.

Moved verbatim from api/app.py (WP-18, issue #73): no route, dependency or limit changed.
"""

from __future__ import annotations

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ... import auth, queries
from ... import mail as _mail
from ...billing.limits import BillingLimitError, check_limit
from ...cases.review import (
    single_operator_mode,
)
from ...db import set_org_alert_threshold, set_org_single_operator_mode, utcnow
from ...match.engine import DEFAULT_THRESHOLD
from ..deps import (
    SESSION_COOKIE,
    current_session,
    require_csrf,
    require_role,
    require_session,
)



from fastapi import APIRouter

from ..helpers import (
    DB,
    _is_applications_viewer,
    back,
    render,
)

router = APIRouter()


# ------------------------------------------------- applications (admin viewer)
def _applications_viewer(request: Request, db: DB):
    """The platform admin who receives quotation requests, or None.

    Applications are not tenant data (no org_id), so this is not an org-role
    check: the session must be a super-admin whose own email is one of the
    quote recipients (AMLKIT_QUOTE_TO, default info@grovisor.ae). Anyone else
    gets a plain 404 so the page's existence is not revealed.
    """
    try:
        session = require_session(request, db)
    except PermissionError:
        return None
    if _is_applications_viewer(session):
        return session
    return None

def _not_found(request: Request, db: DB):
    return HTMLResponse("Not found", status_code=404)

@router.get("/admin/applications", response_class=HTMLResponse)
def applications_view(request: Request, db: DB, status: str = ""):
    from ...cases import applications as apps
    session = _applications_viewer(request, db)
    if session is None:
        return _not_found(request, db)
    rows = apps.list_applications(db, status=status or None)
    return render(request, "admin_applications.html", {
        "session": session, "applications": rows, "status": status if status in apps.STATUSES else "",
        "statuses": apps.STATUSES, "counts": apps.counts_by_status(db),
        "retention_days": apps.RETENTION_DAYS, "expired": apps.expired_count(db),
    }, db)

@router.post("/admin/applications/{application_id}/status")
def applications_set_status(
    request: Request, db: DB, application_id: int,
    status: Annotated[str, Form()], csrf_token: Annotated[str, Form()] = "",
):
    from ...cases import applications as apps
    session = _applications_viewer(request, db)
    if session is None:
        return _not_found(request, db)
    try:
        require_csrf(request, csrf_token)
        found = apps.set_status(db, application_id, status, actor=session.operator_name)
    except (PermissionError, ValueError) as exc:
        return back("/admin/applications", err=str(exc))
    if not found:
        return back("/admin/applications", err=f"Request #{application_id} not found.")
    return back("/admin/applications", msg=f"Request #{application_id} marked {status}.")

@router.post("/admin/applications/{application_id}/delete")
def applications_delete(
    request: Request, db: DB, application_id: int, csrf_token: Annotated[str, Form()] = "",
):
    from ...cases import applications as apps
    session = _applications_viewer(request, db)
    if session is None:
        return _not_found(request, db)
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back("/admin/applications", err=str(exc))
    if not apps.delete_application(db, application_id, actor=session.operator_name):
        return back("/admin/applications", err=f"Request #{application_id} not found.")
    return back("/admin/applications", msg=f"Request #{application_id} deleted.")

@router.post("/admin/applications/purge")
def applications_purge(request: Request, db: DB, csrf_token: Annotated[str, Form()] = ""):
    from ...cases import applications as apps
    session = _applications_viewer(request, db)
    if session is None:
        return _not_found(request, db)
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back("/admin/applications", err=str(exc))
    n = apps.purge_expired(db, actor=session.operator_name)
    return back("/admin/applications", msg=f"Deleted {n} expired request(s).")

# ---------------------------------------------------------------------- admin
@router.get("/admin", response_class=HTMLResponse)
def admin_view(request: Request, db: DB):
    try:
        session = require_session(request, db)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        # L-75: an MLRO still locked behind MFA goes straight to the challenge
        # (one hop) instead of "/" -> /login -> /mfa/verify.
        pending = auth.mfa_session_state(db, request.cookies.get(SESSION_COOKIE))
        if pending and pending["role"] == "mlro" and not pending["mfa_verified"]:
            return RedirectResponse(auth.mfa_challenge_path(db, pending["operator_id"]), status_code=303)
        return back("/", err=str(exc))
    org = db.execute("""
        SELECT name, slug, org_address, reporting_person_name,
               reporting_person_title, reporting_person_phone,
               goaml_entity_reference
        FROM organizations WHERE id=?
    """, (session.org_id,)).fetchone()
    if org is None:
        return back("/", err="Organization not found.")
    from ...ingest.loader import staleness_report

    # Check for EU FSF token configuration issues
    eu_warning = None
    import os
    from datetime import datetime, timezone, timedelta

    # Check if token is unset or using the demo default
    eu_token = os.environ.get("AMLKIT_EU_FSF_TOKEN", "").strip()
    demo_token = "dG9rZW4tMjAxNy0xMS0xMw"  # from ingest/eu.py

    if not eu_token or eu_token == demo_token:
        eu_warning = (
            "EU Consolidated Sanctions List is using the demo token. "
            "Register at https://webgate.ec.europa.eu/fsd/fsf and set AMLKIT_EU_FSF_TOKEN "
            "before production use — the demo token may be rate-limited or rotated without notice."
        )
    else:
        # Check if EU refresh has been failing for >3 days
        eu_ds = db.execute(
            "SELECT last_error, error_at FROM datasets WHERE key='eu_sanctions'"
        ).fetchone()
        if eu_ds and eu_ds["last_error"] and eu_ds["error_at"]:
            error_time = datetime.fromisoformat(eu_ds["error_at"])
            # Make timezone-aware if naive (database stores UTC timestamps)
            if error_time.tzinfo is None:
                error_time = error_time.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - error_time > timedelta(days=3):
                eu_warning = (
                    f"EU sanctions refresh has been failing for >3 days (since {error_time.strftime('%Y-%m-%d')}). "
                    f"Error: {eu_ds['last_error'][:200]}"
                )

    return render(request, "admin.html", {
        "session": session, "org": dict(org),
        "operators": queries.operators(db, session.org_id),
        "mail_configured": _mail.is_configured(),
        "threshold": queries.org_alert_threshold(db, session.org_id),
        "default_threshold": DEFAULT_THRESHOLD,
        "single_operator_setting": queries.org_single_operator_setting(db, session.org_id),
        "single_operator_effective": single_operator_mode(db, session.org_id),
        "sanctions": staleness_report(db),
        "eu_warning": eu_warning,
    })

@router.post("/admin/org-profile")
def admin_save_org_profile(
    request: Request, db: DB,
    org_address: Annotated[str, Form()] = "",
    reporting_person_name: Annotated[str, Form()] = "",
    reporting_person_title: Annotated[str, Form()] = "",
    reporting_person_phone: Annotated[str, Form()] = "",
    goaml_entity_reference: Annotated[str, Form()] = "",
    clear_goaml_entity_reference: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = ""
):
    """Save organization reporting entity profile for goAML exports (p46).

    The goAML entity reference is only erased when the operator explicitly
    ticks "clear"; a blank submit keeps the saved value (a stale or partial
    form must not silently blank the reference every STR is filed under).
    """
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        # Same convention as every other form route: redirect back with a flash
        # error. Nothing is written, so the profile is unchanged.
        return back("/admin", err=str(exc))
    try:
        require_role(session, "mlro")
    except PermissionError as exc:
        return back("/admin", err=str(exc))

    if clear_goaml_entity_reference:
        goaml_entity_reference = ""
    elif not goaml_entity_reference.strip():
        saved = db.execute(
            "SELECT goaml_entity_reference FROM organizations WHERE id = ?",
            (session.org_id,),
        ).fetchone()
        goaml_entity_reference = (saved["goaml_entity_reference"] or "") if saved else ""

    # Update org profile
    db.execute("""
        UPDATE organizations
        SET org_address = ?,
            reporting_person_name = ?,
            reporting_person_title = ?,
            reporting_person_phone = ?,
            goaml_entity_reference = ?
        WHERE id = ?
    """, (
        org_address.strip() or None,
        reporting_person_name.strip() or None,
        reporting_person_title.strip() or None,
        reporting_person_phone.strip() or None,
        goaml_entity_reference.strip() or None,
        session.org_id
    ))

    # Audit the change
    from ...db import audit
    audit(db, session.operator_name, "org.profile_update", "organization", session.org_id, {
        "org_address": org_address.strip() or None,
        "reporting_person_name": reporting_person_name.strip() or None,
        "reporting_person_title": reporting_person_title.strip() or None,
        "reporting_person_phone": reporting_person_phone.strip() or None,
        "goaml_entity_reference": goaml_entity_reference.strip() or None,
    }, org_id=session.org_id)

    db.commit()
    return back("/admin", msg="Reporting entity profile updated.")

@router.get("/admin/compliance", response_class=HTMLResponse)
def compliance_health_view(request: Request, db: DB):
    try:
        session = require_session(request, db)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        return back("/", err=str(exc))
    from ...ingest.loader import staleness_report
    report = staleness_report(db)
    # Enrich with last_error / error_at from the datasets table
    error_info = {
        row["key"]: {"last_error": row["last_error"], "error_at": row["error_at"]}
        for row in db.execute("SELECT key, last_error, error_at FROM datasets").fetchall()
    }
    datasets = []
    for ds in report:
        ei = error_info.get(ds["key"], {})
        last_error = ei.get("last_error")
        error_at = ei.get("error_at")
        max_age = ds["max_age_hours"]
        # Determine status
        if last_error:
            status = "FAIL"
        elif ds["breach"]:
            status = "BREACH"
        elif ds["hours_since_refresh"] is not None and ds["hours_since_refresh"] > max_age:
            status = "STALE"
        else:
            status = "OK"
        datasets.append({
            **ds,
            "last_error": last_error,
            "error_at": error_at,
            "status": status,
        })
    return render(request, "compliance.html", {
        "session": session,
        "datasets": datasets,
    })

@router.post("/admin/threshold")
def admin_set_threshold(
    request: Request, db: DB,
    threshold: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": str(exc)}, status_code=403)

    raw = threshold.strip()
    if not raw:
        set_org_alert_threshold(db, session.org_id, None)
        return back("/admin", msg=f"Threshold reset to the engine default ({DEFAULT_THRESHOLD}).")
    try:
        value = float(raw)
    except ValueError:
        return back("/admin", err="Threshold must be a number.")
    if not (queries.MIN_ALERT_THRESHOLD <= value <= 1.0):  # also rejects NaN
        return back("/admin", err=f"Threshold must be between {queries.MIN_ALERT_THRESHOLD} and 1.0.")
    set_org_alert_threshold(db, session.org_id, value)
    from ...db import audit
    audit(db, session.operator_name, "org.threshold_set", "organization", session.org_id,
          {"threshold": value}, org_id=session.org_id)
    db.commit()
    return back("/admin", msg=f"Alert threshold set to {value}.")

@router.post("/admin/single-operator")
def admin_set_single_operator(
    request: Request, db: DB,
    mode: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
):
    """Per-org single-operator mode (Issue #258). 'on' / 'off' set it
    explicitly; 'default' clears it back to the instance default."""
    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": str(exc)}, status_code=403)

    choices = {"on": True, "off": False, "default": None}
    if mode not in choices:
        return back("/admin", err="Choose on, off, or default.")
    set_org_single_operator_mode(db, session.org_id, choices[mode])
    from ...db import audit
    audit(db, session.operator_name, "org.single_operator_set", "organization", session.org_id,
          {"single_operator_mode": choices[mode]}, org_id=session.org_id)
    db.commit()
    state = "on" if single_operator_mode(db, session.org_id) else "off"
    return back("/admin", msg=f"Single-operator mode is now {state}.")

@router.post("/admin/operators/{operator_id}/reset-password")
def admin_reset_password(
    request: Request, db: DB, operator_id: int,
    new_password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": str(exc)}, status_code=403)

    row = db.execute(
        "SELECT id FROM operators WHERE id=? AND org_id=?", (operator_id, session.org_id)
    ).fetchone()
    if row is None:
        return back("/admin", err="Operator not found.")
    try:
        auth.check_new_password(new_password)
    except auth.PasswordComplexityError as exc:
        return back("/admin", err=str(exc))

    auth.set_password(db, operator_id, new_password)
    from ...db import audit
    audit(db, session.operator_name, "operator.password_reset", "operator", operator_id,
          None, org_id=session.org_id)
    db.commit()
    return back("/admin", msg="Password reset. All of that operator's sessions were signed out.")

@router.post("/admin/operators/{operator_id}/unlock")
def admin_unlock_operator(
    request: Request, db: DB, operator_id: int, csrf_token: Annotated[str, Form()] = ""
):
    """Clear an operator's MFA lock and password-login lock (L-74, L-46).

    Same gate as the other /admin/operators actions: MLRO only, same org.
    """
    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": str(exc)}, status_code=403)

    row = db.execute(
        "SELECT id, name FROM operators WHERE id=? AND org_id=?", (operator_id, session.org_id)
    ).fetchone()
    if row is None:
        return back("/admin", err="Operator not found.")
    db.execute(
        "UPDATE operators SET failed_login_count=0, locked_until=NULL WHERE id=? AND org_id=?",
        (operator_id, session.org_id),
    )
    db.execute(
        "UPDATE mfa_secrets SET failed_attempts=0, locked_until=NULL WHERE operator_id=?",
        (operator_id,),
    )
    from ...db import audit
    audit(db, session.operator_name, "operator.unlock", "operator", operator_id,
          None, org_id=session.org_id)
    db.commit()
    return back("/admin", msg=f"Sign-in and MFA locks cleared for {row['name']}.")

@router.post("/admin/operators/{operator_id}/rename")
def admin_rename_operator(
    request: Request, db: DB, operator_id: int,
    name: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": str(exc)}, status_code=403)

    from ...cases.operators import rename_operator
    try:
        result = rename_operator(
            db, operator_id, session.org_id, name, actor=session.operator_name,
        )
    except ValueError as exc:
        return back("/admin", err=str(exc))
    if not result["changed"]:
        return back("/admin", msg="That is already this operator's name.")
    return back("/admin", msg=f"Renamed {result['old_name']} to {result['new_name']}.")

@router.post("/admin/operators")
def admin_create_operator(
    request: Request, db: DB,
    name: Annotated[str, Form()],
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    role: Annotated[str, Form()] = "officer",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": str(exc)}, status_code=403)

    try:
        auth.check_new_password(password)
        clean_name, clean_email = auth.check_operator_identity(name, email)
    except ValueError as exc:  # PasswordComplexityError / IdentityError
        return back("/admin", err=str(exc))
    if role not in auth.OPERATOR_ROLES:
        return back("/admin", err="Role must be Officer or MLRO.")
    from ...cases.operators import operator_name_taken
    if operator_name_taken(db, session.org_id, clean_name):
        return back("/admin", err="An operator with that name or email already exists.")
    try:
        check_limit(db, session.org_id, "operators")
    except BillingLimitError as exc:
        return back("/admin", err=str(exc))
    try:
        now = utcnow()
        cur = db.execute(
            # email_verified_at=now: an MLRO adding a known colleague inside
            # their own org is a different trust boundary from public
            # self-registration (see /register-organization) -- the admin is
            # already vouching for this person's identity, so there is no
            # separate email-ownership gap to close (see auth.login()'s
            # guard).
            """INSERT INTO operators
                   (org_id, name, email, password_hash, role, is_active, email_verified_at, created_at)
               VALUES (?,?,?,?,?,1,?,?)""",
            (session.org_id, clean_name, clean_email,
             auth.hash_password(password), role, now, now),
        )
    except sqlite3.IntegrityError:
        return back("/admin", err="An operator with that name or email already exists.")
    from ...db import audit
    audit(db, session.operator_name, "operator.create", "operator", cur.lastrowid,
          {"email": clean_email, "role": role}, org_id=session.org_id)
    db.commit()
    return back("/admin", msg=f"Operator {clean_name} created.")

@router.post("/admin/operators/{operator_id}/deactivate")
def admin_deactivate_operator(
    request: Request, db: DB, operator_id: int, csrf_token: Annotated[str, Form()] = ""
):
    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": str(exc)}, status_code=403)

    row = db.execute(
        "SELECT id, role, is_active FROM operators WHERE id=? AND org_id=?",
        (operator_id, session.org_id),
    ).fetchone()
    if row is None:
        return back("/admin", err="Operator not found.")
    if row["role"] == "mlro" and row["is_active"]:
        other_active_mlros = db.execute(
            "SELECT COUNT(*) c FROM operators WHERE org_id=? AND role='mlro' "
            "AND is_active=1 AND id != ?",
            (session.org_id, operator_id),
        ).fetchone()["c"]
        if other_active_mlros == 0:
            return back(
                "/admin",
                err="Cannot deactivate the last active MLRO. Promote another "
                    "operator to MLRO first.",
            )
    db.execute("UPDATE operators SET is_active=0 WHERE id=?", (operator_id,))
    auth.revoke_sessions_for(db, operator_id)
    from ...db import audit
    audit(db, session.operator_name, "operator.deactivate", "operator", operator_id,
          None, org_id=session.org_id)
    db.commit()
    return back("/admin", msg="Operator deactivated and signed out of every session.")

@router.post("/admin/operators/{operator_id}/reactivate")
def admin_reactivate_operator(
    request: Request, db: DB, operator_id: int, csrf_token: Annotated[str, Form()] = ""
):
    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": str(exc)}, status_code=403)

    row = db.execute(
        "SELECT id FROM operators WHERE id=? AND org_id=?", (operator_id, session.org_id)
    ).fetchone()
    if row is None:
        return back("/admin", err="Operator not found.")
    try:
        check_limit(db, session.org_id, "operators")
    except BillingLimitError as exc:
        return back("/admin", err=str(exc))
    db.execute("UPDATE operators SET is_active=1 WHERE id=? AND org_id=?", (operator_id, session.org_id))
    from ...db import audit
    audit(db, session.operator_name, "operator.reactivate", "operator", operator_id,
          None, org_id=session.org_id)
    db.commit()
    return back("/admin", msg="Operator reactivated.")
