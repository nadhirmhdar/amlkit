"""JSON API for the native mobile app (and any other non-browser client).

`app.py` renders HTML for a browser session (cookie + CSRF synchronizer
token). A mobile client cannot hold cookies the way a browser does and has no
ambient-credential CSRF exposure in the first place, so this router uses a
bearer token instead: the *same* opaque session token `amlkit.auth` already
issues (see `auth.create_session` / `auth.resolve_session`), just carried in
an `Authorization: Bearer <token>` header rather than a cookie. That reuse is
deliberate -- session lifetime, revocation-on-password-change, and
lockout/audit behaviour all come for free instead of being reimplemented for
a second time here.

Every route below is a thin wrapper: it resolves the bearer session, calls
the exact same library function (`queries`, `cases.manager`, `cases.review`,
`match.engine`, `risk.model`) the HTML routes in `app.py` call, and returns
JSON. No screening, risk, or review logic is duplicated -- see app.py's own
module docstring for why that rule matters here.
"""

from __future__ import annotations

import dataclasses
import json
import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

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
from .deps import client_ip, get_db, require_role

router = APIRouter(prefix="/api/v1")

DB = Annotated[sqlite3.Connection, Depends(get_db)]


# --------------------------------------------------------------- auth/session
def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        token = header[7:].strip()
        return token or None
    return None


def api_session(request: Request, db: DB) -> auth.SessionInfo:
    """Resolve the caller's session from the Authorization header.

    Raises 401 rather than letting a route proceed with `None` -- same
    reasoning as `deps.require_session` for the cookie-based web app.
    """
    session = auth.resolve_session(db, _bearer_token(request))
    if session is None:
        raise HTTPException(status_code=401, detail="Missing or expired token.")
    return session


Session = Annotated[auth.SessionInfo, Depends(api_session)]


def _require_mlro(session: auth.SessionInfo) -> None:
    try:
        require_role(session, "mlro")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _operator_json(session: auth.SessionInfo) -> dict[str, Any]:
    return {
        "operator_id": session.operator_id,
        "org_id": session.org_id,
        "name": session.operator_name,
        "role": session.operator_role,
        "email": session.email,
    }


# ---------------------------------------------------------------------- auth
class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/auth/login")
def api_login(body: LoginRequest, db: DB):
    try:
        token, info = auth.login(db, body.email, body.password)
    except auth.AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return {"token": token, "operator": _operator_json(info)}


@router.post("/auth/logout", status_code=204)
def api_logout(request: Request, db: DB, session: Session):
    token = _bearer_token(request)
    if token:
        auth.logout(db, token, session)
    return Response(status_code=204)


@router.get("/auth/me")
def api_me(session: Session):
    return {"operator": _operator_json(session)}


class RegisterOrgRequest(BaseModel):
    org_name: str
    name: str
    email: str
    password: str


@router.post("/auth/register-organization")
def api_register_organization(body: RegisterOrgRequest, db: DB):
    if len(body.password) < 10:
        raise HTTPException(status_code=400, detail="Password must be at least 10 characters.")
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", body.org_name.strip().lower()).strip("-") or "org"
    now = utcnow()
    try:
        cur = db.execute(
            "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
            (body.org_name.strip(), slug, "active", now),
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=400, detail="An organization with a similar name already exists."
        ) from exc
    org_id = cur.lastrowid
    cur2 = db.execute(
        """INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at)
           VALUES (?,?,?,?,?,1,?)""",
        (org_id, body.name.strip(), body.email.strip().lower(),
         auth.hash_password(body.password), "mlro", now),
    )
    db.commit()
    from ..db import audit

    audit(db, body.name.strip(), "organization.register", "organization", org_id,
          {"org_name": body.org_name.strip()}, org_id=org_id)
    db.commit()
    token, info = auth.login(db, body.email.strip().lower(), body.password)
    return {"token": token, "operator": _operator_json(info)}


class SetupRequest(BaseModel):
    token: str
    name: str
    email: str
    password: str


@router.get("/auth/setup")
def api_setup_check(token: str, db: DB):
    from .app import _valid_setup_token

    row = _valid_setup_token(db, token)
    if row is None:
        raise HTTPException(status_code=400, detail="This setup link is invalid, expired, or already used.")
    org = db.execute("SELECT name FROM organizations WHERE id=?", (row["org_id"],)).fetchone()
    return {"valid": True, "org_name": org["name"]}


