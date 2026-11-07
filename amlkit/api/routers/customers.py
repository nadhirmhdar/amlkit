"""Customer CRUD, case file, periodic review, scans, UAE PASS verification and evidence pack.

Moved verbatim from api/app.py (WP-18, issue #73): no route, dependency or limit changed.
"""

from __future__ import annotations

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from ... import auth, queries, uaepass
from ...billing.limits import BillingLimitError, check_limit, check_scan_allowed
from ..limits import limiter, operator_rate_limit_key
from ...cases.manager import (
    EXIT_REASONS,
    StaleDatasetsError,
    add_case_note,
    close_relationship,
    complete_periodic_review,
    periodic_reviews,
    reactivate_customer,
    onboard,
    record_uaepass_verification,
)
from ...datamodel import validate_ownership_pct, validate_required_name
from ...cases.review import (
    REASON_CODES,
    review_history,
    single_operator_mode,
)
from ...db import utcnow
from ...risk.model import ruleset
from ..deps import (
    require_csrf,
    require_role,
    require_session,
    startup_warning,
)

import json


from fastapi import APIRouter

from ..helpers import (
    DB,
    _audit_export,
    _clear_uaepass_state_cookie,
    _csv_response,
    _set_uaepass_state_cookie,
    _uaepass_redirect_uri,
    back,
    render,
    templates,
)

router = APIRouter()


# ------------------------------------------------------------------ customers
@router.get("/customers", response_class=HTMLResponse)
def customers(request: Request, db: DB, q: str = ""):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    if q.strip():
        results = queries.search_customers(db, session.org_id, q)
    else:
        results = queries.customer_list(db, session.org_id)
    return render(request, "customers.html",
                 {"session": session, "customers": results, "search_query": q}, db)

@router.get("/customers/new", response_class=HTMLResponse)
def customer_new(request: Request, db: DB):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    return render(request, "customer_new.html", _customer_new_ctx(session))

def _customer_new_ctx(session) -> dict:
    rs = ruleset()
    return {
        "session": session,
        "sectors": sorted(rs["factors"]["sector"]["points_by_sector"]),
        "channels": sorted(rs["factors"]["delivery_channel"]["points_by_channel"]),
        "structures": sorted(rs["factors"]["structure"]["points_by_type"]),
        "tiers": sorted(rs["factors"]["jurisdiction"]["points_by_tier"]),
    }

