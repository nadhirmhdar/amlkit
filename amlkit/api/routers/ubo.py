"""Ultimate beneficial owner entry.

Moved verbatim from api/app.py (WP-18, issue #73): no route, dependency or limit changed.
"""

from __future__ import annotations

from __future__ import annotations

from typing import Annotated

from fastapi import Form, Request
from fastapi.responses import RedirectResponse

from ... import queries
from ...cases.manager import (
    add_ubo,
)
from ...datamodel import validate_ownership_pct
from ...match.engine import screen
from ..deps import (
    require_csrf,
    require_session,
)



from fastapi import APIRouter

from ..helpers import (
    DB,
    back,
)

router = APIRouter()


@router.post("/customers/{customer_id}/ubo")
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
    # Range / finite / combined-total rules live in one place
    # (datamodel.validate_ownership_pct); add_ubo re-applies them atomically.
    try:
        existing_total = db.execute(
            """SELECT COALESCE(SUM(ownership_pct), 0) FROM ubo_links
               WHERE customer_id=? AND org_id=? AND parent_ubo_id IS NULL""",
            (customer_id, session.org_id)
        ).fetchone()[0]
        pct = validate_ownership_pct(ownership_pct, existing_total)
    except ValueError as exc:
        return back(f"/customers/{customer_id}", err=f"UBO ownership: {exc}")

    try:
        ubo_id = add_ubo(db, customer_id, org_id=session.org_id, person_name=person_name.strip(),
                         ownership_pct=pct, control_type=control_type, actor=session.operator_name)
    except ValueError as exc:
        return back(f"/customers/{customer_id}", err=str(exc))
    res = screen(db, person_name.strip(), org_id=session.org_id, trigger="onboarding",
                 customer_id=customer_id, ubo_id=ubo_id, actor=session.operator_name,
                 threshold=queries.org_alert_threshold_or_default(db, session.org_id))
    if res.unscreenable:
        note = ("Beneficial owner added but NOT screened: the name has no searchable tokens."
                " Screen manually with a Latin or Arabic spelling.")
    elif res.hits:
        note = "Beneficial owner added. MATCH FOUND - review alerts."
    else:
        note = "Beneficial owner added and screened clear."
    return back(f"/customers/{customer_id}", msg=note)
