"""Public pages: home, health, about/privacy, blog, apply, changelog, robots/sitemap.

Moved verbatim from api/app.py (WP-18, issue #73): no route, dependency or limit changed.
"""

from __future__ import annotations

from __future__ import annotations

from typing import Annotated

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from ... import auth, changelog, queries, uaepass
from ...web import blog
from ..limits import limiter
from ..deps import (
    current_session,
    require_csrf,
    require_session,
)

import os


from fastapi import APIRouter

from ..helpers import (
    DB,
    public_base_url,
    render,
)

router = APIRouter()


# ----------------------------------------------------------------- health
def _uaepass_live() -> bool:
    """Public copy may mention UAE PASS only when it is real: configured AND
    pointed at production. The staging sandbox accepts POC credentials only,
    so real customers cannot complete it (L-118)."""
    cfg = uaepass.load_config()
    return cfg is not None and cfg.environment == "production"


@router.get("/health")
def health_check(db: DB):
    from fastapi.responses import JSONResponse
    from ...ingest.loader import staleness_report
    # N002: Public /health returns status (healthy/degraded) but not dataset details.
    # Degraded = mandatory list breach (compliance signal for Cloud Run probes).
    # Details moved to /admin/compliance (auth-required).
    datasets = staleness_report(db)
    any_breach = any(d["breach"] for d in datasets)
    return JSONResponse({
        "status": "degraded" if any_breach else "healthy",
    })

def _apply_ctx(extra: dict | None = None) -> dict:
    from ...cases import applications as apps
    ctx = {
        "session": None, "categories": apps.CATEGORIES, "jurisdictions": apps.JURISDICTIONS,
        "applicant_types": apps.APPLICANT_TYPES, "client_firm_counts": apps.CLIENT_FIRMS,
        "consultant": apps.CONSULTANT, "name_optional_types": sorted(apps.NAME_OPTIONAL_TYPES),
        "no_firm_types": sorted(apps.NO_FIRM_TYPES),
        "team_sizes": apps.TEAM_SIZES, "customers_per_year": apps.CUSTOMERS_PER_YEAR,
        "screenings_per_month": apps.SCREENINGS_PER_MONTH, "needs_options": apps.NEEDS,
        "values": {}, "errors": {},
        "invite_registration": bool(os.environ.get("AMLKIT_REGISTRATION_INVITE_CODE", "").strip()),
    }
    ctx.update(extra or {})
    return ctx

@router.get("/apply", response_class=HTMLResponse)
def apply_form(request: Request, db: DB):
    return render(request, "apply.html", _apply_ctx())

@router.post("/apply")
@limiter.limit("5/hour")
@limiter.limit("30/day")
def apply_submit(
    request: Request, db: DB,
    applicant_type: Annotated[str, Form()] = "",
    client_firms: Annotated[str, Form()] = "",
    org_name: Annotated[str, Form()] = "",
    category: Annotated[str, Form()] = "",
    jurisdiction: Annotated[str, Form()] = "",
    contact_name: Annotated[str, Form()] = "",
    job_title: Annotated[str, Form()] = "",
    email: Annotated[str, Form()] = "",
    phone: Annotated[str, Form()] = "",
    team_size: Annotated[str, Form()] = "",
    customers_per_year: Annotated[str, Form()] = "",
    screenings_per_month: Annotated[str, Form()] = "",
    needs: Annotated[list[str] | None, Form()] = None,
    message: Annotated[str, Form()] = "",
    consent: Annotated[str, Form()] = "",
    company_website: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
):
    from ...cases import applications as apps
    from ... import mail

    values = {
        "applicant_type": applicant_type, "client_firms": client_firms,
        "org_name": org_name, "category": category, "jurisdiction": jurisdiction,
        "contact_name": contact_name, "job_title": job_title, "email": email, "phone": phone,
        "team_size": team_size, "customers_per_year": customers_per_year,
        "screenings_per_month": screenings_per_month, "needs": needs or [],
        "message": message, "consent": consent,
    }
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return render(request, "apply.html", _apply_ctx({"values": values, "err": str(exc)}))

    # Honeypot: real people never see or fill this field. Pretend it worked.
    # Not logged to auth_log: bots would add one row per hit, unbounded.
    if company_website.strip():
        return RedirectResponse("/apply/thanks", status_code=303)

    clean, errors = apps.validate(values)
    if errors:
        return render(request, "apply.html", _apply_ctx({
            "values": values, "errors": errors,
            "err": "Please fix the highlighted fields and send it again.",
        }))

    application_id = apps.save(db, clean)
    outcome = mail.send_application_notice(application_id, clean)
    apps.record_delivery(db, application_id, outcome)
    # No email here: auth_log is outside the 12-month applications purge, so
    # storing it would outlive the retention period and an erasure request.
    auth._log_auth_event(db, "application_submitted", None,
                         {"application_id": application_id, "email_delivery": outcome})
    return RedirectResponse("/apply/thanks", status_code=303)

@router.get("/apply/thanks", response_class=HTMLResponse)
def apply_thanks(request: Request, db: DB):
    return render(request, "apply_thanks.html", {"session": None})