@router.post("/customers")
def customer_create(
    request: Request, db: DB,
    reference: Annotated[str, Form()],
    full_name: Annotated[str, Form()],
    customer_type: Annotated[str, Form()] = "natural",
    name_arabic: Annotated[str, Form()] = "",
    nationality: Annotated[str, Form()] = "",
    birth_date: Annotated[str, Form()] = "",
    gender: Annotated[str, Form()] = "",
    trade_licence: Annotated[str, Form()] = "",
    sector: Annotated[str, Form()] = "other",
    delivery_channel: Annotated[str, Form()] = "face_to_face",
    cash_level: Annotated[str, Form()] = "non_cash",
    jurisdiction_tier: Annotated[str, Form()] = "standard",
    structure: Annotated[str, Form()] = "natural_person",
    ubo_names: Annotated[list[str], Form()] = [],
    ubo_pcts: Annotated[list[str], Form()] = [],
    ubo_controls: Annotated[list[str], Form()] = [],
    purpose_of_relationship: Annotated[str, Form()] = "",
    expected_activity: Annotated[str, Form()] = "",
    risk_level: Annotated[str, Form()] = "",
    source_of_wealth: Annotated[str, Form()] = "",
    source_of_funds: Annotated[str, Form()] = "",
    subregion: Annotated[str, Form()] = "",
    nationalities_csv: Annotated[str, Form()] = "",
    tax_residencies_csv: Annotated[str, Form()] = "",
    establishment_date: Annotated[str, Form()] = "",
    civil_status_code: Annotated[str, Form()] = "",
    occupation: Annotated[str, Form()] = "",
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

    # A blank name cannot be screened and would read as "clear": reject it with
    # the form re-shown, rather than a redirect that loses what was typed.
    try:
        validate_required_name("full_name", full_name)
    except ValueError as exc:
        resp = render(request, "customer_new.html", {
            **_customer_new_ctx(session), "err": f"{exc}. Enter the customer's name.",
        }, db)
        resp.status_code = 400
        return resp

    # Validate EDD fields for high-risk customers (at onboarding, use declared risk_level)
    if risk_level and risk_level.strip() == "high":
        if not source_of_wealth or not source_of_wealth.strip():
            return back("/customers/new", err="Source of Wealth is required for high-risk customers")
        if not source_of_funds or not source_of_funds.strip():
            return back("/customers/new", err="Source of Funds is required for high-risk customers")

    ubos = []
    ubo_running_total = 0.0
    for i, nm in enumerate(ubo_names):
        nm = (nm or "").strip()
        if not nm:
            continue
        pct_raw = ubo_pcts[i] if i < len(ubo_pcts) else ""
        try:
            pct = validate_ownership_pct(pct_raw, ubo_running_total)
        except ValueError as exc:
            return back("/customers/new", err=f"UBO ownership for {nm}: {exc}")
        if pct is not None:
            ubo_running_total += pct

        ubos.append({
            "person_name": nm,
            "ownership_pct": pct,
            "control_type": (ubo_controls[i] if i < len(ubo_controls) else "ownership") or "ownership",
        })

    nats_list = [c.strip().upper() for c in nationalities_csv.split(",") if c.strip()] or None
    tax_list = [c.strip().upper() for c in tax_residencies_csv.split(",") if c.strip()] or None
    try:
        result = onboard(
            db, org_id=session.org_id, reference=reference.strip(), full_name=full_name.strip(),
            customer_type=customer_type, name_arabic=name_arabic.strip() or None,
            nationality=nationality.strip() or None, birth_date=birth_date.strip() or None,
            gender=gender.strip() or None, trade_licence=trade_licence.strip() or None,
            sector=sector, delivery_channel=delivery_channel, cash_level=cash_level,
            jurisdiction_tier=jurisdiction_tier, structure=structure,
            purpose_of_relationship=purpose_of_relationship.strip() or None,
            expected_activity=expected_activity.strip() or None,
            risk_level=risk_level.strip() or None,
            source_of_wealth=source_of_wealth.strip() or None,
            source_of_funds=source_of_funds.strip() or None,
            subregion=subregion.strip() or None,
            nationalities=nats_list,
            tax_residencies=tax_list,
            establishment_date=establishment_date.strip() or None,
            civil_status_code=civil_status_code.strip() or None,
            occupation=occupation.strip() or None,
            ubos=ubos, actor=session.operator_name,
            threshold=queries.org_alert_threshold_or_default(db, session.org_id),
        )
    except StaleDatasetsError as exc:
        return back("/customers/new", err=str(exc))
    except ValueError as exc:  # includes BillingLimitError (plan cap / lapsed subscription)
        return back("/customers/new", err=str(exc))
    except sqlite3.IntegrityError:
        return back("/customers/new", err=f"Reference {reference!r} already exists.")

    if result.blocked and result.freeze_required:
        note = "Onboarded. MATCH FOUND on a UN / UAE-local sanctions list - see alerts, freeze without delay and do not tip off."
    elif result.blocked:
        note = ("Onboarded. MATCH FOUND on a non-UAE sanctions list - see alerts, apply "
                "enhanced due diligence and consider an STR/SAR; no UAE freeze obligation arises.")
    else:
        note = f"Onboarded. Risk rating: {result.risk.rating}."
    if result.unscreenable:
        # Not a clear result: the name had no searchable tokens (e.g. non-Latin,
        # non-Arabic script). Say so rather than leave "no alerts" to be read
        # as "no hits".
        note += (
            " WARNING: " + ", ".join(result.unscreenable_names)
            + " could NOT be screened (no searchable name tokens) - screen"
            " manually with a Latin or Arabic spelling before relying on this result."
        )
    return back(f"/customers/{result.customer_id}", msg=note)

def _refuse_scan_if_unpaid(db, org_id: int) -> None:
    """402 with the payment prompt for an org that has not added payment details."""
    from fastapi import HTTPException
    try:
        check_scan_allowed(db, org_id)
    except BillingLimitError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc

def _read_scan_upload(upload: UploadFile) -> bytes:
    """Read + validate a scan upload (size, type, pixel count) or raise HTTPException 413/415."""
    from fastapi import HTTPException
    from ...validation import IMAGE_MIMES, PDF, UploadRejected, read_capped, validate_upload

    content = read_capped(upload.file)
    try:
        validate_upload(content, allowed_mimes=IMAGE_MIMES | {PDF}, check_pdf_pages=True)
    except UploadRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return content

@router.post("/customers/scan-passport")
@limiter.limit("10/minute", key_func=operator_rate_limit_key)
def customer_scan_passport(
    request: Request, db: DB,
    passport_file: UploadFile,
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail=str(exc))
    _refuse_scan_if_unpaid(db, session.org_id)

    import io
    from ...cases.ocr import extract_passport_data

    content = _read_scan_upload(passport_file)
    try:
        file_like = io.BytesIO(content)
        data = extract_passport_data(file_like)
        return data
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(exc))

