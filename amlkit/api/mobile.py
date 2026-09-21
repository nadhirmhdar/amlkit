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

The Android client lives in a separate repo, nadhirmhdar/amlkit-mobile, with
its own CI and Play Console pipeline. A field added or renamed here has no
automated check that the Android DTOs (`data/dto/*.kt` there) still match --
that used to be caught by CI in a single PR when both lived in this repo (see
`amlkit-mobile`'s own history for a fix that landed exactly this way). Check
that repo by hand when changing a response shape here.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote as _urlquote

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, field_validator

from .. import auth, mail, queries, storage
from .limits import limiter, login_rate_limit_key
from ..cases.manager import (
    ADVERSE_MEDIA_BATCH_LIMIT,
    StaleDatasetsError,
    add_case_note,
    add_ubo,
    close_relationship,
    disposition_adverse_media_finding,
    disposition_transaction_alert,
    due_for_review,
    onboard,
    reassess_risk,
    record_signature,
    record_transaction,
    run_adverse_media,
    run_due_adverse_media,
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
from ..screening.adverse_media import ATTRIBUTION as GDELT_ATTRIBUTION, DEFAULT_WINDOW_MONTHS
from .csv_utils import _escape_csv_formula
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
    token = _bearer_token(request)
    session = auth.resolve_session(db, token)
    if session is None:
        raise HTTPException(status_code=401, detail="Missing or expired token.")
    # p15: an MLRO bearer token is issued locked (see _login_json) and stays
    # useless until POST /auth/mfa/verify -- the web app's require_session()
    # rule, so a stolen password alone never reaches tenant data by API either.
    if session.operator_role == "mlro" and not auth.session_mfa_verified(db, token):
        raise HTTPException(status_code=403, detail=MFA_REQUIRED)
    return session


MFA_REQUIRED = "mfa_required"


Session = Annotated[auth.SessionInfo, Depends(api_session)]


def _reassess_into_result(result: dict, db, alert_id: int, session) -> None:
    row = db.execute(
        "SELECT s.customer_id FROM alerts a JOIN screenings s ON s.id=a.screening_id"
        " WHERE a.id=? AND a.org_id=?", (alert_id, session.org_id)
    ).fetchone()
    if row and row["customer_id"]:
        assessment = reassess_risk(db, row["customer_id"], session.org_id, actor=session.operator_name)
        if assessment:
            result["risk_rating"] = assessment.rating
            result["risk_score"] = assessment.score
            result["requires_edd"] = assessment.requires_edd


def _assessment_json(assessment) -> dict[str, Any]:
    return {
        "rating": assessment.rating,
        "score": assessment.score,
        "requires_edd": assessment.requires_edd,
        "next_review": assessment.next_review,
        "ruleset_version": assessment.ruleset_version,
        "factors": assessment.factors,
    }



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


def _login_json(db, token: str, info: auth.SessionInfo) -> dict[str, Any]:
    """Session response for every token-minting route.

    For an MLRO the token comes back locked: `mfa_required` is true and the
    client must POST /auth/mfa/verify with a TOTP (or backup code) before any
    other route accepts it. `mfa_enrolled` false means the operator has not
    set up an authenticator yet, which today is done in the web app.
    """
    challenge = auth.mfa_lock_session(db, token, info.operator_id, info.operator_role)
    out: dict[str, Any] = {
        "token": token, "operator": _operator_json(info), "mfa_required": challenge is not None,
    }
    if challenge is not None:
        out["mfa_enrolled"] = challenge == "/mfa/verify"
    return out


@router.post("/auth/login")
@limiter.limit("10/minute")  # IP ceiling, mirrors web /login
@limiter.limit("3/minute", key_func=login_rate_limit_key)  # per-account, mirrors web /login
def api_login(request: Request, body: LoginRequest, db: DB):
    try:
        token, info = auth.login(db, body.email, body.password)
    except auth.AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return _login_json(db, token, info)


class MfaVerifyRequest(BaseModel):
    code: str


@router.post("/auth/mfa/verify")
def api_mfa_verify(request: Request, body: MfaVerifyRequest, db: DB):
    """Unlock a locked MLRO token with a TOTP or one unused backup code (p15).

    Deliberately not behind `Session`, which rejects locked tokens. Wrong
    codes count towards auth.MFA_MAX_FAILURES, after which the challenge is
    locked for auth.MFA_LOCKOUT and answered 429.
    """
    token = _bearer_token(request)
    row = auth.mfa_session_state(db, token)
    if row is None:
        raise HTTPException(status_code=401, detail="Missing or expired token.")
    if row["mfa_verified"]:
        return {"ok": True}
    if not auth.mfa_is_enrolled(db, row["operator_id"]):
        raise HTTPException(status_code=403, detail=(
            "Two-factor authentication is not set up for this account yet. "
            "Sign in to the web app once to enrol an authenticator."
        ))
    outcome = auth.mfa_check_code(db, row["operator_id"], body.code, stage="verify",
                                  actor=row["name"], org_id=row["org_id"])
    if outcome == "ok":
        auth.set_session_mfa_verified(db, token, True)
        return {"ok": True}
    if outcome == "locked":
        raise HTTPException(status_code=429, detail=(
            "Too many failed codes. Two-factor sign-in is locked for 15 minutes."
        ))
    raise HTTPException(status_code=401, detail="Invalid verification code.")


@router.post("/auth/logout")
def api_logout(request: Request, db: DB):
    """Returns a small JSON body (not a bare 204) so every client -- including
    Retrofit's kotlinx.serialization converter, which errors decoding a
    zero-byte body -- gets a response its JSON decoder can actually parse.

    Resolves the session itself rather than via `Session` so a locked MLRO
    token can still be revoked."""
    token = _bearer_token(request)
    session = auth.resolve_session(db, token)
    if session is None:
        raise HTTPException(status_code=401, detail="Missing or expired token.")
    auth.logout(db, token, session)
    return {"ok": True}


@router.get("/auth/me")
def api_me(session: Session):
    return {"operator": _operator_json(session)}


class RegisterOrgRequest(BaseModel):
    org_name: str
    name: str
    email: str
    password: str
    invite_code: str = ""


@router.post("/auth/register-organization")
@limiter.limit("5/minute")
def api_register_organization(request: Request, body: RegisterOrgRequest, db: DB):
    import os
    import secrets

    expected = os.environ.get("AMLKIT_REGISTRATION_INVITE_CODE", "").strip()
    if not expected or not secrets.compare_digest(body.invite_code.strip().encode(), expected.encode()):
        auth._log_auth_event(db, "register_denied", body.email.strip().lower(),
                             {"reason": "invalid_invite_code", "via": "api"})
        db.commit()
        raise HTTPException(status_code=403, detail="Registration requires a valid invite code.")

    if len(body.password) < 10:
        raise HTTPException(status_code=400, detail="Password must be at least 10 characters.")
    if not auth.looks_like_email(body.email):
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
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
    try:
        cur2 = db.execute(
            """INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at)
               VALUES (?,?,?,?,?,1,?)""",
            (org_id, body.name.strip(), body.email.strip().lower(),
             auth.hash_password(body.password), "mlro", now),
        )
    except sqlite3.IntegrityError as exc:
        # operators.email is UNIQUE across the whole app, not just this org
        # (see db.py) -- unlike the org-name collision above, this one was
        # previously uncaught and surfaced as a raw 500 with no detail,
        # which also meant an operator's SECOND registration attempt with
        # an email they'd already used silently left the just-inserted
        # organizations row behind with no operator in it. Roll that back
        # too, not just report the error.
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="An account with that email already exists. Try signing in instead.",
        ) from exc
    operator_id = cur2.lastrowid
    db.commit()
    from ..db import audit

    email = body.email.strip().lower()
    audit(db, body.name.strip(), "organization.register", "organization", org_id,
          {"org_name": body.org_name.strip()}, org_id=org_id)
    db.commit()

    # Not activated yet -- see auth.login()'s email_verified_at guard. The
    # account exists and is fully privileged (MLRO) the moment this link is
    # clicked, so it must not be usable before then.
    raw_token = auth.create_email_verify_token(db, operator_id)
    delivery = mail.send_verification_email(email, body.name.strip(), raw_token)
    # Outcome, not just the attempt -- a provider failing every send is
    # otherwise invisible; see the matching note in app.py.
    audit(db, body.name.strip(), "operator.verification_sent", "operator", operator_id,
          {"email": email, "delivery": delivery}, org_id=org_id)
    db.commit()

    response = {
        "status": "verification_required",
        "message": f"Account created. Check {email} for a verification link before signing in.",
        "email": email,
    }
    if delivery == mail.NOT_CONFIGURED:
        # No SMTP configured AT ALL -- see amlkit/mail.py. The link was
        # printed to the server console; handing it back here too keeps
        # registration usable in dev/test without mail infrastructure.
        #
        # This branch used to be `if not emailed`, which also caught "mail is
        # configured but the send failed" and handed the raw token to the
        # client in that case. The token activates a fully-privileged MLRO
        # account and email control is the thing it exists to prove, so a
        # deployment whose provider had lapsed was giving any caller an
        # account under any address they cared to type.
        response["dev_verification_token"] = raw_token
    elif delivery == mail.FAILED:
        response["status"] = "verification_send_failed"
        response["message"] = (
            f"Account created, but the verification email to {email} could not "
            "be sent. Ask your administrator to check the mail service, then "
            "request a new link."
        )
    return response


class VerifyEmailRequest(BaseModel):
    token: str


@router.post("/auth/verify-email")
def api_verify_email(body: VerifyEmailRequest, db: DB):
    operator = auth.consume_email_verify_token(db, body.token)
    if operator is None:
        raise HTTPException(
            status_code=400,
            detail="This verification link is invalid, expired, or already used.",
        )
    from ..db import audit

    audit(db, operator["name"], "operator.email_verified", "operator", operator["id"],
          {"email": operator["email"]}, org_id=operator["org_id"])
    db.commit()

    token = auth.create_session(db, operator["id"], operator["org_id"])
    # create_session() doesn't audit a "login" itself -- this route bypasses
    # auth.login() entirely (no password to re-check), so without this the
    # operator's very first session would leave no audit trail entry at all.
    audit(db, operator["name"], "operator.login", "operator", operator["id"],
          None, org_id=operator["org_id"])
    db.commit()
    org_name_row = db.execute("SELECT name FROM organizations WHERE id = ?", (operator["org_id"],)).fetchone()
    info = auth.SessionInfo(
        operator_id=operator["id"], org_id=operator["org_id"], org_name=org_name_row["name"] if org_name_row else "",
        operator_name=operator["name"], operator_role=operator["role"], email=operator["email"],
    )
    return _login_json(db, token, info)


class ResendVerificationRequest(BaseModel):
    email: str


@router.post("/auth/resend-verification")
def api_resend_verification(body: ResendVerificationRequest, db: DB):
    """Always returns the same generic message, whether or not the email
    belongs to a real, still-unverified account -- same anti-enumeration
    reasoning as auth.login()'s single error string. The actual resend (or
    lack of one) happens silently behind that constant response."""
    generic = {
        "message": "If that email has a pending registration, a new verification link has been sent.",
    }
    email = body.email.strip().lower()
    row = db.execute(
        "SELECT id, org_id, name, email_verified_at FROM operators WHERE lower(email)=?",
        (email,),
    ).fetchone()
    if row is None or row["email_verified_at"] is not None:
        return generic

    # Cooldown, not a hard limit: a resend inside the window is a silent
    # no-op since the previous link is still live anyway. Keeps this route
    # from being usable to mail-bomb an address without a rate-limiting
    # dependency or table.
    age = auth.last_email_verify_token_age_seconds(db, row["id"])
    if age is not None and age < 60:
        return generic

    raw_token = auth.create_email_verify_token(db, row["id"])
    delivery = mail.send_verification_email(email, row["name"], raw_token)
    from ..db import audit

    # The response stays generic (see `generic`) so this route cannot be used
    # to probe which addresses have accounts, which makes the audit log the
    # only place a repeatedly-failing provider shows up.
    audit(db, row["name"], "operator.verification_resent", "operator", row["id"],
          {"email": email, "delivery": delivery}, org_id=row["org_id"])
    db.commit()
    return generic


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
        # email_verified_at=now: claiming a setup link already proves control
        # of a channel an admin trusted, so there's no separate
        # email-ownership gap left to close here, unlike public
        # self-registration in api_register_organization (see
        # auth.login()'s guard).
        """INSERT INTO operators
               (org_id, name, email, password_hash, role, is_active, email_verified_at, created_at)
           VALUES (?,?,?,?,?,1,?,?)""",
        (row["org_id"], body.name.strip(), body.email.strip().lower(),
         auth.hash_password(body.password), "mlro", now, now),
    )
    operator_id = cur.lastrowid
    db.execute("UPDATE setup_tokens SET used_at=? WHERE id=?", (now, row["id"]))
    db.commit()
    from ..db import audit

    audit(db, body.name.strip(), "operator.setup_claimed", "operator", operator_id,
          {"email": body.email.strip().lower()}, org_id=row["org_id"])
    db.commit()
    token, info = auth.login(db, body.email.strip().lower(), body.password)
    return _login_json(db, token, info)


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

    @field_validator("ownership_pct")
    @classmethod
    def validate_ownership_pct(cls, v: float | None) -> float | None:
        if v is not None and not (0 <= v <= 100):
            raise ValueError(f"ownership_pct must be between 0 and 100, got {v}")
        return v


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
    # Contact fields
    email: str = ""
    phone: str = ""
    address_line1: str = ""
    address_line2: str = ""
    city: str = ""
    postal_code: str = ""
    contact_person: str = ""
    contact_phone: str = ""
    contact_email: str = ""


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
            email=body.email.strip() or None,
            phone=body.phone.strip() or None,
            address_line1=body.address_line1.strip() or None,
            address_line2=body.address_line2.strip() or None,
            city=body.city.strip() or None,
            postal_code=body.postal_code.strip() or None,
            contact_person=body.contact_person.strip() or None,
            contact_phone=body.contact_phone.strip() or None,
            contact_email=body.contact_email.strip() or None,
        )
    except StaleDatasetsError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=400, detail=f"Reference {body.reference!r} already exists."
        ) from exc
    return {
        "customer_id": result.customer_id, "reference": result.reference,
        "blocked": result.blocked, "risk_rating": result.risk.rating,
        "risk_score": result.risk.score, "requires_edd": result.risk.requires_edd,
    }