# ------------------------------------------------------------------ home
@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: DB):
    """Signed in: the first screen after sign-in -- an orientation page, not the
    dashboard. A new or occasional operator needs "what do I do" before
    "what's outstanding"; the dashboard (queue/stale-list detail) is one
    click away via the nav or the alerts bar below, not buried.
    Anonymous visitors get the public landing page (no tenant data read)."""
    try:
        session = require_session(request, db)
    except PermissionError:
        if current_session(request, db) is None:
            return render(request, "landing.html", {"session": None, "nav": "home",
                                                     "uaepass_live": _uaepass_live()}, db)
        return RedirectResponse("/login", status_code=303)

    first_name = (session.operator_name or "").split()
    first_name = first_name[0] if first_name else session.operator_name

    d = queries.dashboard(db, session.org_id)

    return render(request, "home.html", {
        "session": session,
        "d": d,
        "first_name": first_name,
    }, db)

# ------------------------------------------------- public marketing pages
# Same per-IP limit as GET /apply: the app-wide default (100/minute). No
# tenant data is read by any of these.
@router.get("/aml-law", response_class=HTMLResponse)
def aml_law_view(request: Request, db: DB):
    return render(request, "aml_law.html", {"session": current_session(request, db),
                                             "uaepass_live": _uaepass_live()}, db)

@router.get("/pricing", response_class=HTMLResponse)
def pricing(request: Request, db: DB):
    """Always public. Prices come from STRIPE_DISPLAY_PRICE_<TIER> ("Contact us"
    when blank); the CTA follows billing.self_serve_enabled()."""
    from ...billing import plans, stripe_client
    from ..billing import plan_cards
    return render(request, "pricing.html", {
        "session": current_session(request, db),
        "cards": plan_cards(stripe_client.load_config()), "trial_days": plans.TRIAL_DAYS,
    }, db)

# ------------------------------------------------------------------ changelog
@router.get("/changelog", response_class=HTMLResponse)
def changelog_page(request: Request, db: DB):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    changelog.mark_seen(db, session.org_id, session.operator_id)
    return render(request, "changelog.html", {
        "session": session, "entries": changelog.entries(), "changelog_unseen": False,
    }, db)

@router.get("/about", response_class=HTMLResponse)
def about_view(request: Request, db: DB):
    session = current_session(request, db)
    return render(request, "about.html", {"session": session}, db)

@router.get("/privacy", response_class=HTMLResponse)
def privacy_view(request: Request, db: DB):
    session = current_session(request, db)
    from ...mail import quote_recipients
    return render(request, "privacy.html",
                  {"session": session, "quote_to": quote_recipients()[0]}, db)

# ------------------------------------------------------------------------ blog
# Public, same as /about -- educational content for DNFBPs researching their
# screening obligations, meant to be found by search rather than reached from
# inside the product.
@router.get("/blog", response_class=HTMLResponse)
def blog_index(request: Request, db: DB, topic: str = "", q: str = ""):
    session = current_session(request, db)
    active = blog.get_topic(topic) if topic else None
    if topic and active is None:
        raise HTTPException(status_code=404)
    q = q.strip()[:100]
    posts = blog.posts_in_topic(active.slug) if active else blog.all_posts()
    if q:  # no-JS fallback; blog.js filters the same cards instantly in the browser
        posts = blog.search(q, posts)
    featured = next((p for p in posts if p.featured), None) if not (active or q) else None
    return render(request, "blog_index.html", {
        "session": session, "posts": posts, "featured": featured, "q": q,
        "active_topic": active, "topics": blog.topic_counts(),
    }, db)

@router.get("/blog/{slug}", response_class=HTMLResponse)
def blog_post_view(request: Request, slug: str, db: DB):
    post = blog.get_post(slug)
    if post is None:
        raise HTTPException(status_code=404)
    session = current_session(request, db)
    return render(request, f"blog/{post.slug}.html", {
        "session": session, "post": post, "related": blog.related_posts(post),
    }, db)

@router.get("/favicon.ico", include_in_schema=False)
def favicon_ico():
    # Browsers and crawlers request /favicon.ico regardless of the <link rel="icon">
    # in base.html. Redirect to the static copy (16/32/48px, rendered from
    # favicon.svg) so it gets /static/ caching rather than no-store.
    return RedirectResponse("/static/img/favicon.ico", status_code=301)

@router.get("/robots.txt", response_class=Response)
def robots_txt():
    # Disallow only stops crawling; the noindex meta on signed-in pages is the
    # real control (L-88).
    private = ("customers", "alerts", "admin", "audit", "reports", "compliance", "billing",
               "dashboard", "screen", "freeze", "policies", "notifications", "profile")
    body = ("User-agent: *\n" + "".join(f"Disallow: /{p}\n" for p in private)
            + f"Allow: /\nSitemap: {public_base_url()}/sitemap.xml\n")
    return Response(body, media_type="text/plain")

@router.get("/sitemap.xml", response_class=Response)
def sitemap_xml():
    urls = ["/", "/aml-law", "/pricing", "/about", "/privacy", "/apply", "/blog"] + [f"/blog/{p.slug}" for p in blog.all_posts()]
    lastmods = {"/blog": blog.all_posts()[0].updated if blog.all_posts() else None}
    for p in blog.all_posts():
        lastmods[f"/blog/{p.slug}"] = p.updated
    entries = "\n".join(
        f'  <url><loc>{public_base_url()}{u}</loc>'
        + (f'<lastmod>{lastmods[u]}</lastmod>' if lastmods.get(u) else '')
        + '</url>'
        for u in urls
    )
    body = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{entries}\n</urlset>\n'
    return Response(body, media_type="application/xml")
