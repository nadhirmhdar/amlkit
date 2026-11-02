"""Name screening, adverse media and full-book rescreen.

Moved verbatim from api/app.py (WP-18, issue #73): no route, dependency or limit changed.
"""

from __future__ import annotations

from __future__ import annotations

from typing import Annotated

from fastapi import Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ... import queries
from ...datamodel import MAX_NAME_LENGTH
from ..limits import limiter
from ...cases.manager import (
    ADVERSE_MEDIA_BATCH_LIMIT,
    disposition_adverse_media_finding,
    run_adverse_media,
    run_due_adverse_media,
)
from ...datamodel import validate_required_name
from ...match.engine import screen
from ...screening.adverse_media import DEFAULT_WINDOW_MONTHS
from ...screening.pf import triage_category
from ..deps import (
    current_session,
    require_csrf,
    require_role,
    require_session,
)



from fastapi import APIRouter

from ..helpers import (
    DB,
    back,
    log,
    render,
)

router = APIRouter()


# --------------------------------------------------------------------- screen
@router.get("/screen", response_class=HTMLResponse)
def screen_form(request: Request, db: DB, name: str = ""):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    return render(request, "screen.html", {"session": session, "result": None, "query": name.strip()[:200],
                                           "recent": queries.recent_adhoc_screenings(db, session.org_id)}, db)