def _scan_document(content: bytes, extractor) -> dict:
    """Shared body for the passport/Emirates-ID scan routes.

    Image-quality is assessed independently of extraction -- in its own
    try/except, swallowed on failure -- so a bad photo still gets a
    diagnostic flag (e.g. "low resolution") folded into the 400 even when
    extraction itself throws outright, which is exactly the case where that
    signal is most useful to the person retaking the photo.
    """
    import io

    from ..cases.ocr import assess_image_quality

    quality = None
    try:
        quality = assess_image_quality(io.BytesIO(content))
    except Exception:
        pass

    try:
        result = extractor(io.BytesIO(content))
    except Exception as exc:
        detail = str(exc)
        if quality and quality.get("flags"):
            detail += " (image quality: " + "; ".join(quality["flags"]) + ")"
        raise HTTPException(status_code=400, detail=detail) from exc

    result["image_quality"] = quality
    return result


@router.post("/customers/scan-passport")
def api_scan_passport(session: Session, passport_file: UploadFile):
    from ..cases.ocr import extract_passport_data
    from ..validation import validate_file_mime

    content = passport_file.file.read()
    # Validate MIME type
    try:
        validate_file_mime(content, passport_file.filename or "passport.jpg")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return _scan_document(content, extract_passport_data)


@router.post("/customers/scan-emirates-id")
def api_scan_emirates_id(session: Session, emirates_id_file: UploadFile):
    from ..cases.ocr import extract_emirates_id_data
    from ..validation import validate_file_mime

    content = emirates_id_file.file.read()
    # Validate MIME type
    try:
        validate_file_mime(content, emirates_id_file.filename or "emirates_id.jpg")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return _scan_document(content, extract_emirates_id_data)


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