@router.post("/auth/setup")
def api_setup_submit(body: SetupRequest, db: DB):
    from .app import _valid_setup_token

    row = _valid_setup_token(db, body.token)
    if row is None:
        raise HTTPException(status_code=400, detail="This setup link is invalid, expired, or already used.")
    if len(body.password) < 10:
        raise HTTPException(status_code=400, detail="Password must be at least 10 characters.")

    now = utcnow()
    cur = db.execute(
        """INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at)
           VALUES (?,?,?,?,?,1,?)""",
        (row["org_id"], body.name.strip(), body.email.strip().lower(),
         auth.hash_password(body.password), "mlro", now),
    )
    operator_id = cur.lastrowid
    db.execute("UPDATE setup_tokens SET used_at=? WHERE id=?", (now, row["id"]))
    db.commit()
    from ..db import audit

    audit(db, body.name.strip(), "operator.setup_claimed", "operator", operator_id,
          {"email": body.email.strip().lower()}, org_id=row["org_id"])
    db.commit()
    token, info = auth.login(db, body.email.strip().lower(), body.password)
    return {"token": token, "operator": _operator_json(info)}


# ----------------------------------------------------------------- dashboard
@router.get("/dashboard")
def api_dashboard(db: DB, session: Session):
    return queries.dashboard(db, session.org_id)


@router.get("/datasets")
def api_datasets(db: DB, session: Session):
    return {"datasets": queries.datasets(db)}


@router.get("/reason-codes")
def api_reason_codes(session: Session):
    return {"reason_codes": REASON_CODES, "single_operator_mode": single_operator_mode()}


# --------------------------------------------------------------------- screen
class ScreenRequest(BaseModel):
    name: str
    country: str = ""
    birth_date: str = ""
    gender: str = ""


def _hit_json(db: sqlite3.Connection, h) -> dict[str, Any]:
    return {
        "score": h.score, "caption": h.caption, "dataset": h.dataset,
        "schema_type": h.schema_type, "matched_name": h.matched_name,
        "category": ("proliferation" if h.is_proliferation
                     else "terrorism" if h.is_terrorism
                     else "sanction" if h.is_sanction else "other"),
        "obligation": h.obligation, "programs": h.programs,
        "detail": h.detail, "entity_id": h.entity_id,
        "aliases": queries.entity_names(db, h.entity_id),
    }


@router.post("/screen")
def api_screen(body: ScreenRequest, db: DB, session: Session):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Enter a name to screen.")
    result = screen(
        db, name, org_id=session.org_id, trigger="adhoc",
        threshold=queries.org_alert_threshold(db, session.org_id) or DEFAULT_THRESHOLD,
        country=body.country.strip() or None,
        birth_date=body.birth_date.strip() or None,
        gender=body.gender.strip() or None,
        actor=session.operator_name,
    )
    return {
        "query": result.query, "clear": result.clear, "candidates": result.candidates,
        "threshold": result.threshold, "low_confidence": len(name.split()) < 2,
        "hits": [_hit_json(db, h) for h in result.hits],
    }


# ----------------------------------------------------------------- customers
@router.get("/customers")
def api_customers(db: DB, session: Session):
    return {"customers": queries.customer_list(db, session.org_id)}


class UboIn(BaseModel):
    person_name: str
    ownership_pct: float | None = None
    control_type: str = "ownership"


class CustomerCreateRequest(BaseModel):
    reference: str
    full_name: str
    customer_type: str = "natural"
    name_arabic: str = ""
    nationality: str = ""
    birth_date: str = ""
    gender: str = ""
    sector: str = "other"
    delivery_channel: str = "face_to_face"
    cash_level: str = "non_cash"
    jurisdiction_tier: str = "standard"
    structure: str = "natural_person"
    ubos: list[UboIn] = []