@router.post("/customers/scan-trade-licence")
@limiter.limit("10/minute", key_func=operator_rate_limit_key)
def customer_scan_trade_licence(
    request: Request, db: DB,
    licence_file: UploadFile,
    csrf_token: Annotated[str, Form()] = "",
):
    """Same contract as /customers/scan-passport, for the legal-person path.

    Onboarding a company previously reused the passport scanner under a
    relabelled button -- it read passports, never trade licences, so a
    company's licence photo silently produced almost nothing. This is the
    real extractor (see cases/ocr.py's extract_trade_licence_data).
    """
    try:
        session = require_session(request, db)
    except PermissionError:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail=str(exc))
    _refuse_scan_if_unpaid(db, session.org_id)

    import io
    from ...cases.ocr import extract_trade_licence_data

    content = _read_scan_upload(licence_file)
    try:
        file_like = io.BytesIO(content)
        data = extract_trade_licence_data(file_like)
        return data
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(exc))

@router.get("/customers/{customer_id}", response_class=HTMLResponse)
def customer_detail(request: Request, db: DB, customer_id: int):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    data = queries.customer(db, customer_id, session.org_id)
    if data is None:
        return back("/customers", err=f"Customer {customer_id} not found.")
    from ...cases.diagram import generate_ubo_diagram
    diagram_svg = generate_ubo_diagram(db, customer_id, session.org_id)
    # Stored as JSON lists; show "AE, GB" rather than ["AE", "GB"] (and nothing for []).
    for key in ("nationalities", "tax_residencies"):
        data["customer"][key] = _code_list(data["customer"].get(key))
    for alert in data["alerts"]:
        alert["reviews"] = review_history(db, alert["id"], session.org_id)
    eff_risk = queries.effective_risk(db, customer_id, session.org_id)
    return render(request, "customer.html",
                 data | {"today": datetime.now(timezone.utc).date().isoformat(),
                         "reviews": periodic_reviews(db, customer_id, session.org_id),
                         "review_outcomes": REVIEW_OUTCOME_LABELS, "session": session, "reason_codes": REASON_CODES, "ubo_diagram": diagram_svg,
                         "effective_risk": eff_risk, "exit_reasons": EXIT_REASONS})

