"""FastAPI application.

Routes are thin: they collect form input, call the existing engine functions,
and render. All screening, risk and review logic lives in `amlkit.match`,
`amlkit.cases` and `amlkit.risk` — duplicating any of it here would create a
second implementation that tests do not cover.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import queries
from ..cases.manager import add_ubo, close_relationship, onboard
from ..cases.review import (
    REASON_CODES,
    ReviewError,
    confirm_disposition,
    propose_disposition,
    review_history,
    single_operator_mode,
)
from ..match.engine import screen
from ..names.arabic import has_arabic_script
from ..risk.model import ruleset
from .deps import (
    OPERATOR_COOKIE,
    current_operator,
    ensure_operator,
    get_db,
    require_operator,
    startup_warning,
)

WEB = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="amlkit", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")
templates = Jinja2Templates(directory=str(WEB / "templates"))
templates.env.globals["has_arabic"] = has_arabic_script

DB = Annotated[sqlite3.Connection, Depends(get_db)]


def render(request: Request, name: str, ctx: dict) -> HTMLResponse:
    """Render with the context every page needs."""
    ctx.setdefault("operator", current_operator(request))
    ctx.setdefault("security_warning", startup_warning())
    ctx.setdefault("single_operator", single_operator_mode())
    ctx.setdefault("msg", request.query_params.get("msg"))
    ctx.setdefault("err", request.query_params.get("err"))
    # Starlette >= 0.29 takes the request first; the older
    # TemplateResponse(name, context) form silently misreads the arguments.
    return templates.TemplateResponse(request, name, ctx)


def back(url: str, msg: str = "", err: str = "") -> RedirectResponse:
    from urllib.parse import quote

    sep = "&" if "?" in url else "?"
    if msg:
        url = f"{url}{sep}msg={quote(msg)}"
    elif err:
        url = f"{url}{sep}err={quote(err)}"
    return RedirectResponse(url, status_code=303)


# ------------------------------------------------------------------ dashboard
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: DB):
    return render(request, "dashboard.html", {
        "d": queries.dashboard(db),
        "datasets": queries.datasets(db),
    })


# ------------------------------------------------------------------- operator
@app.post("/operator")
def set_operator(request: Request, db: DB, name: Annotated[str, Form()],
                 role: Annotated[str, Form()] = "officer"):
    try:
        canonical = ensure_operator(db, name, role)
    except ValueError as exc:
        return back("/", err=str(exc))
    resp = back(request.headers.get("referer", "/"), msg=f"Acting as {canonical}")
    # Session cookie: expires when the browser closes, so an unattended machine
    # does not stay attributable to whoever last used it.
    resp.set_cookie(OPERATOR_COOKIE, canonical, httponly=True, samesite="strict")
    return resp


# --------------------------------------------------------------------- screen
@app.get("/screen", response_class=HTMLResponse)
def screen_form(request: Request, db: DB):
    return render(request, "screen.html", {"result": None, "query": ""})


@app.post("/screen", response_class=HTMLResponse)
def screen_run(
    request: Request, db: DB,
    name: Annotated[str, Form()],
    country: Annotated[str, Form()] = "",
    birth_date: Annotated[str, Form()] = "",
    gender: Annotated[str, Form()] = "",
):
    name = name.strip()
    if not name:
        return render(request, "screen.html",
                      {"result": None, "query": "", "err": "Enter a name to screen."})
    try:
        operator = require_operator(request)
    except PermissionError as exc:
        return render(request, "screen.html",
                      {"result": None, "query": name, "err": str(exc)})

    result = screen(
        db, name, trigger="adhoc",
        country=country.strip() or None,
        birth_date=birth_date.strip() or None,
        gender=gender.strip() or None,
        actor=operator,
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
        "query": name, "result": result, "hits": hits,
        # Surfaced rather than swallowed: a one-token query is weak evidence
        # whatever it scores, and the operator should be told so.
        "low_confidence": len(name.split()) < 2,
    })


# ------------------------------------------------------------------ customers
@app.get("/customers", response_class=HTMLResponse)
def customers(request: Request, db: DB):
    return render(request, "customers.html", {"customers": queries.customer_list(db)})


@app.get("/customers/new", response_class=HTMLResponse)
def customer_new(request: Request, db: DB):
    rs = ruleset()
    return render(request, "customer_new.html", {
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
):
    try:
        operator = require_operator(request)
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
            db, reference=reference.strip(), full_name=full_name.strip(),
            customer_type=customer_type, name_arabic=name_arabic.strip() or None,
            nationality=nationality.strip() or None, birth_date=birth_date.strip() or None,
            gender=gender.strip() or None, sector=sector,
            delivery_channel=delivery_channel, cash_level=cash_level,
            jurisdiction_tier=jurisdiction_tier, structure=structure,
            ubos=ubos, actor=operator,
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
    data = queries.customer(db, customer_id)
    if data is None:
        return back("/customers", err=f"Customer {customer_id} not found.")
    return render(request, "customer.html", data | {"reason_codes": REASON_CODES})


@app.get("/customers/{customer_id}/evidence", response_class=HTMLResponse)
def evidence_pack(request: Request, db: DB, customer_id: int):
    data = queries.customer(db, customer_id)
    if data is None:
        return back("/customers", err=f"Customer {customer_id} not found.")
    for alert in data["alerts"]:
        alert["reviews"] = review_history(db, alert["id"])
    return render(request, "evidence.html", data)


@app.post("/customers/{customer_id}/close")
def customer_close(request: Request, db: DB, customer_id: int):
    try:
        operator = require_operator(request)
    except PermissionError as exc:
        return back(f"/customers/{customer_id}", err=str(exc))
    until = close_relationship(db, customer_id, actor=operator)
    return back(f"/customers/{customer_id}", msg=f"Relationship closed. Records retained until {until}.")


@app.post("/customers/{customer_id}/ubo")
def customer_add_ubo(
    request: Request, db: DB, customer_id: int,
    person_name: Annotated[str, Form()],
    ownership_pct: Annotated[str, Form()] = "",
    control_type: Annotated[str, Form()] = "ownership",
):
    try:
        operator = require_operator(request)
    except PermissionError as exc:
        return back(f"/customers/{customer_id}", err=str(exc))
    try:
        pct = float(ownership_pct) if ownership_pct.strip() else None
    except ValueError:
        pct = None
    ubo_id = add_ubo(db, customer_id, person_name=person_name.strip(),
                     ownership_pct=pct, control_type=control_type, actor=operator)
    res = screen(db, person_name.strip(), trigger="onboarding",
                 customer_id=customer_id, ubo_id=ubo_id, actor=operator)
    note = ("Beneficial owner added. MATCH FOUND - review alerts."
            if res.hits else "Beneficial owner added and screened clear.")
    return back(f"/customers/{customer_id}", msg=note)


# --------------------------------------------------------------------- alerts
@app.get("/alerts", response_class=HTMLResponse)
def alerts(request: Request, db: DB, status: str = "open"):
    queue = queries.alert_queue(db, status=None if status == "all" else status)
    for a in queue:
        a["reviews"] = review_history(db, a["id"])
    return render(request, "alerts.html", {
        "alerts": queue, "status": status, "reason_codes": REASON_CODES,
    })


@app.post("/alerts/{alert_id}/disposition")
def alert_disposition(
    request: Request, db: DB, alert_id: int,
    status: Annotated[str, Form()],
    reason_code: Annotated[str, Form()] = "",
    narrative: Annotated[str, Form()] = "",
    back_to: Annotated[str, Form()] = "/alerts",
):
    try:
        operator = require_operator(request)
        outcome = propose_disposition(
            db, alert_id, status=status, reason_code=reason_code,
            operator=operator, narrative=narrative,
        )
    except (ReviewError, PermissionError) as exc:
        return back(back_to, err=str(exc))
    return back(back_to, msg=outcome.message)


@app.post("/alerts/{alert_id}/confirm")
def alert_confirm(
    request: Request, db: DB, alert_id: int,
    agree: Annotated[str, Form()] = "yes",
    narrative: Annotated[str, Form()] = "",
    back_to: Annotated[str, Form()] = "/alerts",
):
    try:
        operator = require_operator(request)
        outcome = confirm_disposition(
            db, alert_id, operator=operator,
            agree=(agree == "yes"), narrative=narrative,
        )
    except (ReviewError, PermissionError) as exc:
        return back(back_to, err=str(exc))
    return back(back_to, msg=outcome.message)


# ---------------------------------------------------------------------- audit
@app.get("/audit", response_class=HTMLResponse)
def audit_view(request: Request, db: DB):
    return render(request, "audit.html", {"entries": queries.audit_trail(db, limit=300)})