@router.post("/customers")
def api_customer_create(body: CustomerCreateRequest, db: DB, session: Session):
    ubos = [
        {"person_name": u.person_name.strip(), "ownership_pct": u.ownership_pct,
         "control_type": u.control_type or "ownership"}
        for u in body.ubos if u.person_name.strip()
    ]
    try:
        result = onboard(
            db, org_id=session.org_id, reference=body.reference.strip(),
            full_name=body.full_name.strip(), customer_type=body.customer_type,
            name_arabic=body.name_arabic.strip() or None,
            nationality=body.nationality.strip() or None,
            birth_date=body.birth_date.strip() or None,
            gender=body.gender.strip() or None, sector=body.sector,
            delivery_channel=body.delivery_channel, cash_level=body.cash_level,
            jurisdiction_tier=body.jurisdiction_tier, structure=body.structure,
            ubos=ubos, actor=session.operator_name,
            threshold=queries.org_alert_threshold(db, session.org_id) or DEFAULT_THRESHOLD,
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=400, detail=f"Reference {body.reference!r} already exists."
        ) from exc
    return {
        "customer_id": result.customer_id, "reference": result.reference,
        "blocked": result.blocked, "risk_rating": result.risk.rating,
        "risk_score": result.risk.score, "requires_edd": result.risk.requires_edd,
    }