# -------------------------------------------------------- risk rating endpoints

class RiskFactorUpdateRequest(BaseModel):
    """Mutable risk factors. Omit any field to keep the current value."""
    jurisdiction_tier: str | None = None
    sector: str | None = None
    delivery_channel: str | None = None
    cash_level: str | None = None
    structure: str | None = None


@router.post("/customers/{customer_id}/risk")
def api_customer_reassess_risk(customer_id: int, db: DB, session: Session):
    """Trigger a risk re-assessment using the customer's current state.

    Re-derives sanctions_hit from open alerts, preserves PEP status and
    all other factors from the prior assessment. Returns the new rating.
    Useful after an MLRO dismisses an alert or marks adverse media as
    relevant, and wants to see the updated rating without waiting for the
    next scheduled rescreen.
    """
    if db.execute(
        "SELECT id FROM customers WHERE id=? AND org_id=?", (customer_id, session.org_id)
    ).fetchone() is None:
        raise HTTPException(status_code=404, detail="Customer not found.")
    assessment = reassess_risk(db, customer_id, session.org_id, actor=session.operator_name)
    if assessment is None:
        raise HTTPException(
            status_code=409,
            detail="No prior assessment found. Complete onboarding before re-assessing.",
        )
    return _assessment_json(assessment)


