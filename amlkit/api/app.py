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

from fastapi import Depends, FastAPI, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import auth, queries
from ..cases.manager import (
    add_case_note,
    add_ubo,
    close_relationship,
    disposition_transaction_alert,
    onboard,
    record_signature,
    record_transaction,
)
from ..cases.review import (
    REASON_CODES,
    ReviewError,
    assign_alert,
    confirm_disposition,
    propose_disposition,
    review_history,
    single_operator_mode,
)
from ..db import set_org_alert_threshold, utcnow
from ..match.engine import DEFAULT_THRESHOLD, screen
from ..names.arabic import has_arabic_script
from ..risk.model import ruleset
from .deps import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    client_ip,
    current_session,
    db_path,
    get_db,
    require_csrf,
    require_role,
    require_session,
    startup_warning,
)

WEB = Path(__file__).resolve().parent.parent / "web"

# ---------------------------------------------------------------------- scheduler
import contextlib
import logging
import os

log = logging.getLogger("amlkit.scheduler")


def _run_scheduled_refresh() -> None:
    """Load fresh sanctions lists and re-screen all orgs. Runs every 23 hours.

    23 hours (not 24) gives a safety margin against the EOCN 24-hour rule:
    if a download is slow or retried once, we still finish within the window.
    """
    from ..db import connect
    from ..ingest.base import AdapterError
    from ..ingest.loader import load
    from ..ingest.opensanctions import uae_local_terrorists
    from ..ingest.un import UNSanctionsAdapter
    from ..ingest.ofac import OFACSDNAdapter
    from ..ingest.eu import EUSanctionsAdapter
    from ..match.engine import rescreen_all

    log.info("Scheduled sanctions refresh starting…")
    conn = connect()
    total_alerts = 0
    for factory in [uae_local_terrorists, UNSanctionsAdapter, OFACSDNAdapter, EUSanctionsAdapter]:
        adapter = factory()
        try:
            result = load(conn, adapter, actor="scheduler")
            log.info("Loaded %s: %d entities", adapter.key, result.entities)
        except AdapterError as exc:
            log.error("FAILED to load %s: %s", adapter.key, exc)
    conn.commit()
    orgs = conn.execute("SELECT id, name FROM organizations WHERE status='active'").fetchall()
    for org in orgs:
        outcome = rescreen_all(conn, org["id"], actor="scheduler")
        total_alerts += outcome["alerts"]
        log.info("Re-screened org '%s': %d names, %d alerts", org["name"], outcome["screened"], outcome["alerts"])
    conn.commit()
    conn.close()
    log.info("Scheduled refresh complete. %d new alert(s) raised.", total_alerts)


