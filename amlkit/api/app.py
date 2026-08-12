"""FastAPI application.

Routes are thin: they authenticate the request, collect form input, call the
existing engine functions with the session's org_id, and render. All
screening, risk, review and tenancy logic lives in `amlkit.match`,
`amlkit.cases`, `amlkit.risk`, `amlkit.auth` and `amlkit.db` -- duplicating
any of it here would create a second implementation that tests do not cover.

Every route that reads or writes tenant data resolves a session first and
passes `session.org_id` into the library call. There is no route that skips
this: `queries.py` and the write-path functions in `cases`/`match`/`risk`
require `org_id` as a mandatory argument, so a route that forgot to check the
session would fail to even construct the call, not silently query across
every tenant.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import auth, queries
from ..cases.manager import add_ubo, close_relationship, onboard
from ..cases.review import (
    REASON_CODES,
    ReviewError,
    confirm_disposition,
    propose_disposition,
    review_history,
    single_operator_mode,
)
from ..db import utcnow
from ..match.engine import screen
from ..names.arabic import has_arabic_script
from ..risk.model import ruleset
from .deps import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    current_session,
    db_path,
    get_db,
    require_csrf,
    require_role,
    require_session,
    startup_warning,
)

WEB = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="amlkit", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")
templates = Jinja2Templates(directory=str(WEB / "templates"))
templates.env.globals["has_arabic"] = has_arabic_script

DB = Annotated[sqlite3.Connection, Depends(get_db)]

# Cookie lifetime for the CSRF token mirrors the session's: no point in one
# outliving the other.
_COOKIE_MAX_AGE = int(auth.SESSION_LIFETIME.total_seconds())


def render(request: Request, name: str, ctx: dict, db: sqlite3.Connection | None = None) -> HTMLResponse:
    """Render with the context every page needs, including a fresh CSRF token
    for any form on the page."""
    session = ctx.get("session")
    if session is None and db is not None:
        session = current_session(request, db)
    ctx.setdefault("session", session)
    ctx.setdefault("security_warning", startup_warning())
    ctx.setdefault("single_operator", single_operator_mode())
    ctx.setdefault("msg", request.query_params.get("msg"))
    ctx.setdefault("err", request.query_params.get("err"))
    ctx.setdefault("csrf_token", request.cookies.get(CSRF_COOKIE) or auth.new_csrf_token())
    return templates.TemplateResponse(request, name, ctx)


def back(url: str, msg: str = "", err: str = "") -> RedirectResponse:
    from urllib.parse import quote

    sep = "&" if "?" in url else "?"
    if msg:
        url = f"{url}{sep}msg={quote(msg)}"
    elif err:
        url = f"{url}{sep}err={quote(err)}"
    return RedirectResponse(url, status_code=303)


def _set_csrf_cookie(resp, request: Request) -> None:
    """Ensure every response carries a CSRF cookie, issuing one if absent."""
    if not request.cookies.get(CSRF_COOKIE):
        resp.set_cookie(CSRF_COOKIE, auth.new_csrf_token(), httponly=False,
                        samesite="strict", secure=False, max_age=_COOKIE_MAX_AGE)


@app.middleware("http")
async def ensure_csrf_cookie(request: Request, call_next):
    response = await call_next(request)
    _set_csrf_cookie(response, request)
    return response


# ----------------------------------------------------------------- sign-in
@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, db: DB):
    return render(request, "login.html", {"session": None})


def _login_page_error(request: Request, message: str) -> HTMLResponse:
    return render(request, "login.html", {"session": None, "err": message})


@app.post("/login")
def login_submit(
    request: Request, db: DB,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return _login_page_error(request, str(exc))
    try:
        token, info = auth.login(db, email, password)
    except auth.AuthError as exc:
        return _login_page_error(request, str(exc))
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="strict",
                    max_age=_COOKIE_MAX_AGE)
    return resp


@app.post("/logout")
def logout_submit(request: Request, db: DB):
    session = current_session(request, db)
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        auth.logout(db, token, session)
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


@app.get("/setup", response_class=HTMLResponse)
def setup_form(request: Request, db: DB, token: str = ""):
    row = _valid_setup_token(db, token)
    if row is None:
        return render(request, "setup.html", {
            "session": None, "valid": False,
            "err": "This setup link is invalid, expired, or already used.",
        })
    org = db.execute("SELECT name FROM organizations WHERE id=?", (row["org_id"],)).fetchone()
    return render(request, "setup.html", {
        "session": None, "valid": True, "token": token, "org_name": org["name"],
    })


@app.post("/setup")
def setup_submit(
    request: Request, db: DB,
    token: Annotated[str, Form()],
    name: Annotated[str, Form()],
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return render(request, "setup.html", {"session": None, "valid": True, "token": token, "err": str(exc)})

    row = _valid_setup_token(db, token)
    if row is None:
        return render(request, "setup.html", {
            "session": None, "valid": False,
            "err": "This setup link is invalid, expired, or already used.",
        })
    if len(password) < 10:
        return render(request, "setup.html", {
            "session": None, "valid": True, "token": token,
            "err": "Password must be at least 10 characters.",
        })

    now = utcnow()
    cur = db.execute(
        """INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at)
           VALUES (?,?,?,?,?,1,?)""",
        (row["org_id"], name.strip(), email.strip().lower(),
         auth.hash_password(password), "mlro", now),
    )
    operator_id = cur.lastrowid
    db.execute("UPDATE setup_tokens SET used_at=? WHERE id=?", (now, row["id"]))
    db.commit()
    from ..db import audit
    audit(db, name.strip(), "operator.setup_claimed", "operator", operator_id,
          {"email": email.strip().lower()}, org_id=row["org_id"])
    db.commit()

    session_token, _ = auth.login(db, email.strip().lower(), password)
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(SESSION_COOKIE, session_token, httponly=True, samesite="strict",
                    max_age=_COOKIE_MAX_AGE)
    return resp


def _valid_setup_token(db: sqlite3.Connection, raw_token: str):
    if not raw_token:
        return None
    from hashlib import sha256
    row = db.execute(
        "SELECT id, org_id, used_at FROM setup_tokens WHERE token_hash=?",
        (sha256(raw_token.encode()).hexdigest(),),
    ).fetchone()
    if row is None or row["used_at"] is not None:
        return None
    return row


@app.get("/register-organization", response_class=HTMLResponse)
def register_org_form(request: Request, db: DB):
    return render(request, "register_organization.html", {"session": None})


@app.post("/register-organization")
def register_org_submit(
    request: Request, db: DB,
    org_name: Annotated[str, Form()],
    name: Annotated[str, Form()],
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return render(request, "register_organization.html", {"session": None, "err": str(exc)})

    if len(password) < 10:
        return render(request, "register_organization.html",
                      {"session": None, "err": "Password must be at least 10 characters."})

    import re
    slug = re.sub(r"[^a-z0-9]+", "-", org_name.strip().lower()).strip("-") or "org"
    now = utcnow()
    try:
        cur = db.execute(
            "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
            (org_name.strip(), slug, "active", now),
        )
    except sqlite3.IntegrityError:
        return render(request, "register_organization.html",
                      {"session": None, "err": f"An organization with a similar name already exists."})
    org_id = cur.lastrowid
    cur2 = db.execute(
        """INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at)
           VALUES (?,?,?,?,?,1,?)""",
        (org_id, name.strip(), email.strip().lower(), auth.hash_password(password), "mlro", now),
    )
    operator_id = cur2.lastrowid
    db.commit()
    from ..db import audit
    audit(db, name.strip(), "organization.register", "organization", org_id,
          {"org_name": org_name.strip()}, org_id=org_id)
    db.commit()

    session_token, _ = auth.login(db, email.strip().lower(), password)
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(SESSION_COOKIE, session_token, httponly=True, samesite="strict",
                    max_age=_COOKIE_MAX_AGE)
    return resp


# ------------------------------------------------------------------ dashboard
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: DB):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    return render(request, "dashboard.html", {
        "session": session,
        "d": queries.dashboard(db, session.org_id),
        "datasets": queries.datasets(db),
    })


# --------------------------------------------------------------------- screen
@app.get("/screen", response_class=HTMLResponse)
def screen_form(request: Request, db: DB):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    return render(request, "screen.html", {"session": session, "result": None, "query": ""})


@app.post("/screen", response_class=HTMLResponse)
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
        return render(request, "screen.html", {"session": session, "result": None, "query": name, "err": str(exc)})

    name = name.strip()
    if not name:
        return render(request, "screen.html",
                      {"session": session, "result": None, "query": "", "err": "Enter a name to screen."})

    result = screen(
        db, name, org_id=session.org_id, trigger="adhoc",
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
            "category": ("proliferation" if h.is_proliferation
                         else "terrorism" if h.is_terrorism
                         else "sanction" if h.is_sanction else "other"),
            "obligation": h.obligation, "programs": h.programs,
            "detail": h.detail, "entity_id": h.entity_id,
            "aliases": queries.entity_names(db, h.entity_id),
        })
    return render(request, "screen.html", {
        "session": session, "query": name, "result": result, "hits": hits,
        "low_confidence": len(name.split()) < 2,
    })


# ------------------------------------------------------------------ customers
@app.get("/customers", response_class=HTMLResponse)
def customers(request: Request, db: DB):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    return render(request, "customers.html",
                 {"session": session, "customers": queries.customer_list(db, session.org_id)})


@app.get("/customers/new", response_class=HTMLResponse)
def customer_new(request: Request, db: DB):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    rs = ruleset()
    return render(request, "customer_new.html", {
        "session": session,
        "sectors": sorted(rs["factors"]["sector"]["points_by_sector"]),
        "channels": sorted(rs["factors"]["delivery_channel"]["points_by_channel"]),
        "structures": sorted(rs["factors"]["structure"]["points_by_type"]),
        "tiers": sorted(rs["factors"]["jurisdiction"]["points_by_tier"]),
    })


@app.post("/customers")
def customer_create(
    request: Request, db: DB,
    reference: Annotated[str, Form()],
    full_name: Annotated[str, Form()],
    customer_type: Annotated[str, Form()] = "natural",
    name_arabic: Annotated[str, Form()] = "",
    nationality: Annotated[str, Form()] = "",
    birth_date: Annotated[str, Form()] = "",
    gender: Annotated[str, Form()] = "",
    sector: Annotated[str, Form()] = "other",
    delivery_channel: Annotated[str, Form()] = "face_to_face",
    cash_level: Annotated[str, Form()] = "non_cash",
    jurisdiction_tier: Annotated[str, Form()] = "standard",
    structure: Annotated[str, Form()] = "natural_person",
    ubo_names: Annotated[list[str], Form()] = [],
    ubo_pcts: Annotated[list[str], Form()] = [],
    ubo_controls: Annotated[list[str], Form()] = [],
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back("/customers/new", err=str(exc))

    ubos = []
    for i, nm in enumerate(ubo_names):
        nm = (nm or "").strip()
        if not nm:
            continue
        pct_raw = ubo_pcts[i] if i < len(ubo_pcts) else ""
        try:
            pct = float(pct_raw) if str(pct_raw).strip() else None
        except ValueError:
            pct = None
        ubos.append({
            "person_name": nm,
            "ownership_pct": pct,
            "control_type": (ubo_controls[i] if i < len(ubo_controls) else "ownership") or "ownership",
        })

    try:
        result = onboard(
            db, org_id=session.org_id, reference=reference.strip(), full_name=full_name.strip(),
            customer_type=customer_type, name_arabic=name_arabic.strip() or None,
            nationality=nationality.strip() or None, birth_date=birth_date.strip() or None,
            gender=gender.strip() or None, sector=sector,
            delivery_channel=delivery_channel, cash_level=cash_level,
            jurisdiction_tier=jurisdiction_tier, structure=structure,
            ubos=ubos, actor=session.operator_name,
        )
    except sqlite3.IntegrityError:
        return back("/customers/new", err=f"Reference {reference!r} already exists.")

    note = (
        "Onboarded. MATCH FOUND - see alerts, freeze without delay and do not tip off."
        if result.blocked else
        f"Onboarded. Risk rating: {result.risk.rating}."
    )
    return back(f"/customers/{result.customer_id}", msg=note)


@app.get("/customers/{customer_id}", response_class=HTMLResponse)
def customer_detail(request: Request, db: DB, customer_id: int):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    data = queries.customer(db, customer_id, session.org_id)
    if data is None:
        return back("/customers", err=f"Customer {customer_id} not found.")
    return render(request, "customer.html",
                 data | {"session": session, "reason_codes": REASON_CODES})


@app.get("/customers/{customer_id}/evidence", response_class=HTMLResponse)
def evidence_pack(request: Request, db: DB, customer_id: int):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    data = queries.customer(db, customer_id, session.org_id)
    if data is None:
        return back("/customers", err=f"Customer {customer_id} not found.")
    for alert in data["alerts"]:
        alert["reviews"] = review_history(db, alert["id"], session.org_id)
    return render(request, "evidence.html", data | {"session": session})


@app.post("/customers/{customer_id}/close")
def customer_close(request: Request, db: DB, customer_id: int,
                   csrf_token: Annotated[str, Form()] = ""):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back(f"/customers/{customer_id}", err=str(exc))
    until = close_relationship(db, customer_id, org_id=session.org_id, actor=session.operator_name)
    return back(f"/customers/{customer_id}", msg=f"Relationship closed. Records retained until {until}.")


@app.post("/customers/{customer_id}/ubo")
def customer_add_ubo(
    request: Request, db: DB, customer_id: int,
    person_name: Annotated[str, Form()],
    ownership_pct: Annotated[str, Form()] = "",
    control_type: Annotated[str, Form()] = "ownership",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back(f"/customers/{customer_id}", err=str(exc))
    try:
        pct = float(ownership_pct) if ownership_pct.strip() else None
    except ValueError:
        pct = None
    ubo_id = add_ubo(db, customer_id, org_id=session.org_id, person_name=person_name.strip(),
                     ownership_pct=pct, control_type=control_type, actor=session.operator_name)
    res = screen(db, person_name.strip(), org_id=session.org_id, trigger="onboarding",
                 customer_id=customer_id, ubo_id=ubo_id, actor=session.operator_name)
    note = ("Beneficial owner added. MATCH FOUND - review alerts."
            if res.hits else "Beneficial owner added and screened clear.")
    return back(f"/customers/{customer_id}", msg=note)


# --------------------------------------------------------------------- alerts
@app.get("/alerts", response_class=HTMLResponse)
def alerts(request: Request, db: DB, status: str = "open"):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    queue = queries.alert_queue(db, session.org_id, status=None if status == "all" else status)
    for a in queue:
        a["reviews"] = review_history(db, a["id"], session.org_id)
    return render(request, "alerts.html", {
        "session": session, "alerts": queue, "status": status, "reason_codes": REASON_CODES,
    })


@app.post("/alerts/{alert_id}/disposition")
def alert_disposition(
    request: Request, db: DB, alert_id: int,
    status: Annotated[str, Form()],
    reason_code: Annotated[str, Form()] = "",
    narrative: Annotated[str, Form()] = "",
    back_to: Annotated[str, Form()] = "/alerts",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
        outcome = propose_disposition(
            db, alert_id, org_id=session.org_id, status=status, reason_code=reason_code,
            operator=session.operator_name, narrative=narrative,
        )
    except (PermissionError, ReviewError) as exc:
        return back(back_to, err=str(exc))
    return back(back_to, msg=outcome.message)


@app.post("/alerts/{alert_id}/confirm")
def alert_confirm(
    request: Request, db: DB, alert_id: int,
    agree: Annotated[str, Form()] = "yes",
    narrative: Annotated[str, Form()] = "",
    back_to: Annotated[str, Form()] = "/alerts",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
        outcome = confirm_disposition(
            db, alert_id, org_id=session.org_id, operator=session.operator_name,
            agree=(agree == "yes"), narrative=narrative,
        )
    except (PermissionError, ReviewError) as exc:
        return back(back_to, err=str(exc))
    return back(back_to, msg=outcome.message)


# ---------------------------------------------------------------------- audit
@app.get("/audit", response_class=HTMLResponse)
def audit_view(request: Request, db: DB):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    return render(request, "audit.html",
                 {"session": session, "entries": queries.audit_trail(db, session.org_id, limit=300)})


# ---------------------------------------------------------------------- admin
@app.get("/admin", response_class=HTMLResponse)
def admin_view(request: Request, db: DB):
    try:
        session = require_session(request, db)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        return back("/", err=str(exc))
    org = db.execute("SELECT name, slug FROM organizations WHERE id=?", (session.org_id,)).fetchone()
    return render(request, "admin.html", {
        "session": session, "org": dict(org),
        "operators": queries.operators(db, session.org_id),
    })


@app.post("/admin/operators/{operator_id}/reset-password")
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
        return back("/admin", err=str(exc))

    row = db.execute(
        "SELECT id FROM operators WHERE id=? AND org_id=?", (operator_id, session.org_id)
    ).fetchone()
    if row is None:
        return back("/admin", err="Operator not found.")
    if len(new_password) < 10:
        return back("/admin", err="Password must be at least 10 characters.")

    auth.set_password(db, operator_id, new_password)
    from ..db import audit
    audit(db, session.operator_name, "operator.password_reset", "operator", operator_id,
          None, org_id=session.org_id)
    db.commit()
    return back("/admin", msg="Password reset. All of that operator's sessions were signed out.")


@app.post("/admin/operators")
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
        return back("/admin", err=str(exc))

    if len(password) < 10:
        return back("/admin", err="Password must be at least 10 characters.")
    try:
        cur = db.execute(
            """INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at)
               VALUES (?,?,?,?,?,1,?)""",
            (session.org_id, name.strip(), email.strip().lower(),
             auth.hash_password(password), role, utcnow()),
        )
    except sqlite3.IntegrityError:
        return back("/admin", err="An operator with that name or email already exists.")
    from ..db import audit
    audit(db, session.operator_name, "operator.create", "operator", cur.lastrowid,
          {"email": email.strip().lower(), "role": role}, org_id=session.org_id)
    db.commit()
    return back("/admin", msg=f"Operator {name.strip()} created.")


@app.post("/admin/operators/{operator_id}/deactivate")
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
        return back("/admin", err=str(exc))

    row = db.execute(
        "SELECT id FROM operators WHERE id=? AND org_id=?", (operator_id, session.org_id)
    ).fetchone()
    if row is None:
        return back("/admin", err="Operator not found.")
    db.execute("UPDATE operators SET is_active=0 WHERE id=?", (operator_id,))
    auth.revoke_sessions_for(db, operator_id)
    from ..db import audit
    audit(db, session.operator_name, "operator.deactivate", "operator", operator_id,
          None, org_id=session.org_id)
    db.commit()
    return back("/admin", msg="Operator deactivated and signed out of every session.")