@router.post("/screen", response_class=HTMLResponse)
@limiter.limit("10/minute")
def screen_run(
    request: Request, db: DB,
    name: Annotated[str, Form()],
    country: Annotated[str, Form()] = "",
    birth_date: Annotated[str, Form()] = "",
    gender: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return render(request, "screen.html", {"session": session, "result": None, "query": name, "err": str(exc)}, db)

    name = name.strip()
    try:
        validate_required_name("name", name)
    except ValueError:
        # Blank, or nothing but invisible characters: nothing to search.
        name = ""
    if not name:
        return render(request, "screen.html",
                      {"session": session, "result": None, "query": "", "err": "Enter a name to screen."}, db)
    if len(name) > MAX_NAME_LENGTH:
        too_long = render(request, "screen.html",
                          {"session": session, "result": None, "query": name[:MAX_NAME_LENGTH],
                           "err": f"Name exceeds {MAX_NAME_LENGTH} characters."}, db)
        too_long.status_code = 400
        return too_long

    result = screen(
        db, name, org_id=session.org_id, trigger="adhoc",
        threshold=queries.org_alert_threshold_or_default(db, session.org_id),
        country=country.strip() or None,
        birth_date=birth_date.strip() or None,
        gender=gender.strip() or None,
        actor=session.operator_name,
    )
    hits = []
    for h in result.hits:
        hits.append({
            "score": h.score, "caption": h.caption, "dataset": h.dataset,
            "schema_type": h.schema_type, "matched_name": h.matched_name,
            "category": triage_category(h.topics, h.programs),
            "obligation": h.obligation, "programs": h.programs,
            "detail": h.detail, "entity_id": h.entity_id,
            "aliases": queries.entity_names(db, h.entity_id),
        })
    return render(request, "screen.html", {
        "session": session, "query": name, "result": result, "hits": hits,
        "low_confidence": len(name.split()) < 2,
        "recent": queries.recent_adhoc_screenings(db, session.org_id),
    }, db)

# --------------------------------------------------------------- adverse media
@router.post("/customers/{customer_id}/adverse-media")
def customer_run_adverse_media(
    request: Request, db: DB, customer_id: int,
    window_months: Annotated[int, Form()] = DEFAULT_WINDOW_MONTHS,
    csrf_token: Annotated[str, Form()] = "",
):
    """Run an adverse-media check for one customer, on demand.

    Deliberately operator-triggered rather than part of onboarding or the
    post-refresh re-screen: the provider is a free public service rate-limited
    to one request every five seconds, so this cannot run in a loop over a
    whole customer book. See screening/adverse_media.py's module docstring.
    """
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    back_url = f"/customers/{customer_id}"
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back(back_url, err=str(exc))

    data = queries.customer(db, customer_id, session.org_id)
    if data is None:
        return back("/customers", err=f"Customer {customer_id} not found.")
    c = data["customer"]

    _, result, new_findings = run_adverse_media(
        db,
        org_id=session.org_id,
        customer_id=customer_id,
        name=c["full_name"],
        name_arabic=c["name_arabic"],
        trigger="adhoc",
        window_months=max(1, min(int(window_months or DEFAULT_WINDOW_MONTHS), 120)),
        actor=session.operator_name,
    )
    # A provider outage is reported as a warning, not an error: the check was
    # attempted and the attempt is on the record. Presenting it as a failed
    # action would invite the operator to assume nothing was written.
    if result.status != "ok":
        return back(back_url, err=f"Adverse media check could not complete: {result.error}")
    if not result.findings:
        return back(back_url, msg=f"Adverse media: no adverse coverage found "
                                  f"({result.articles_considered} articles screened).")
    return back(back_url, msg=f"Adverse media: {len(result.findings)} finding(s), "
                              f"{new_findings} new to review.")

ADVERSE_LIST_CAP = 200

@router.get("/adverse-media", response_class=HTMLResponse)
def adverse_media_list(request: Request, db: DB, status: str = "open"):
    """Every adverse-media finding across the firm's customers, for triage.

    Read-only: a finding is marked relevant or not relevant on its customer's
    page, where the rest of the file is. This is the list that tells you which
    customers to open."""
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    status = status if status in (*queries.ADVERSE_STATUSES, "all") else "open"
    findings = queries.adverse_media_queue(
        db, session.org_id, status=None if status == "all" else status,
        limit=ADVERSE_LIST_CAP, oldest_first=True)
    counts = queries.adverse_media_counts(db, session.org_id)
    return render(request, "adverse_media.html", {
        "session": session, "findings": findings, "status": status, "counts": counts,
        "truncated": counts[status] > len(findings), "cap": ADVERSE_LIST_CAP,
    }, db)

@router.post("/adverse-media/run-due")
def adverse_media_run_due(
    request: Request, db: DB,
    limit: Annotated[int, Form()] = ADVERSE_MEDIA_BATCH_LIMIT,
    csrf_token: Annotated[str, Form()] = "",
):
    """Re-check the next few customers whose adverse media is due.

    Bounded and operator-triggered, not a scheduled sweep -- the provider's
    rate limit makes a whole-book batch impossible, so this is "work through
    the next few" with the throttle still between each one. The request blocks
    for the duration, which is why the form caps the batch rather than
    offering "run all".
    """
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back("/dashboard", err=str(exc))

    outcome = run_due_adverse_media(
        db, session.org_id,
        limit=max(1, min(int(limit or ADVERSE_MEDIA_BATCH_LIMIT), 20)),
        actor=session.operator_name,
    )
    if outcome["attempted"] == 0:
        return back("/dashboard", msg="Nothing due for an adverse media check.")
    # Failures are reported alongside successes rather than instead of them:
    # a batch where the provider died halfway still checked the first few, and
    # saying only "it failed" would understate what is on the record.
    msg = (f"Adverse media: checked {outcome['checked']}, "
           f"{outcome['new_findings']} new finding(s), "
           f"{outcome['still_due']} still due.")
    if outcome["failed"]:
        return back("/dashboard", err=msg + f" {outcome['failed']} could not complete.")
    return back("/dashboard", msg=msg)

@router.post("/adverse-media/{finding_id}/disposition")
def adverse_media_disposition(
    request: Request, db: DB, finding_id: int,
    status: Annotated[str, Form()],
    note: Annotated[str, Form()] = "",
    customer_id: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    back_url = f"/customers/{customer_id}" if customer_id.strip() else "/alerts"
    try:
        require_csrf(request, csrf_token)
        rating = disposition_adverse_media_finding(
            db, finding_id, session.org_id, status=status, note=note,
            actor=session.operator_name,
        )
    except (PermissionError, ValueError) as exc:
        return back(back_url, err=str(exc))
    # The re-rating is surfaced rather than left to be discovered on reload:
    # confirming a finding relevant is the one action here that can move a
    # customer's risk band, and the operator should see that it did.
    msg = "Adverse media finding dispositioned."
    if status == "relevant" and rating:
        msg += f" Customer re-rated {rating}."
    return back(back_url, msg=msg)

@router.post("/admin/rescreen")
@limiter.limit("10/minute")
def admin_rescreen(
    request: Request, db: DB,
    csrf_token: Annotated[str, Form()] = "",
):
    """Manually trigger bulk re-screening of all active customers.

    MLRO-only endpoint. Calls rescreen_all() without refreshing sanctions lists.
    Returns count of customers re-screened and new alerts created.
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

    from ...match.engine import rescreen_all
    from ...db import audit

    audit(db, session.operator_name, "system.rescreen_all", org_id=session.org_id)

    try:
        outcome = rescreen_all(db, session.org_id, actor=session.operator_name)
        db.commit()

        msg = f"Re-screened {outcome['screened']} name(s) across customers and related parties."
        if outcome["alerts"]:
            msg += f" {outcome['alerts']} new alert(s) raised — check Alerts."
        if outcome.get("unscreenable"):
            msg += (
                f" {outcome['unscreenable']} name(s) could not be screened"
                " (no searchable tokens) and need manual screening."
            )
        return back("/admin", msg=msg)
    except Exception as exc:
        log.exception("rescreen_all failed for org %s: %s", session.org_id, exc)
        return back("/admin", err=f"Re-screening failed: {exc}")
