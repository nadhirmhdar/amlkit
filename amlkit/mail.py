"""Outbound transactional email: today, just registration email verification.

SMTP via stdlib `smtplib` rather than a new dependency or a third-party HTTP
API client -- the same "avoid a new dependency" default the rest of this
project applies (see auth.py's module docstring for the one place that
default was deliberately overridden; sending a verification link is not that
kind of regulated-data decision). SMTP also works unmodified against every
major transactional-mail provider (SES, SendGrid, Postmark, Mailgun, a plain
Gmail/Workspace relay), so there is no lock-in to a specific vendor's API.

No SMTP configuration is treated as a deliberate, supported state, not an
error: `AMLKIT_SMTP_HOST` unset means send_verification_email() logs the
link to the console instead of emailing it, exactly like the existing
one-time /setup link already does for the tenancy-migration admin-claim flow
(see db.py's `connect()`). This keeps registration usable out of the box on
a fresh checkout with no mail infrastructure.

**Why the outcome is three-valued and not a bool.** It used to return
True/False, and False meant both "no SMTP configured" and "SMTP configured
but the send failed". The callers could not tell those apart, so both
registration routes fell back to handing the raw verification link straight
back to whoever submitted the form -- correct for the first case, a hole in
the second. That link activates a fully-privileged MLRO account, and proving
control of the mailbox is the entire point of the check; returning it to the
submitter when a *configured* provider was merely down let anyone register
under an address they do not own and activate it.

That is not hypothetical. SendGrid withdrew its free tier in May 2025 (see
research/commercial-launch-costs.md), so a deployment whose trial lapsed goes
on accepting registrations with SMTP configured and every send failing --
precisely the state that turned the dev convenience into an auth bypass.

So: `NOT_CONFIGURED` is the only outcome that may reveal the link, `FAILED`
must not, and every caller records the outcome in the audit log so a failing
provider is visible rather than inferred from nobody signing up.
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

logger = logging.getLogger("amlkit.mail")


def app_base_url() -> str:
    return os.environ.get("AMLKIT_APP_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


DEFAULT_FROM = "no-reply@groaml.grovisor.ae"
SENDER_NAME = "groAML by Grovisor"


def sender_address(smtp_user: str) -> str:
    """The From address: AMLKIT_SMTP_FROM, else the SMTP login when it is an
    email address, else DEFAULT_FROM.

    The login is only a fallback when it looks like a mailbox. Providers such
    as SendGrid use a fixed login ("apikey") that is not an address, and
    sending From: apikey gets the mail rejected or spam-foldered.
    """
    configured = os.environ.get("AMLKIT_SMTP_FROM", "").strip()
    if configured:
        return configured
    if "@" in smtp_user:
        return smtp_user
    return DEFAULT_FROM


def from_header(address: str) -> str:
    """The From header: address plus the SENDER_NAME display name.

    Without a display name, mail clients label the message with whatever
    name they already associate with the address (a contact entry, or the
    Workspace profile behind noreply@...), so recipients saw a person's name
    instead of the product. An AMLKIT_SMTP_FROM that already carries its own
    display name ("Name <addr>") is left as configured.
    """
    name, addr = parseaddr(address)
    if name:
        return address
    return formataddr((SENDER_NAME, addr or address))


def is_configured() -> bool:
    return bool(os.environ.get("AMLKIT_SMTP_HOST", "").strip())


def verify_url(token: str) -> str:
    return f"{app_base_url()}/verify-email?token={token}"


# Delivery outcomes. Plain strings rather than an Enum to stay consistent with
# the rest of the codebase's status vocabularies (alert status, screening
# status), all of which are stored and compared as text.
SENT = "sent"
NOT_CONFIGURED = "not_configured"
FAILED = "failed"


def send_verification_email(to_email: str, name: str, token: str) -> str:
    """Send (or, with no SMTP configured, console-log) the verification link.

    Returns `SENT`, `NOT_CONFIGURED`, or `FAILED` -- see the module docstring
    for why the distinction between the last two is load-bearing rather than
    cosmetic. Never raises: a mail-server outage should not be the reason a
    registration attempt fails outright; the operator row already exists and
    can be reached again via the resend endpoint once mail is restored.
    """
    url = verify_url(token)

    if not is_configured():
        print(
            "\n" + "=" * 72 +
            f"\namlkit: no SMTP configured (AMLKIT_SMTP_HOST unset) -- printing the\n"
            f"verification link for {to_email} instead of emailing it.\n\n"
            f"  {url}\n\n"
            "Set AMLKIT_SMTP_HOST (and friends) to send this for real.\n" +
            "=" * 72 + "\n"
        )
        return NOT_CONFIGURED

    host = os.environ["AMLKIT_SMTP_HOST"]
    port = int(os.environ.get("AMLKIT_SMTP_PORT", "587"))
    user = os.environ.get("AMLKIT_SMTP_USER", "")
    password = os.environ.get("AMLKIT_SMTP_PASSWORD", "")
    from_addr = sender_address(user)
    use_tls = os.environ.get("AMLKIT_SMTP_USE_TLS", "1") != "0"

    msg = EmailMessage()
    msg["Subject"] = "Verify your groAML account"
    msg["From"] = from_header(from_addr)
    msg["To"] = to_email
    msg.set_content(
        f"Hi {name},\n\n"
        "Confirm this email address to activate your groAML account:\n\n"
        f"  {url}\n\n"
        "This link expires in 3 days. If you didn't request this, ignore this email.\n"
    )

    try:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            if use_tls:
                smtp.starttls()
            if user:
                smtp.login(user, password)
            smtp.send_message(msg)
        return SENT
    except (OSError, smtplib.SMTPException):
        # stdout is shipped to Cloud Logging without passing through the
        # redacting formatter, so this notice deliberately omits the recipient
        # and the live verification link (its token activates the account).
        # Recovery is the resend link once the mail provider is fixed.
        logger.exception("Failed to send verification email")
        print(
            "\n" + "=" * 72 +
            f"\namlkit: SMTP send FAILED for a verification email -- mail IS configured, so\n"
            "the link is NOT being shown. Fix the mail provider, then have the user use\n"
            "the resend link.\n" +
            "=" * 72 + "\n"
        )
        return FAILED


def send_staleness_alert(to_emails: list[str], datasets: list[dict]) -> str:
    """Send email alert to admins when mandatory sanctions lists are stale.

    Returns the same three-valued outcome as send_verification_email: SENT,
    NOT_CONFIGURED, or FAILED. Never raises -- a mail outage should not block
    the refresh itself from completing.
    """
    if not to_emails:
        return SENT  # Nobody to notify

    if not is_configured():
        print(
            "\n" + "=" * 72 +
            f"\namlkit: STALENESS ALERT — {len(datasets)} mandatory list(s) breached 24h.\n"
            "No SMTP configured (AMLKIT_SMTP_HOST unset) -- printing to console only.\n" +
            "=" * 72 + "\n"
        )
        return NOT_CONFIGURED

    host = os.environ["AMLKIT_SMTP_HOST"]
    port = int(os.environ.get("AMLKIT_SMTP_PORT", "587"))
    user = os.environ.get("AMLKIT_SMTP_USER", "")
    password = os.environ.get("AMLKIT_SMTP_PASSWORD", "")
    from_addr = sender_address(user)
    use_tls = os.environ.get("AMLKIT_SMTP_USE_TLS", "1") != "0"

    dataset_list = "\n".join(
        f"  - {d['title']}: last refreshed {d['last_refresh'] or 'Never'} ({d['hours_ago']}h ago)"
        for d in datasets
    )

    msg = EmailMessage()
    msg["Subject"] = f"⚠️  groAML: {len(datasets)} sanctions list(s) stale"
    msg["From"] = from_header(from_addr)
    msg["To"] = ", ".join(to_emails)
    msg.set_content(
        f"ALERT: {len(datasets)} mandatory sanctions list(s) have exceeded the 24-hour refresh requirement.\n\n"
        f"{dataset_list}\n\n"
        "This breach must be resolved immediately to maintain compliance.\n"
        "Log in to refresh the lists manually, or investigate why the automated refresh failed.\n\n"
        f"View status: {app_base_url()}/admin\n"
    )

    try:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            if use_tls:
                smtp.starttls()
            if user:
                smtp.login(user, password)
            smtp.send_message(msg)
        logger.info("Staleness alert sent to %d MLRO recipients", len(to_emails))
        return SENT
    except (OSError, smtplib.SMTPException):
        logger.exception("Failed to send staleness alert email")
        return FAILED


def send_freeze_obligation_alert(
    to_email: str,
    freeze_obligation_id: int,
    customer_reference: str,
    obligation_type: str,
    risk_category: str,
) -> str:
    """Send MLRO email alert for new TFS freeze obligation.

    Cabinet Resolution 134/2025 places personal liability on senior management
    for TFS compliance failures. This alert ensures immediate notification when
    a freeze obligation is identified.

    Subject: "[URGENT] TFS Freeze Obligation - {customer_reference}"
    Body includes:
        - Customer reference
        - Obligation type (sanctions/proliferation/terrorism)
        - Risk category (high/critical)
        - Link to freeze obligation detail page
        - Reminder: freeze must be executed immediately per UAE law

    Returns the same three-valued outcome: SENT, NOT_CONFIGURED, or FAILED.
    Never raises.
    """
    if not to_email:
        return SENT  # Nobody to notify

    # Format obligation type for display
    type_display = {
        "sanctions": "Sanctions",
        "proliferation": "Proliferation Financing (Law 10/2025)",
        "terrorism": "Terrorism Financing",
    }.get(obligation_type, obligation_type.title())

    risk_badge = "🔴 CRITICAL" if risk_category == "critical" else "🟡 HIGH"

    detail_url = f"{app_base_url()}/freeze-obligations/{freeze_obligation_id}"

    if not is_configured():
        print(
            "\n" + "=" * 72 +
            f"\namlkit: TFS FREEZE OBLIGATION ALERT\n"
            f"Customer: {customer_reference}\n"
            f"Type: {type_display}\n"
            f"Risk: {risk_badge}\n\n"
            "No SMTP configured (AMLKIT_SMTP_HOST unset) -- printing to console only.\n\n"
            f"  {detail_url}\n" +
            "=" * 72 + "\n"
        )
        return NOT_CONFIGURED

    host = os.environ["AMLKIT_SMTP_HOST"]
    port = int(os.environ.get("AMLKIT_SMTP_PORT", "587"))
    user = os.environ.get("AMLKIT_SMTP_USER", "")
    password = os.environ.get("AMLKIT_SMTP_PASSWORD", "")
    from_addr = sender_address(user)
    use_tls = os.environ.get("AMLKIT_SMTP_USE_TLS", "1") != "0"

    msg = EmailMessage()
    msg["Subject"] = f"[URGENT] TFS Freeze Obligation - {customer_reference}"
    msg["From"] = from_header(from_addr)
    msg["To"] = to_email
    msg.set_content(
        f"URGENT: New TFS freeze obligation identified\n\n"
        f"Customer: {customer_reference}\n"
        f"Obligation Type: {type_display}\n"
        f"Risk Category: {risk_badge}\n\n"
        "IMMEDIATE ACTION REQUIRED:\n"
        "- Review the freeze obligation details immediately\n"
        "- Execute asset freeze without delay\n"
        "- Document all frozen assets\n"
        "- File FFR (Fund Freeze Report) to FIU\n\n"
        "Cabinet Resolution 134/2025 places personal liability on senior management\n"
        "for TFS compliance failures. Asset freezes must be executed immediately upon\n"
        "identification per UAE law.\n\n"
        f"View freeze obligation: {detail_url}\n"
    )

    try:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            if use_tls:
                smtp.starttls()
            if user:
                smtp.login(user, password)
            smtp.send_message(msg)
        logger.info("Freeze obligation alert sent for obligation %d",
                    freeze_obligation_id)
        return SENT
    except (OSError, smtplib.SMTPException):
        logger.exception("Failed to send freeze obligation alert for obligation %d",
                         freeze_obligation_id)
        return FAILED


def send_screening_match_alert(to_emails: list[str], *, summary: str, alert_url: str) -> str:
    """Email every active MLRO that screening produced new match(es).

    Best-effort second channel next to the in-app notification, which is the
    record of truth. The email deliberately names nobody: neither the
    customer screened nor the listed party. Mail leaves the platform in
    plaintext and sits in inboxes outside the audit trail, so it only says
    that something needs review and links to it (the same approach as the
    freeze alert, which carries a customer reference, not a name). Same
    three-valued outcome as the other senders and, like them, never raises:
    a mail outage must not be able to break a screening.
    """
    recipients = [e for e in to_emails if e]
    if not recipients:
        return SENT  # nobody to notify

    subject = "groAML: new screening match needs review"
    body = (
        f"{summary}\n\n"
        "Review it in groAML (a decision needs a reason and a written narrative):\n"
        f"  {alert_url}\n\n"
        "Do not discuss this alert with the customer.\n"
    )

    if not is_configured():
        print(
            "\n" + "=" * 72 +
            f"\namlkit: NEW SCREENING MATCH ALERT\nTo: {', '.join(recipients)}\n{summary}\n\n"
            "No SMTP configured (AMLKIT_SMTP_HOST unset) -- printing to console only.\n\n"
            f"  {alert_url}\n" + "=" * 72 + "\n"
        )
        return NOT_CONFIGURED

    host = os.environ["AMLKIT_SMTP_HOST"]
    port = int(os.environ.get("AMLKIT_SMTP_PORT", "587"))
    user = os.environ.get("AMLKIT_SMTP_USER", "")
    password = os.environ.get("AMLKIT_SMTP_PASSWORD", "")
    from_addr = sender_address(user)
    use_tls = os.environ.get("AMLKIT_SMTP_USE_TLS", "1") != "0"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_header(from_addr)
    # One message per run, but MLROs must not see each other's addresses.
    msg["To"] = from_header(from_addr)
    msg["Bcc"] = ", ".join(recipients)
    msg.set_content(body)
    try:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            if use_tls:
                smtp.starttls()
            if user:
                smtp.login(user, password)
            smtp.send_message(msg)
        logger.info("Screening match alert sent to %d MLRO(s)", len(recipients))
        return SENT
    except (OSError, smtplib.SMTPException):
        logger.exception("Failed to send screening match alert")
        return FAILED


DEFAULT_QUOTE_TO = "info@grovisor.ae"


def quote_recipients() -> list[str]:
    """Where quotation requests go: AMLKIT_QUOTE_TO (comma separated), else the
    Grovisor info inbox."""
    configured = os.environ.get("AMLKIT_QUOTE_TO", "").strip()
    if not configured:
        return [DEFAULT_QUOTE_TO]
    return [a.strip() for a in configured.split(",") if a.strip()]


def send_application_notice(application_id: int, a: dict) -> str:
    """Email a quotation request to the Grovisor inbox, Reply-To the applicant.

    `a` is the cleaned form from cases.applications.validate (single-line
    fields already stripped of CR/LF, so nothing can inject a header).
    Returns SENT, NOT_CONFIGURED or FAILED and never raises: the request is
    already saved in the database, so a mail outage must not lose it or fail
    the applicant's submission.
    """
    from .cases.applications import NO_FIRM_TYPES

    needs = ", ".join(a.get("needs") or []) or "(none selected)"
    lines = [
        f"New groAML quotation request #{application_id}",
        "",
        f"Applying as:     {a['applicant_type']}"
        + (f" (would run {a['client_firms']} client firms)" if a.get("client_firms") else ""),
        (f"Firm:            {a['org_name']}" if a["applicant_type"] not in NO_FIRM_TYPES
         else "Firm:            (none: applying as an individual)"),
        f"Business type:   {a['category']}",
        f"Licensed in:     {a['jurisdiction']}",
        "",
        f"Contact:         {a['contact_name']}" + (f" ({a['job_title']})" if a.get("job_title") else ""),
        f"Email:           {a['email']}",
        f"Phone:           {a.get('phone') or '(not given)'}",
        "",
        f"Users:           {a['team_size']}",
        f"Customers/year:  {a['customers_per_year']}",
        f"Screenings/mo:   {a.get('screenings_per_month') or '(not given)'}",
        f"Needs:           {needs}",
        "",
        "Message:",
        a.get("message") or "(none)",
        "",
        "The applicant agreed to be contacted about this request.",
        "Reply to this email to answer them directly.",
    ]
    msg = EmailMessage()
    msg["Subject"] = f"groAML quotation request: {a['org_name']}"[:150]
    recipients = quote_recipients()
    msg["To"] = ", ".join(recipients)
    msg["Reply-To"] = formataddr((a["contact_name"], a["email"]))
    msg.set_content("\n".join(lines))

    if not is_configured():
        print(
            "\n" + "=" * 72 +
            f"\namlkit: no SMTP configured (AMLKIT_SMTP_HOST unset) -- printing quotation\n"
            f"request #{application_id} for {', '.join(recipients)} instead of emailing it.\n\n"
            + "\n".join(lines) + "\n" + "=" * 72 + "\n"
        )
        return NOT_CONFIGURED

    user = os.environ.get("AMLKIT_SMTP_USER", "")
    msg["From"] = from_header(sender_address(user))
    try:
        with smtplib.SMTP(os.environ["AMLKIT_SMTP_HOST"],
                          int(os.environ.get("AMLKIT_SMTP_PORT", "587")), timeout=15) as smtp:
            if os.environ.get("AMLKIT_SMTP_USE_TLS", "1") != "0":
                smtp.starttls()
            if user:
                smtp.login(user, os.environ.get("AMLKIT_SMTP_PASSWORD", ""))
            smtp.send_message(msg)
        return SENT
    except (OSError, smtplib.SMTPException):
        # Stdout is shipped to Cloud Logging unredacted: no applicant details here.
        logger.exception("Failed to send quotation request email")
        print(f"\namlkit: SMTP send FAILED for quotation request #{application_id}; it is saved "
              "in the applications table.\n")
        return FAILED