@router.patch("/customers/{customer_id}/risk-factors")
def api_customer_update_risk_factors(
    customer_id: int, body: RiskFactorUpdateRequest, db: DB, session: Session
):
    """Update mutable risk factors and re-assess.

    Only the fields you supply are changed; omitted fields keep their current
    value from the prior assessment. Updates that affect a column on the
    `customers` table (sector, delivery_channel, cash_level) are persisted
    there so `customer_list` reflects the change. jurisdiction_tier and
    structure have no customer-row column -- they live only in the assessment
    factors, carried forward by `reassess_risk`.
    """
    row = db.execute(
        "SELECT id FROM customers WHERE id=? AND org_id=?", (customer_id, session.org_id)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Customer not found.")

    updates: dict[str, Any] = {}
    if body.sector is not None:
        updates["sector"] = body.sector
    if body.delivery_channel is not None:
        updates["delivery_channel"] = body.delivery_channel
    if body.cash_level is not None:
        updates["is_cash_intensive"] = int(body.cash_level == "predominantly_cash")

    if updates:
        set_clause = ", ".join(f"{k}=?" for k in updates)
        db.execute(
            f"UPDATE customers SET {set_clause}, updated_at=? WHERE id=? AND org_id=?",
            (*updates.values(), utcnow(), customer_id, session.org_id),
        )
        from ..db import audit
        audit(db, session.operator_name, "customer.risk_factors_updated", "customer",
              customer_id, {k: v for k, v in body.__dict__.items() if v is not None},
              org_id=session.org_id)
        db.commit()

    assessment = reassess_risk(
        db, customer_id, session.org_id, actor=session.operator_name,
        jurisdiction_tier=body.jurisdiction_tier,
        sector=body.sector,
        delivery_channel=body.delivery_channel,
        cash_level=body.cash_level,
        structure=body.structure,
    )
    if assessment is None:
        raise HTTPException(
            status_code=409,
            detail="No prior assessment found. Complete onboarding before updating risk factors.",
        )
    return _assessment_json(assessment)


@router.get("/risk/ruleset")
def api_risk_ruleset(session: Session):
    """Return the active ruleset — version, bands, EDD triggers, factor labels.

    Lets the mobile app show the scoring criteria in context (e.g. beside each
    factor on the customer detail screen) without hardcoding them in the app.
    """
    from ..risk.model import ruleset as load_ruleset
    rs = load_ruleset()
    return {
        "version": rs["version"],
        "effective_from": rs.get("effective_from"),
        "bands": rs["bands"],
        "edd_triggers": rs.get("edd_triggers", []),
        "review_months": rs.get("review_months", {}),
        "adverse_media_months": rs.get("adverse_media_months", {}),
        "factors": {
            key: {"label": val.get("label", key)}
            for key, val in rs.get("factors", {}).items()
        },
    }


class UboAddRequest(BaseModel):
    person_name: str
    ownership_pct: float | None = None
    control_type: str = "ownership"

    @field_validator("ownership_pct")
    @classmethod
    def validate_ownership_percentage(cls, v: float | None) -> float | None:
        if v is not None and not (0 <= v <= 100):
            raise ValueError(f"ownership_pct must be between 0 and 100, got {v}")
        return v


@router.post("/customers/{customer_id}/ubo")
def api_customer_add_ubo(customer_id: int, body: UboAddRequest, db: DB, session: Session):
    try:
        ubo_id = add_ubo(
            db, customer_id, org_id=session.org_id, person_name=body.person_name.strip(),
            ownership_pct=body.ownership_pct, control_type=body.control_type,
            actor=session.operator_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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


@router.get("/customers/{customer_id}/transactions")
def api_customer_transactions(customer_id: int, db: DB, session: Session):
    """Transaction history and associated KYT alerts for one customer."""
    if db.execute(
        "SELECT 1 FROM customers WHERE id=? AND org_id=?", (customer_id, session.org_id)
    ).fetchone() is None:
        raise HTTPException(status_code=404, detail="Customer not found.")
    return {
        "transactions": queries.transactions_for_customer(db, customer_id, session.org_id),
        "transaction_alerts": queries.transaction_alert_queue(
            db, session.org_id, status=None, customer_id=customer_id
        ),
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


class AdverseMediaRunRequest(BaseModel):
    window_months: int = DEFAULT_WINDOW_MONTHS


@router.post("/customers/{customer_id}/adverse-media")
def api_customer_run_adverse_media(
    customer_id: int, body: AdverseMediaRunRequest, db: DB, session: Session
):
    """Run an adverse-media check for one customer.

    Slow by design -- the provider is rate-limited to one request every five
    seconds, and a customer with an Arabic name costs two. Clients should
    treat this as a long-running action rather than a tap that returns
    instantly.

    A provider outage comes back as HTTP 200 with `status: "unavailable"`,
    not an error status. The check WAS recorded, and a client that treated it
    as a failed request would show the operator nothing happened when in fact
    a row saying "attempted, provider down" now exists on the file.
    """
    data = queries.customer(db, customer_id, session.org_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found.")
    c = data["customer"]
    screening_id, result, new_findings = run_adverse_media(
        db,
        org_id=session.org_id,
        customer_id=customer_id,
        name=c["full_name"],
        name_arabic=c["name_arabic"],
        trigger="adhoc",
        window_months=max(1, min(int(body.window_months or DEFAULT_WINDOW_MONTHS), 120)),
        actor=session.operator_name,
    )
    return {
        "screening_id": screening_id,
        "status": result.status,
        "error": result.error,
        "articles_considered": result.articles_considered,
        "findings": len(result.findings),
        "new_findings": new_findings,
        "severity": result.severity,
        "attribution": GDELT_ATTRIBUTION,
    }


class AdverseMediaRunDueRequest(BaseModel):
    limit: int = ADVERSE_MEDIA_BATCH_LIMIT


@router.post("/adverse-media/run-due")
def api_adverse_media_run_due(
    body: AdverseMediaRunDueRequest, db: DB, session: Session
):
    """Re-check the next few customers whose adverse media is due.

    The due list itself comes back on `/dashboard` (`adverse_media_due`), so a
    client can show the queue without calling this. Slow and bounded for the
    same reason as the per-customer run: the throttle applies between each
    customer, so a batch of 5 is roughly half a minute.
    """
    outcome = run_due_adverse_media(
        db, session.org_id,
        limit=max(1, min(int(body.limit or ADVERSE_MEDIA_BATCH_LIMIT), 20)),
        actor=session.operator_name,
    )
    return outcome | {"attribution": GDELT_ATTRIBUTION}


class AdverseMediaDispositionRequest(BaseModel):
    status: str
    note: str = ""


@router.post("/adverse-media/{finding_id}/disposition")
def api_adverse_media_disposition(
    finding_id: int, body: AdverseMediaDispositionRequest, db: DB, session: Session
):
    try:
        rating = disposition_adverse_media_finding(
            db, finding_id, session.org_id, status=body.status, note=body.note,
            actor=session.operator_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Returned so the client can refresh the risk band it is showing: marking
    # a finding relevant is the one disposition here that can move a rating.
    return {"ok": True, "risk_rating": rating}


class SignatureRequest(BaseModel):
    purpose: str
    statement: str
    signer_name: str
    signer_role: str = "customer"


@router.post("/customers/{customer_id}/documents")
def api_customer_upload_document(
    customer_id: int, doc_type: str, file: UploadFile, db: DB, session: Session
):
    """Upload a supporting document (passport, trade licence, proof of address, etc.)
    and record it in the documents table. Files are stored on the local filesystem
    under data/documents/{org_id}/{customer_id}/; in a cloud deployment mount or
    replace DOCS_DIR with a GCS-backed path."""
    row = db.execute(
        "SELECT id FROM customers WHERE id=? AND org_id=?", (customer_id, session.org_id)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Customer not found.")
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename is required.")

    content = file.file.read()

    # Validate MIME type by magic bytes before accepting upload
    from ..validation import validate_file_mime
    try:
        detected_mime = validate_file_mime(content, file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    sha256 = hashlib.sha256(content).hexdigest()

    # Prevent path traversal: store only the basename, never relative segments.
    safe_name = Path(file.filename).name
    stored_path = storage.upload(content, session.org_id, customer_id, safe_name)

    now = utcnow()
    cur = db.execute(
        """INSERT INTO documents (org_id, customer_id, doc_type, filename, stored_path, sha256, uploaded_at)
           VALUES (?,?,?,?,?,?,?)""",
        (session.org_id, customer_id, doc_type, safe_name, stored_path, sha256, now),
    )
    doc_id = cur.lastrowid
    from ..db import audit

    audit(db, session.operator_name, "document.upload", "document", doc_id,
          {"doc_type": doc_type, "filename": safe_name, "sha256": sha256}, org_id=session.org_id)
    db.commit()
    return {"document_id": doc_id, "filename": safe_name, "sha256": sha256, "uploaded_at": now}


@router.get("/customers/{customer_id}/documents")
def api_customer_list_documents(customer_id: int, db: DB, session: Session):
    if db.execute(
        "SELECT id FROM customers WHERE id=? AND org_id=?", (customer_id, session.org_id)
    ).fetchone() is None:
        raise HTTPException(status_code=404, detail="Customer not found.")
    return {"documents": queries.documents_for_customer(db, customer_id, session.org_id)}


@router.get("/customers/{customer_id}/documents/{doc_id}")
def api_customer_download_document(customer_id: int, doc_id: int, db: DB, session: Session):
    row = db.execute(
        "SELECT filename, stored_path FROM documents WHERE id=? AND customer_id=? AND org_id=?",
        (doc_id, customer_id, session.org_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    try:
        content = storage.download(row["stored_path"])
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File missing from storage.")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Storage error: {exc}") from exc
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{_urlquote(row['filename'])}"},
    )


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


@router.get("/alerts/summary")
def api_alerts_summary(db: DB, session: Session):
    """Alert and adverse-media counts by status and category, for dashboard widgets.

    Avoids loading full alert payloads (entity names, score detail, aliases)
    just to display a badge count -- the queue endpoint is for the list view;
    this is for the summary card.
    """
    rows = db.execute(
        """SELECT status, COUNT(*) n FROM alerts WHERE org_id=? GROUP BY status""",
        (session.org_id,),
    ).fetchall()
    by_status = {r["status"]: r["n"] for r in rows}

    cat_rows = db.execute(
        """SELECT e.topics, e.programs, a.status
           FROM alerts a
           JOIN entities e ON e.id = a.entity_id
           WHERE a.org_id = ? AND a.status IN ('open', 'pending_review')""",
        (session.org_id,),
    ).fetchall()
    by_category: dict[str, int] = {}
    from ..screening.pf import classify_programs
    for r in cat_rows:
        topics = json.loads(r["topics"] or "[]")
        programs = json.loads(r["programs"] or "[]")
        cats = classify_programs(programs)
        if "proliferation" in cats:
            cat = "proliferation"
        elif "terrorism" in cats:
            cat = "terrorism"
        elif "sanction" in topics:
            cat = "sanction"
        elif any(t.startswith("role.pep") for t in topics):
            cat = "pep"
        else:
            cat = "other"
        by_category[cat] = by_category.get(cat, 0) + 1

    am_open = db.execute(
        "SELECT COUNT(*) n FROM adverse_media_findings WHERE org_id=? AND status='open'",
        (session.org_id,),
    ).fetchone()["n"]

    txn_open = db.execute(
        "SELECT COUNT(*) n FROM transaction_alerts WHERE org_id=? AND status='open'",
        (session.org_id,),
    ).fetchone()["n"]

    return {
        "alerts_by_status": by_status,
        "open_by_category": by_category,
        "adverse_media_open": am_open,
        "transaction_alerts_open": txn_open,
        "total_open": by_status.get("open", 0) + by_status.get("pending_review", 0),
    }


@router.get("/alerts/{alert_id}")
def api_alert_detail(alert_id: int, db: DB, session: Session):
    """Full alert record with entity details, review history, and customer context."""
    # Use the shared queue function (which handles all enrichment) and filter
    # to this specific id -- avoids duplicating the enrichment logic here.
    alerts = queries.alert_queue(db, session.org_id, status=None, alert_id=alert_id)
    if not alerts:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found.")
    match = alerts[0]
    match["reviews"] = review_history(db, alert_id, session.org_id)
    return match


@router.get("/adverse-media")
def api_adverse_media_queue(db: DB, session: Session, status: str = "open"):
    """Org-wide adverse-media findings, worst and least-reviewed first."""
    findings = queries.adverse_media_queue(
        db, session.org_id, status=None if status == "all" else status
    )
    return {"findings": findings}


@router.get("/transaction-alerts")
def api_transaction_alerts(db: DB, session: Session, status: str = "open"):
    """Org-wide transaction-monitoring alerts."""
    queue = queries.transaction_alert_queue(
        db, session.org_id, status=None if status == "all" else status
    )
    return {"transaction_alerts": queue}


@router.get("/review-queue")
def api_customers_due_review(db: DB, session: Session):
    """Customers whose periodic CDD review date has passed.

    Periodic review is an obligation under Cabinet Res. 134/2025 -- this
    endpoint surfaces the queue so the mobile app can show it without loading
    the full dashboard payload.
    """
    return {"customers": due_for_review(db, session.org_id)}


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
    result = dataclasses.asdict(outcome)
    # Re-assess risk when the disposition is applied immediately (not staged).
    # A false_positive clears sanctions_hit; a true_positive keeps it. Either
    # way the rating should reflect the new state without waiting for the next
    # scheduled rescreen.
    if not outcome.awaiting_second_review:
        _reassess_into_result(result, db, alert_id, session)
    return result


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
    result = dataclasses.asdict(outcome)
    # Confirmation always reaches a terminal status -- re-assess immediately.
    _reassess_into_result(result, db, alert_id, session)
    return result


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
    writer.writerow([_escape_csv_formula(h) for h in header])
    writer.writerows([[_escape_csv_formula(cell) for cell in row] for row in rows])
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
        now = utcnow()
        cur = db.execute(
            # email_verified_at=now: an MLRO adding a known colleague is a
            # different trust boundary from public self-registration -- see
            # the equivalent comment in api_register_organization.
            """INSERT INTO operators
                   (org_id, name, email, password_hash, role, is_active, email_verified_at, created_at)
               VALUES (?,?,?,?,?,1,?,?)""",
            (session.org_id, body.name.strip(), body.email.strip().lower(),
             auth.hash_password(body.password), body.role, now, now),
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
    _require_mlro(session)
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


# ----------------------------------------------------------------- audit export
@router.get("/audit/export")
def api_audit_export(
    request: Request,
    db: DB,
    session: Session,
):
    import csv as _csv
    from io import StringIO

    _require_mlro(session)

    from_date = request.query_params.get("from", "")
    to_date = request.query_params.get("to", "")

    query = "SELECT ts, actor, action, object_type, object_id, detail FROM audit_log WHERE org_id = ?"
    params: list = [session.org_id]

    if from_date:
        query += " AND ts >= ?"
        params.append(from_date)
    if to_date:
        query += " AND ts <= ?"
        params.append(to_date + "T23:59:59")

    query += " ORDER BY ts DESC"
    rows = db.execute(query, params).fetchall()

    buf = StringIO()
    writer = _csv.writer(buf)
    writer.writerow(["ts", "actor", "action", "object_type", "object_id", "detail"])
    for row in rows:
        writer.writerow([row["ts"], row["actor"], row["action"],
                         row["object_type"], row["object_id"], row["detail"]])

    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=audit_export.csv"},
    )