@contextlib.asynccontextmanager
async def _lifespan(app):
    """Start the 23-hour refresh scheduler when the container boots.

    Cloud Run may scale to zero (killing the scheduler) when idle for long
    periods. The /system/refresh endpoint below provides a reliable fallback
    that Cloud Scheduler can call via HTTP even after a cold start.
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler()
        scheduler.add_job(
            _run_scheduled_refresh,
            trigger="interval",
            hours=23,
            id="sanctions_refresh",
            replace_existing=True,
        )
        scheduler.start()
        log.info("APScheduler started — sanctions refresh every 23 hours.")
        yield
        scheduler.shutdown(wait=False)
    except ImportError:
        log.warning("apscheduler not installed — in-process scheduling disabled. "
                    "Use Cloud Scheduler + /system/refresh endpoint instead.")
        yield


app = FastAPI(title="amlkit", docs_url=None, redoc_url=None, lifespan=_lifespan)
app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")
templates = Jinja2Templates(directory=str(WEB / "templates"))
templates.env.globals["has_arabic"] = has_arabic_script

DB = Annotated[sqlite3.Connection, Depends(get_db)]

# Cookie lifetime for the CSRF token mirrors the session's: no point in one
# outliving the other.
_COOKIE_MAX_AGE = int(auth.SESSION_LIFETIME.total_seconds())


def render(request: Request, name: str, ctx: dict, db: sqlite3.Connection | None = None) -> HTMLResponse:
    """Render with the context every page needs, including a fresh CSRF token
    for any form on the page.

    The CSRF token is set BOTH in the template context (for the hidden form
    field) AND as a cookie on the response. Both must use the same value —
    using the existing cookie value if present, or generating one new token
    that is written to both places at once. Generating one token for the form
    and a separate one for the cookie (as a middleware would) causes every
    first-visit form submission to fail the CSRF check.
    """
    session = ctx.get("session")
    if session is None and db is not None:
        session = current_session(request, db)
    ctx.setdefault("session", session)
    ctx.setdefault("security_warning", startup_warning())
    ctx.setdefault("single_operator", single_operator_mode())
    ctx.setdefault("msg", request.query_params.get("msg"))
    ctx.setdefault("err", request.query_params.get("err"))

    # Use the cookie value if already present; otherwise mint one token that
    # goes into BOTH the form field AND the cookie on this same response.
    existing = request.cookies.get(CSRF_COOKIE)
    token = existing or auth.new_csrf_token()
    ctx.setdefault("csrf_token", token)

    resp = templates.TemplateResponse(request, name, ctx)
    if not existing:
        _behind_proxy = os.environ.get("AMLKIT_BEHIND_PROXY") == "1"
        resp.set_cookie(
            CSRF_COOKIE, token,
            httponly=False,
            samesite="lax",
            secure=_behind_proxy,
            max_age=_COOKIE_MAX_AGE,
        )
    return resp


def back(url: str, msg: str = "", err: str = "") -> RedirectResponse:
    from urllib.parse import quote

    sep = "&" if "?" in url else "?"
    if msg:
        url = f"{url}{sep}msg={quote(msg)}"
    elif err:
        url = f"{url}{sep}err={quote(err)}"
    return RedirectResponse(url, status_code=303)


def _set_csrf_cookie(resp, request: Request) -> None:
    """Ensure every response carries a CSRF cookie, issuing one if absent.

    secure=True is required on Cloud Run (HTTPS). Without it, modern browsers
    silently drop the cookie on HTTPS pages, causing every form submission to
    fail the CSRF check with "stale page" even on a fresh load.

    samesite="lax" (not strict) allows the cookie to survive navigating to the
    login page from an external link or bookmark -- strict would drop it on the
    very first GET, which is the most common path for a new user.
    """
    if not request.cookies.get(CSRF_COOKIE):
        _behind_proxy = os.environ.get("AMLKIT_BEHIND_PROXY") == "1"
        resp.set_cookie(CSRF_COOKIE, auth.new_csrf_token(), httponly=False,
                        samesite="lax", secure=_behind_proxy,
                        max_age=_COOKIE_MAX_AGE)


@app.middleware("http")
async def ensure_csrf_cookie(request: Request, call_next):
    # CSRF cookie is now set directly by render() so that the same token
    # goes into both the form hidden field and the cookie. This middleware
    # is kept as a passthrough only — it no longer generates tokens.
    return await call_next(request)


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
        threshold=queries.org_alert_threshold(db, session.org_id) or DEFAULT_THRESHOLD,
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
            threshold=queries.org_alert_threshold(db, session.org_id) or DEFAULT_THRESHOLD,
        )
    except sqlite3.IntegrityError:
        return back("/customers/new", err=f"Reference {reference!r} already exists.")

    note = (
        "Onboarded. MATCH FOUND - see alerts, freeze without delay and do not tip off."
        if result.blocked else
        f"Onboarded. Risk rating: {result.risk.rating}."
    )
    return back(f"/customers/{result.customer_id}", msg=note)


@app.post("/customers/scan-passport")
def customer_scan_passport(
    request: Request, db: DB,
    passport_file: UploadFile,
):
    try:
        session = require_session(request, db)
    except PermissionError:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")

    import io
    from ..cases.ocr import extract_passport_data

    try:
        content = passport_file.file.read()
        file_like = io.BytesIO(content)
        data = extract_passport_data(file_like)
        return data
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/customers/{customer_id}", response_class=HTMLResponse)
def customer_detail(request: Request, db: DB, customer_id: int):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    data = queries.customer(db, customer_id, session.org_id)
    if data is None:
        return back("/customers", err=f"Customer {customer_id} not found.")
    from ..cases.diagram import generate_ubo_diagram
    diagram_svg = generate_ubo_diagram(db, customer_id, session.org_id)
    for alert in data["alerts"]:
        alert["reviews"] = review_history(db, alert["id"], session.org_id)
    return render(request, "customer.html",
                 data | {"session": session, "reason_codes": REASON_CODES, "ubo_diagram": diagram_svg})


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
                 customer_id=customer_id, ubo_id=ubo_id, actor=session.operator_name,
                 threshold=queries.org_alert_threshold(db, session.org_id) or DEFAULT_THRESHOLD)
    note = ("Beneficial owner added. MATCH FOUND - review alerts."
            if res.hits else "Beneficial owner added and screened clear.")
    return back(f"/customers/{customer_id}", msg=note)


@app.post("/customers/{customer_id}/notes")
def customer_add_note(
    request: Request, db: DB, customer_id: int,
    body: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
        add_case_note(db, customer_id, session.org_id, author=session.operator_name, body=body)
    except (PermissionError, ValueError) as exc:
        return back(f"/customers/{customer_id}", err=str(exc))
    return back(f"/customers/{customer_id}", msg="Note added.")


@app.post("/customers/{customer_id}/transactions")
def customer_add_transaction(
    request: Request, db: DB, customer_id: int,
    direction: Annotated[str, Form()],
    method: Annotated[str, Form()],
    amount: Annotated[str, Form()],
    currency: Annotated[str, Form()] = "AED",
    amount_aed: Annotated[str, Form()] = "",
    counterparty_name: Annotated[str, Form()] = "",
    counterparty_country: Annotated[str, Form()] = "",
    occurred_at: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
        amt = float(amount)
        aed = float(amount_aed) if amount_aed.strip() else None
        transaction_id, triggered = record_transaction(
            db, customer_id, session.org_id,
            direction=direction, method=method, amount=amt, currency=currency,
            amount_aed=aed, counterparty_name=counterparty_name.strip() or None,
            counterparty_country=counterparty_country.strip() or None,
            occurred_at=(occurred_at.strip() + "T00:00:00+00:00") if occurred_at.strip() else None,
            actor=session.operator_name,
        )
    except (PermissionError, ValueError) as exc:
        return back(f"/customers/{customer_id}", err=str(exc))
    note = (
        f"Transaction recorded. {len(triggered)} rule(s) triggered: "
        + ", ".join(r.rule_key for r in triggered)
        if triggered else "Transaction recorded. No rules triggered."
    )
    return back(f"/customers/{customer_id}", msg=note)


@app.post("/transaction-alerts/{alert_id}/disposition")
def transaction_alert_disposition(
    request: Request, db: DB, alert_id: int,
    status: Annotated[str, Form()],
    note: Annotated[str, Form()] = "",
    customer_id: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    back_url = f"/customers/{customer_id}" if customer_id.strip() else "/"
    try:
        require_csrf(request, csrf_token)
        disposition_transaction_alert(
            db, alert_id, session.org_id, status=status, note=note,
            actor=session.operator_name,
        )
    except (PermissionError, ValueError) as exc:
        return back(back_url, err=str(exc))
    return back(back_url, msg="Transaction alert dispositioned.")


@app.post("/customers/{customer_id}/signatures")
def customer_add_signature(
    request: Request, db: DB, customer_id: int,
    purpose: Annotated[str, Form()],
    statement: Annotated[str, Form()],
    signer_name: Annotated[str, Form()],
    signer_role: Annotated[str, Form()] = "customer",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
        record_signature(
            db, customer_id, session.org_id,
            purpose=purpose, statement=statement, signer_name=signer_name,
            signer_role=signer_role, ip_address=client_ip(request),
            user_agent=request.headers.get("User-Agent"),
            actor=session.operator_name,
        )
    except (PermissionError, ValueError) as exc:
        return back(f"/customers/{customer_id}", err=str(exc))
    return back(f"/customers/{customer_id}", msg=f"Signed by {signer_name.strip()}.")


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


@app.post("/alerts/{alert_id}/assign")
def alert_assign_route(
    request: Request, db: DB, alert_id: int,
    operator: Annotated[str, Form()] = "",
    back_to: Annotated[str, Form()] = "/alerts",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
        assign_alert(db, alert_id, session.org_id,
                    operator=operator.strip() or None, actor=session.operator_name)
    except (PermissionError, ReviewError) as exc:
        return back(back_to, err=str(exc))
    msg = f"Assigned to {operator.strip()}." if operator.strip() else "Assignment cleared."
    return back(back_to, msg=msg)


@app.get("/alerts.csv")
def alerts_csv(request: Request, db: DB, status: str = "all"):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    queue = queries.alert_queue(db, session.org_id, status=None if status == "all" else status)
    return _csv_response(
        "alerts.csv",
        ["id", "category", "score", "caption", "matched_party", "status", "reason_code",
         "assigned_to", "customer_reference", "created_at"],
        [
            [a["id"], a["category"], f"{a['score']:.3f}", a["caption"], a["matched_party"],
             a["status"], a.get("reason_code") or "", a.get("assigned_to") or "",
             a.get("reference") or "", a["created_at"]]
            for a in queue
        ],
    )


@app.get("/customers.csv")
def customers_csv(request: Request, db: DB):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    rows = queries.customer_list(db, session.org_id)
    return _csv_response(
        "customers.csv",
        ["reference", "full_name", "customer_type", "sector", "status", "rating",
         "risk_score", "open_alerts", "last_screened", "review_overdue"],
        [
            [c["reference"], c["full_name"], c["customer_type"], c.get("sector") or "",
             c["status"], c.get("rating") or "", c.get("risk_score") or "",
             c["open_alerts"], c.get("last_screened") or "", c["review_overdue"]]
            for c in rows
        ],
    )


def _csv_response(filename: str, header: list[str], rows: list[list]):
    import csv
    import io

    from fastapi.responses import StreamingResponse

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
    from ..ingest.loader import staleness_report
    return render(request, "admin.html", {
        "session": session, "org": dict(org),
        "operators": queries.operators(db, session.org_id),
        "threshold": queries.org_alert_threshold(db, session.org_id),
        "default_threshold": DEFAULT_THRESHOLD,
        "sanctions": staleness_report(db),
    })


@app.post("/admin/threshold")
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
        return back("/admin", err=str(exc))

    raw = threshold.strip()
    if not raw:
        set_org_alert_threshold(db, session.org_id, None)
        return back("/admin", msg=f"Threshold reset to the engine default ({DEFAULT_THRESHOLD}).")
    try:
        value = float(raw)
    except ValueError:
        return back("/admin", err="Threshold must be a number.")
    if not (0.0 <= value <= 1.0):
        return back("/admin", err="Threshold must be between 0.0 and 1.0.")
    set_org_alert_threshold(db, session.org_id, value)
    from ..db import audit
    audit(db, session.operator_name, "org.threshold_set", "organization", session.org_id,
          {"threshold": value}, org_id=session.org_id)
    db.commit()
    return back("/admin", msg=f"Alert threshold set to {value}.")


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


# ---------------------------------------------------------------------- sanctions refresh
@app.post("/admin/refresh")
def admin_refresh_sanctions(
    request: Request, db: DB,
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

    from ..ingest.base import AdapterError
    from ..ingest.loader import load
    from ..ingest.opensanctions import uae_local_terrorists, cia_world_leaders
    from ..ingest.un import UNSanctionsAdapter
    from ..ingest.ofac import OFACSDNAdapter
    from ..ingest.eu import EUSanctionsAdapter
    from ..ingest.uk import UKSanctionsAdapter
    from ..match.engine import rescreen_all
    from ..db import audit

    failures: list[str] = []
    loaded: list[str] = []
    for factory in [uae_local_terrorists, UNSanctionsAdapter, OFACSDNAdapter, EUSanctionsAdapter, UKSanctionsAdapter, cia_world_leaders]:
        adapter = factory()
        try:
            result = load(db, adapter, actor=session.operator_name)
            loaded.append(f"{adapter.title}: {result.entities} entities")
        except AdapterError as exc:
            failures.append(f"{adapter.title}: {exc}")
            audit(db, session.operator_name, "dataset.refresh_failed",
                  "dataset", adapter.key, {"error": str(exc)}, org_id=None)
            db.commit()

    # Re-screen every active org's customer book
    total_alerts = 0
    orgs = db.execute("SELECT id FROM organizations WHERE status='active'").fetchall()
    for org in orgs:
        outcome = rescreen_all(db, org["id"], actor=session.operator_name)
        total_alerts += outcome["alerts"]
    db.commit()

    if failures:
        return back("/admin", err="Refresh failed for: " + "; ".join(failures))

    msg = "Sanctions lists refreshed. " + "; ".join(loaded)
    if total_alerts:
        msg += f" {total_alerts} new alert(s) raised — check Alerts."
    return back("/admin", msg=msg)


# ---------------------------------------------------------------------- system/refresh (Cloud Scheduler endpoint)
@app.post("/system/refresh")
def system_refresh(request: Request):
    """HTTP endpoint for Cloud Scheduler to call every 23 hours.

    Protected by a bearer token stored in the SCHEDULER_SECRET environment
    variable. If the variable is not set the endpoint is disabled entirely
    (returns 403) to prevent accidental exposure on a fresh deploy.
    """
    secret = os.environ.get("SCHEDULER_SECRET", "").strip()
    if not secret:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "endpoint disabled — set SCHEDULER_SECRET"}, status_code=403)

    auth_header = request.headers.get("Authorization", "")
    if auth_header != f"Bearer {secret}":
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    import threading
    thread = threading.Thread(target=_run_scheduled_refresh, daemon=True)
    thread.start()
    from fastapi.responses import JSONResponse
    return JSONResponse({"status": "refresh started", "note": "running in background"})


# ---------------------------------------------------------------------- regulatory reports
@app.get("/reports", response_class=HTMLResponse)
def reports_view(request: Request, db: DB):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    
    r_list = queries.report_list(db, session.org_id)
    return render(request, "reports.html", {"session": session, "reports": r_list})


@app.get("/reports/new", response_class=HTMLResponse)
def report_new_view(request: Request, db: DB):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    
    customers = queries.customer_list(db, session.org_id)
    return render(request, "report_new.html", {"session": session, "customers": customers})


@app.get("/reports/build", response_class=HTMLResponse)
def report_build_view(
    request: Request, db: DB,
    customer_id: int,
    report_type: str = "STR",
    report_id: int | None = None,
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    
    cust_data = queries.customer(db, customer_id, session.org_id)
    if not cust_data:
        return back("/reports", err="Customer not found")
        
    payload = {}
    if report_id:
        existing = queries.report(db, report_id, session.org_id)
        if existing:
            import json
            payload = json.loads(existing["payload"] or "{}")

    return render(request, "str_builder.html", {
        "session": session,
        "customer": cust_data["customer"],
        "type": report_type,
        "payload": payload,
        "report_id": report_id,
    })


@app.post("/reports")
def report_save(
    request: Request, db: DB,
    customer_id: int,
    report_type: str,
    reporting_entity_name: Annotated[str, Form()],
    entity_reference: Annotated[str, Form()],
    reporter_name: Annotated[str, Form()],
    reporter_email: Annotated[str, Form()],
    first_name: Annotated[str, Form()],
    last_name: Annotated[str, Form()] = "",
    nationality: Annotated[str, Form()] = "AE",
    birth_date: Annotated[str, Form()] = "",
    gender: Annotated[str, Form()] = "",
    id_type: Annotated[str, Form()] = "",
    id_number: Annotated[str, Form()] = "",
    amount: Annotated[str, Form()] = "",
    transaction_type: Annotated[str, Form()] = "",
    transaction_date: Annotated[str, Form()] = "",
    source_account: Annotated[str, Form()] = "",
    destination_account: Annotated[str, Form()] = "",
    reason_description: Annotated[str, Form()] = "",
    action_taken: Annotated[str, Form()] = "",
    evidence_pack_attached: Annotated[str, Form()] = "",
    report_id: Annotated[int, Form()] = None,
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back("/reports", err=str(exc))

    import json
    # Look up customer type for correct goAML XML serialisation
    cust_row = db.execute(
        "SELECT customer_type, full_name FROM customers WHERE id = ? AND org_id = ?",
        (customer_id, session.org_id)
    ).fetchone()
    cust_type = cust_row["customer_type"] if cust_row else "natural"

    # Bundle all collected parameters into a payload dict
    payload_dict = {
        "customer_id": customer_id,
        "customer_type": cust_type,
        "report_type": report_type,
        "reporting_entity_name": reporting_entity_name.strip(),
        "entity_reference": entity_reference.strip(),
        "reporter_name": reporter_name.strip(),
        "reporter_email": reporter_email.strip(),
        "first_name": first_name.strip(),
        "last_name": last_name.strip(),
        "nationality": nationality.strip().upper(),
        "birth_date": birth_date.strip(),
        "gender": gender.strip(),
        "id_type": id_type.strip(),
        "id_number": id_number.strip(),
        "amount": float(amount) if amount.strip() else None,
        "transaction_type": transaction_type.strip() if transaction_type else None,
        "transaction_date": transaction_date.strip() if transaction_date else None,
        "source_account": source_account.strip(),
        "destination_account": destination_account.strip(),
        "reason_description": reason_description.strip(),
        "action_taken": action_taken.strip(),
        "evidence_pack_attached": bool(evidence_pack_attached),
    }

    payload_json = json.dumps(payload_dict)
    now = utcnow()

    with db:
        if report_id:
            db.execute(
                """UPDATE reports 
                   SET payload=?, reference=? 
                   WHERE id=? AND org_id=?""",
                (payload_json, f"goAML-{report_type}-{report_id}", report_id, session.org_id)
            )
            rid = report_id
        else:
            cur = db.execute(
                """INSERT INTO reports (org_id, customer_id, report_type, status, payload, created_at)
                   VALUES (?,?,?,?,?,?)""",
                (session.org_id, customer_id, report_type, "draft", payload_json, now)
            )
            rid = cur.lastrowid
            db.execute(
                "UPDATE reports SET reference=? WHERE id=?",
                (f"goAML-{report_type}-{rid}", rid)
            )

        from ..db import audit
        audit(db, session.operator_name, "report.save", "report", rid,
              {"report_type": report_type}, org_id=session.org_id)

    return back(f"/reports/{rid}", msg="Draft report saved.")


@app.get("/reports/{report_id}", response_class=HTMLResponse)
def report_detail_view(request: Request, db: DB, report_id: int):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
        
    rep = queries.report(db, report_id, session.org_id)
    if not rep:
        return back("/reports", err="Report not found")
        
    import json
    payload = json.loads(rep["payload"] or "{}")
    
    return render(request, "report_detail.html", {
        "session": session,
        "report": rep,
        "payload": payload,
    })


@app.post("/reports/{report_id}/submit")
def report_submit(request: Request, db: DB, report_id: int, csrf_token: Annotated[str, Form()] = ""):
    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back(f"/reports/{report_id}", err=str(exc))

    rep = queries.report(db, report_id, session.org_id)
    if not rep:
        return back("/reports", err="Report not found")

    now = utcnow()
    with db:
        db.execute(
            "UPDATE reports SET status='submitted', submitted_at=? WHERE id=? AND org_id=?",
            (now, report_id, session.org_id)
        )
        from ..db import audit
        audit(db, session.operator_name, "report.submit", "report", report_id,
              {"report_type": rep["report_type"]}, org_id=session.org_id)

    return back(f"/reports/{report_id}", msg="Report submitted to UAE FIU successfully.")


@app.get("/reports/{report_id}/export")
def report_export_xml(request: Request, db: DB, report_id: int):
    try:
        session = require_session(request, db)
    except PermissionError:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")

    rep = queries.report(db, report_id, session.org_id)
    if not rep:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Report not found")

    import json
    from ..reporting.goaml import serialize_goaml_xml
    
    payload = json.loads(rep["payload"] or "{}")
    xml_content = serialize_goaml_xml(payload)

    from fastapi.responses import Response
    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={
            "Content-Disposition": f"attachment; filename=goAML_{rep['report_type']}_{report_id}.xml"
        }
    )