def _code_list(value) -> str:
    """'["AE","GB"]' (or a list) -> 'AE, GB'; empty or unparseable -> ''."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return value.strip()
    if not value:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v).strip() for v in value if str(v).strip())
    return str(value)

@router.get("/customers/{customer_id}/uaepass/start")
@limiter.limit("10/minute")  # IP ceiling, same as the operator SSO pair above
def uaepass_customer_start(request: Request, db: DB, customer_id: int):
    """Redirect the browser to UAE PASS so a customer can verify their
    identity for CDD -- stronger evidence than the OCR passport/Emirates-ID
    scan in cases/ocr.py, which remains the fallback.

    Session-gated and org-scoped like every other customer route (see
    queries.customer()'s tenant-isolation comment): the operator's own
    session must be valid, and the customer must belong to that operator's
    org, both checked before anything is sent to UAE PASS.
    """
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    config = uaepass.load_config()
    if config is None:
        raise HTTPException(status_code=404)

    owned = db.execute(
        "SELECT 1 FROM customers WHERE id=? AND org_id=?", (customer_id, session.org_id)
    ).fetchone()
    if owned is None:
        return back("/customers", err=f"Customer {customer_id} not found.")

    redirect_uri = _uaepass_redirect_uri(f"/customers/{customer_id}/uaepass/callback")
    # state is bound to (org_id, customer_id): a captured callback cannot be
    # replayed against a different customer, even within the same org -- see
    # auth.consume_uaepass_state().
    state = auth.create_uaepass_state(
        db, purpose="customer_verification", redirect_uri=redirect_uri,
        org_id=session.org_id, customer_id=customer_id,
    )
    resp = RedirectResponse(
        uaepass.build_authorize_url(
            config, state=state, redirect_uri=redirect_uri, acr=uaepass.ACR_LEVEL_DEFAULT
        ),
        status_code=303,
    )
    _set_uaepass_state_cookie(resp, state)
    return resp

@router.get("/customers/{customer_id}/uaepass/callback")
@limiter.limit("10/minute")  # IP ceiling, same as the operator SSO pair above
def uaepass_customer_callback(
    request: Request, db: DB, customer_id: int, code: str = "", state: str = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    config = uaepass.load_config()
    if config is None:
        raise HTTPException(status_code=404)

    expired_err = "UAE PASS verification expired, was already used, or does not match this customer."
    if not auth.csrf_valid(request.cookies.get(auth.UAEPASS_STATE_COOKIE), state):
        return _clear_uaepass_state_cookie(back(f"/customers/{customer_id}", err=expired_err))
    row = auth.consume_uaepass_state(
        db, state, purpose="customer_verification",
        org_id=session.org_id, customer_id=customer_id,
    )
    if row is None:
        return _clear_uaepass_state_cookie(back(f"/customers/{customer_id}", err=expired_err))
    if not code:
        return _clear_uaepass_state_cookie(back(
            f"/customers/{customer_id}",
            err="UAE PASS verification was cancelled or did not return a code.",
        ))

    try:
        token_payload = uaepass.exchange_code(config, code=code, redirect_uri=row["redirect_uri"])
        profile = uaepass.fetch_userinfo(config, token_payload["access_token"])
    except uaepass.UaePassError as exc:
        return _clear_uaepass_state_cookie(
            back(f"/customers/{customer_id}", err=f"UAE PASS verification failed: {exc}")
        )

    if not profile.uuid:
        # uaepass_verifications.uaepass_uuid is NOT NULL; fetch_userinfo()
        # parses defensively and never raises on a missing field, so this is
        # the one place that must still fail loudly rather than let an
        # unexpected UAE PASS response shape hit a DB constraint as a 500.
        return _clear_uaepass_state_cookie(back(
            f"/customers/{customer_id}",
            err="UAE PASS did not return a verifiable identity. Please try again.",
        ))

    try:
        record_uaepass_verification(
            db, customer_id, session.org_id, profile,
            actor=session.operator_name, verified_by=session.operator_id,
        )
    except ValueError as exc:
        # record_uaepass_verification() raises when customer_id/org_id don't
        # match -- same "not found" treatment as every other cross-tenant
        # customer_id in this file (see add_case_note()'s docstring).
        return _clear_uaepass_state_cookie(back("/customers", err=str(exc)))
    db.commit()
    latest = db.execute(
        "SELECT match_status, match_detail FROM uaepass_verifications"
        " WHERE customer_id=? AND org_id=? ORDER BY id DESC LIMIT 1",
        (customer_id, session.org_id),
    ).fetchone()
    reused = db.execute(
        "SELECT 1 FROM identity_reuse_alerts WHERE org_id=? AND customer_id=? AND status='open'",
        (session.org_id, customer_id),
    ).fetchone()
    if reused is not None:
        extra = (f" It also does NOT match this customer file: {latest['match_detail']}."
                 if latest is not None and latest["match_status"] == "mismatch" else "")
        return _clear_uaepass_state_cookie(back(
            f"/customers/{customer_id}",
            err=("UAE PASS result recorded, but this identity was already verified for another "
                 "customer. A review alert is open and nothing was copied onto this record."
                 + extra),
        ))
    if latest is not None and latest["match_status"] == "mismatch":
        return _clear_uaepass_state_cookie(back(
            f"/customers/{customer_id}",
            err=("UAE PASS result recorded but does NOT match this customer file: "
                 f"{latest['match_detail']}. No details were copied onto the customer. "
                 "Review before relying on this verification."),
        ))
    return _clear_uaepass_state_cookie(
        back(f"/customers/{customer_id}", msg="Customer identity verified via UAE PASS.")
    )

@router.get("/customers/{customer_id}/evidence", response_class=HTMLResponse)
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
    eff_risk = queries.effective_risk(db, customer_id, session.org_id)
    return render(request, "evidence.html", data | {"session": session, "generated_at": utcnow(),
                                                     "effective_risk": eff_risk}, db)

@router.get("/customers/{customer_id}/evidence.pdf")
def evidence_pack_pdf(request: Request, db: DB, customer_id: int):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    data = queries.customer(db, customer_id, session.org_id)
    if data is None:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "not found"}, status_code=404)
    for alert in data["alerts"]:
        alert["reviews"] = review_history(db, alert["id"], session.org_id)

    from ...risk.model import ruleset as load_ruleset
    rs = load_ruleset()
    generated_at = utcnow()
    eff_risk = queries.effective_risk(db, customer_id, session.org_id)
    ctx = data | {"session": session, "generated_at": generated_at,
                  "effective_risk": eff_risk}
    ctx.setdefault("security_warning", startup_warning())
    ctx.setdefault("single_operator", single_operator_mode(db, session.org_id))
    ctx["csrf_token"] = ""
    ctx["request"] = request

    html_str = templates.get_template("evidence.html").render(ctx)
    footer_html = (
        f'<div style="text-align:center; font-size:9px; color:#888; padding:4px;">'
        f'Generated {generated_at[:19].replace("T", " ")} UTC'
        f' &middot; groAML by Grovisor &middot; ruleset {rs.get("version", "unknown")}'
        f'</div>'
    )
    html_str = html_str.replace("</body>", footer_html + "</body>")

    try:
        from ...reporting.evidence_pdf import render_pdf
        pdf_bytes = render_pdf(html_str)
    except (ImportError, OSError):
        return back(f"/customers/{customer_id}/evidence",
                    err="PDF generation unavailable — WeasyPrint system libraries not installed.")

    _audit_export(db, session, "export.evidence_pdf", "customer", customer_id)
    from fastapi.responses import Response
    # Header values must be latin-1: give an ASCII fallback filename plus the
    # full (possibly Arabic) name via RFC 6266 filename*.
    import re as _re
    from urllib.parse import quote as _quote
    full_name = data["customer"]["full_name"]
    ascii_name = _re.sub(r"[^A-Za-z0-9._-]+", "_", full_name).strip("_") or "customer"
    utf8_name = _quote(f"evidence-{customer_id}-{full_name}.pdf", safe="")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="evidence-{customer_id}-{ascii_name}.pdf"; '
                f"filename*=UTF-8''{utf8_name}"
            ),
        },
    )

@router.post("/customers/{customer_id}/close")
def customer_close(request: Request, db: DB, customer_id: int,
                   exit_reason: Annotated[str, Form()] = "",
                   exit_note: Annotated[str, Form()] = "",
                   csrf_token: Annotated[str, Form()] = ""):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back(f"/customers/{customer_id}", err=str(exc))
    try:
        until = close_relationship(db, customer_id, org_id=session.org_id,
                                   reason=exit_reason, note=exit_note[:1000],
                                   actor=session.operator_name)
    except ValueError as exc:
        return back(f"/customers/{customer_id}", err=str(exc))
    return back(f"/customers/{customer_id}", msg=f"Relationship closed. Records retained until {until}.")

REVIEW_OUTCOME_LABELS = {
    "no_change": "No change",
    "risk_changed": "Risk changed (re-assess)",
    "exit_relationship": "Exit the relationship",
}

@router.post("/customers/{customer_id}/periodic-review")
def customer_periodic_review(
    request: Request, db: DB, customer_id: int,
    outcome: Annotated[str, Form()] = "",
    note: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
):
    """Complete a periodic CDD review. The only action that resets the
    customer's next review date."""
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
        require_role(session, *auth.OPERATOR_ROLES)
    except PermissionError as exc:
        return back(f"/customers/{customer_id}", err=str(exc))
    try:
        complete_periodic_review(db, session.org_id, customer_id, session,
                                 outcome, note)
    except LookupError:
        raise HTTPException(status_code=404, detail="Customer not found.")
    except ValueError as exc:
        return back(f"/customers/{customer_id}", err=str(exc))
    return back(f"/customers/{customer_id}", msg="Periodic review recorded.")

@router.post("/customers/{customer_id}/reactivate")
def customer_reactivate(
    request: Request, db: DB, customer_id: int,
    reason: Annotated[str, Form()] = "",
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
        require_role(session, "mlro")
    except PermissionError as exc:
        return back(f"/customers/{customer_id}", err=str(exc))
    try:
        check_limit(db, session.org_id, "customers")
    except BillingLimitError as exc:
        return back(f"/customers/{customer_id}", err=str(exc))
    try:
        reactivate_customer(db, customer_id, org_id=session.org_id,
                            reason=reason.strip() or "No reason provided",
                            actor=session.operator_name)
    except ValueError as exc:
        return back(f"/customers/{customer_id}", err=str(exc))
    return back(f"/customers/{customer_id}", msg="Customer reactivated.")

@router.post("/customers/{customer_id}/notes")
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

@router.get("/customers.csv")
def customers_csv(request: Request, db: DB):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    rows = queries.customer_list(db, session.org_id)
    _audit_export(db, session, "export.customers_csv", None, None, {"rows": len(rows)})
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