@router.post("/customers/scan-passport")
def api_scan_passport(session: Session, passport_file: UploadFile):
    import io

    from ..cases.ocr import extract_passport_data

    try:
        content = passport_file.file.read()
        return extract_passport_data(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/customers/{customer_id}")
def api_customer_detail(customer_id: int, db: DB, session: Session):
    data = queries.customer(db, customer_id, session.org_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found.")
    for a in data["alerts"]:
        a["reviews"] = review_history(db, a["id"], session.org_id)
    return data


@router.get("/customers/{customer_id}/evidence")
def api_customer_evidence(customer_id: int, db: DB, session: Session):
    """Same case-file data the printable evidence pack is built from.

    The web app renders this into an HTML page; the native app renders its
    own evidence-pack screen (and PDF export) from this JSON directly rather
    than the app fetching and parsing server-rendered HTML.
    """
    data = queries.customer(db, customer_id, session.org_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found.")
    for a in data["alerts"]:
        a["reviews"] = review_history(db, a["id"], session.org_id)
    return data | {"generated_at": utcnow()}


@router.post("/customers/{customer_id}/close")
def api_customer_close(customer_id: int, db: DB, session: Session):
    until = close_relationship(db, customer_id, org_id=session.org_id, actor=session.operator_name)
    return {"retention_until": until}


class UboAddRequest(BaseModel):
    person_name: str
    ownership_pct: float | None = None
    control_type: str = "ownership"


@router.post("/customers/{customer_id}/ubo")
def api_customer_add_ubo(customer_id: int, body: UboAddRequest, db: DB, session: Session):
    ubo_id = add_ubo(
        db, customer_id, org_id=session.org_id, person_name=body.person_name.strip(),
        ownership_pct=body.ownership_pct, control_type=body.control_type,
        actor=session.operator_name,
    )
    result = screen(
        db, body.person_name.strip(), org_id=session.org_id, trigger="onboarding",
        customer_id=customer_id, ubo_id=ubo_id, actor=session.operator_name,
        threshold=queries.org_alert_threshold(db, session.org_id) or DEFAULT_THRESHOLD,
    )
    return {"ubo_id": ubo_id, "hits": [_hit_json(db, h) for h in result.hits]}


class NoteRequest(BaseModel):
    body: str


@router.post("/customers/{customer_id}/notes")
def api_customer_add_note(customer_id: int, body: NoteRequest, db: DB, session: Session):
    try:
        note_id = add_case_note(db, customer_id, session.org_id,
                                author=session.operator_name, body=body.body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"note_id": note_id}


class TransactionRequest(BaseModel):
    direction: str
    method: str
    amount: float
    currency: str = "AED"
    amount_aed: float | None = None
    counterparty_name: str = ""
    counterparty_country: str = ""
    occurred_at: str = ""


@router.post("/customers/{customer_id}/transactions")
def api_customer_add_transaction(customer_id: int, body: TransactionRequest, db: DB, session: Session):
    try:
        transaction_id, triggered = record_transaction(
            db, customer_id, session.org_id,
            direction=body.direction, method=body.method, amount=body.amount,
            currency=body.currency, amount_aed=body.amount_aed,
            counterparty_name=body.counterparty_name.strip() or None,
            counterparty_country=body.counterparty_country.strip() or None,
            occurred_at=(body.occurred_at.strip() + "T00:00:00+00:00") if body.occurred_at.strip() else None,
            actor=session.operator_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "transaction_id": transaction_id,
        "triggered_rules": [{"rule_key": r.rule_key, "severity": r.severity} for r in triggered],
    }


class TxnAlertDispositionRequest(BaseModel):
    status: str
    note: str = ""


@router.post("/transaction-alerts/{alert_id}/disposition")
def api_txn_alert_disposition(alert_id: int, body: TxnAlertDispositionRequest, db: DB, session: Session):
    try:
        disposition_transaction_alert(
            db, alert_id, session.org_id, status=body.status, note=body.note,
            actor=session.operator_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


class SignatureRequest(BaseModel):
    purpose: str
    statement: str
    signer_name: str
    signer_role: str = "customer"


@router.post("/customers/{customer_id}/signatures")
def api_customer_add_signature(customer_id: int, body: SignatureRequest, request: Request, db: DB, session: Session):
    try:
        signature_id = record_signature(
            db, customer_id, session.org_id,
            purpose=body.purpose, statement=body.statement, signer_name=body.signer_name,
            signer_role=body.signer_role, ip_address=client_ip(request),
            user_agent=request.headers.get("User-Agent"), actor=session.operator_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"signature_id": signature_id}


# --------------------------------------------------------------------- alerts
@router.get("/alerts")
def api_alerts(db: DB, session: Session, status: str = "open"):
    queue = queries.alert_queue(db, session.org_id, status=None if status == "all" else status)
    for a in queue:
        a["reviews"] = review_history(db, a["id"], session.org_id)
    return {"alerts": queue}


class AlertDispositionRequest(BaseModel):
    status: str
    reason_code: str = ""
    narrative: str = ""


@router.post("/alerts/{alert_id}/disposition")
def api_alert_disposition(alert_id: int, body: AlertDispositionRequest, db: DB, session: Session):
    try:
        outcome = propose_disposition(
            db, alert_id, org_id=session.org_id, status=body.status,
            reason_code=body.reason_code, operator=session.operator_name,
            narrative=body.narrative,
        )
    except ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return dataclasses.asdict(outcome)


class AlertConfirmRequest(BaseModel):
    agree: bool = True
    narrative: str = ""


@router.post("/alerts/{alert_id}/confirm")
def api_alert_confirm(alert_id: int, body: AlertConfirmRequest, db: DB, session: Session):
    try:
        outcome = confirm_disposition(
            db, alert_id, org_id=session.org_id, operator=session.operator_name,
            agree=body.agree, narrative=body.narrative,
        )
    except ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return dataclasses.asdict(outcome)


class AlertAssignRequest(BaseModel):
    operator: str | None = None


@router.post("/alerts/{alert_id}/assign")
def api_alert_assign(alert_id: int, body: AlertAssignRequest, db: DB, session: Session):
    try:
        assign_alert(db, alert_id, session.org_id,
                    operator=(body.operator or "").strip() or None, actor=session.operator_name)
    except ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@router.get("/alerts.csv")
def api_alerts_csv(db: DB, session: Session, status: str = "all"):
    queue = queries.alert_queue(db, session.org_id, status=None if status == "all" else status)
    return _csv(
        "alerts.csv",
        ["id", "category", "score", "caption", "matched_party", "status", "reason_code",
         "assigned_to", "customer_reference", "created_at"],
        [[a["id"], a["category"], f"{a['score']:.3f}", a["caption"], a["matched_party"],
          a["status"], a.get("reason_code") or "", a.get("assigned_to") or "",
          a.get("reference") or "", a["created_at"]] for a in queue],
    )


@router.get("/customers.csv")
def api_customers_csv(db: DB, session: Session):
    rows = queries.customer_list(db, session.org_id)
    return _csv(
        "customers.csv",
        ["reference", "full_name", "customer_type", "sector", "status", "rating",
         "risk_score", "open_alerts", "last_screened", "review_overdue"],
        [[c["reference"], c["full_name"], c["customer_type"], c.get("sector") or "",
          c["status"], c.get("rating") or "", c.get("risk_score") or "",
          c["open_alerts"], c.get("last_screened") or "", c["review_overdue"]] for c in rows],
    )


def _csv(filename: str, header: list[str], rows: list[list]) -> Response:
    import csv
    import io

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    return Response(
        content=buf.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------- audit
@router.get("/audit")
def api_audit(db: DB, session: Session):
    return {"entries": queries.audit_trail(db, session.org_id, limit=300)}


# ---------------------------------------------------------------------- admin
@router.get("/admin")
def api_admin(db: DB, session: Session):
    _require_mlro(session)
    org = db.execute("SELECT name, slug FROM organizations WHERE id=?", (session.org_id,)).fetchone()
    from ..ingest.loader import staleness_report

    return {
        "org": dict(org), "operators": queries.operators(db, session.org_id),
        "threshold": queries.org_alert_threshold(db, session.org_id),
        "default_threshold": DEFAULT_THRESHOLD, "sanctions": staleness_report(db),
    }


class ThresholdRequest(BaseModel):
    threshold: float | None = None


@router.post("/admin/threshold")
def api_admin_set_threshold(body: ThresholdRequest, db: DB, session: Session):
    _require_mlro(session)
    if body.threshold is None:
        set_org_alert_threshold(db, session.org_id, None)
        return {"threshold": None}
    if not (0.0 <= body.threshold <= 1.0):
        raise HTTPException(status_code=400, detail="Threshold must be between 0.0 and 1.0.")
    set_org_alert_threshold(db, session.org_id, body.threshold)
    from ..db import audit

    audit(db, session.operator_name, "org.threshold_set", "organization", session.org_id,
          {"threshold": body.threshold}, org_id=session.org_id)
    db.commit()
    return {"threshold": body.threshold}


class PasswordResetRequest(BaseModel):
    new_password: str


@router.post("/admin/operators/{operator_id}/reset-password")
def api_admin_reset_password(operator_id: int, body: PasswordResetRequest, db: DB, session: Session):
    _require_mlro(session)
    row = db.execute(
        "SELECT id FROM operators WHERE id=? AND org_id=?", (operator_id, session.org_id)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Operator not found.")
    if len(body.new_password) < 10:
        raise HTTPException(status_code=400, detail="Password must be at least 10 characters.")
    auth.set_password(db, operator_id, body.new_password)
    from ..db import audit

    audit(db, session.operator_name, "operator.password_reset", "operator", operator_id,
          None, org_id=session.org_id)
    db.commit()
    return {"ok": True}


class OperatorCreateRequest(BaseModel):
    name: str
    email: str
    password: str
    role: str = "officer"


@router.post("/admin/operators")
def api_admin_create_operator(body: OperatorCreateRequest, db: DB, session: Session):
    _require_mlro(session)
    if len(body.password) < 10:
        raise HTTPException(status_code=400, detail="Password must be at least 10 characters.")
    try:
        cur = db.execute(
            """INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at)
               VALUES (?,?,?,?,?,1,?)""",
            (session.org_id, body.name.strip(), body.email.strip().lower(),
             auth.hash_password(body.password), body.role, utcnow()),
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=400, detail="An operator with that name or email already exists."
        ) from exc
    from ..db import audit

    audit(db, session.operator_name, "operator.create", "operator", cur.lastrowid,
          {"email": body.email.strip().lower(), "role": body.role}, org_id=session.org_id)
    db.commit()
    return {"operator_id": cur.lastrowid}


@router.post("/admin/operators/{operator_id}/deactivate")
def api_admin_deactivate_operator(operator_id: int, db: DB, session: Session):
    _require_mlro(session)
    row = db.execute(
        "SELECT id FROM operators WHERE id=? AND org_id=?", (operator_id, session.org_id)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Operator not found.")
    db.execute("UPDATE operators SET is_active=0 WHERE id=?", (operator_id,))
    auth.revoke_sessions_for(db, operator_id)
    from ..db import audit

    audit(db, session.operator_name, "operator.deactivate", "operator", operator_id,
          None, org_id=session.org_id)
    db.commit()
    return {"ok": True}


@router.post("/admin/refresh")
def api_admin_refresh(db: DB, session: Session):
    _require_mlro(session)
    from .app import run_sanctions_refresh

    result = run_sanctions_refresh(db, actor=session.operator_name)
    if result["failures"]:
        raise HTTPException(status_code=502, detail="Refresh failed for: " + "; ".join(result["failures"]))
    return result


# -------------------------------------------------------------------- reports
@router.get("/reports")
def api_reports(db: DB, session: Session):
    return {"reports": queries.report_list(db, session.org_id)}


@router.get("/reports/{report_id}")
def api_report_detail(report_id: int, db: DB, session: Session):
    rep = queries.report(db, report_id, session.org_id)
    if not rep:
        raise HTTPException(status_code=404, detail="Report not found.")
    return rep | {"payload": json.loads(rep["payload"] or "{}")}


class ReportSaveRequest(BaseModel):
    customer_id: int
    report_type: str
    reporting_entity_name: str
    entity_reference: str
    reporter_name: str
    reporter_email: str
    first_name: str
    last_name: str = ""
    nationality: str = "AE"
    birth_date: str = ""
    gender: str = ""
    id_type: str = ""
    id_number: str = ""
    amount: float | None = None
    transaction_type: str = ""
    transaction_date: str = ""
    source_account: str = ""
    destination_account: str = ""
    reason_description: str = ""
    action_taken: str = ""
    evidence_pack_attached: bool = False
    report_id: int | None = None


@router.post("/reports")
def api_report_save(body: ReportSaveRequest, db: DB, session: Session):
    cust_row = db.execute(
        "SELECT customer_type FROM customers WHERE id=? AND org_id=?",
        (body.customer_id, session.org_id),
    ).fetchone()
    if cust_row is None:
        raise HTTPException(status_code=404, detail="Customer not found.")

    payload_dict = {
        "customer_id": body.customer_id, "customer_type": cust_row["customer_type"],
        "report_type": body.report_type,
        "reporting_entity_name": body.reporting_entity_name.strip(),
        "entity_reference": body.entity_reference.strip(),
        "reporter_name": body.reporter_name.strip(), "reporter_email": body.reporter_email.strip(),
        "first_name": body.first_name.strip(), "last_name": body.last_name.strip(),
        "nationality": body.nationality.strip().upper(), "birth_date": body.birth_date.strip(),
        "gender": body.gender.strip(), "id_type": body.id_type.strip(),
        "id_number": body.id_number.strip(), "amount": body.amount,
        "transaction_type": body.transaction_type.strip() or None,
        "transaction_date": body.transaction_date.strip() or None,
        "source_account": body.source_account.strip(),
        "destination_account": body.destination_account.strip(),
        "reason_description": body.reason_description.strip(),
        "action_taken": body.action_taken.strip(),
        "evidence_pack_attached": body.evidence_pack_attached,
    }
    payload_json = json.dumps(payload_dict)
    now = utcnow()
    from ..db import audit

    with db:
        if body.report_id:
            existing = queries.report(db, body.report_id, session.org_id)
            if not existing:
                raise HTTPException(status_code=404, detail="Report not found.")
            db.execute(
                "UPDATE reports SET payload=?, reference=? WHERE id=? AND org_id=?",
                (payload_json, f"goAML-{body.report_type}-{body.report_id}",
                 body.report_id, session.org_id),
            )
            rid = body.report_id
        else:
            cur = db.execute(
                """INSERT INTO reports (org_id, customer_id, report_type, status, payload, created_at)
                   VALUES (?,?,?,?,?,?)""",
                (session.org_id, body.customer_id, body.report_type, "draft", payload_json, now),
            )
            rid = cur.lastrowid
            db.execute("UPDATE reports SET reference=? WHERE id=?", (f"goAML-{body.report_type}-{rid}", rid))
        audit(db, session.operator_name, "report.save", "report", rid,
              {"report_type": body.report_type}, org_id=session.org_id)
    return {"report_id": rid}


@router.post("/reports/{report_id}/submit")
def api_report_submit(report_id: int, db: DB, session: Session):
    rep = queries.report(db, report_id, session.org_id)
    if not rep:
        raise HTTPException(status_code=404, detail="Report not found.")
    now = utcnow()
    from ..db import audit

    with db:
        db.execute(
            "UPDATE reports SET status='submitted', submitted_at=? WHERE id=? AND org_id=?",
            (now, report_id, session.org_id),
        )
        audit(db, session.operator_name, "report.submit", "report", report_id,
              {"report_type": rep["report_type"]}, org_id=session.org_id)
    return {"ok": True}


@router.get("/reports/{report_id}/export")
def api_report_export(report_id: int, db: DB, session: Session):
    rep = queries.report(db, report_id, session.org_id)
    if not rep:
        raise HTTPException(status_code=404, detail="Report not found.")
    from ..reporting.goaml import GoAMLValidationError, serialize_goaml_xml

    payload = json.loads(rep["payload"] or "{}")
    try:
        xml_content = serialize_goaml_xml(payload)
    except GoAMLValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=xml_content, media_type="application/xml",
        headers={"Content-Disposition": f"attachment; filename=goAML_{rep['report_type']}_{report_id}.xml"},
    )
