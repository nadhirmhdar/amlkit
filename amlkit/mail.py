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
a fresh checkout with no mail infrastructure, while still recording -- via
the return value -- whether a real email actually went out, so callers can
avoid ever handing the raw token back to a client once real mail is live.
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger("amlkit.mail")


def app_base_url() -> str:
    return os.environ.get("AMLKIT_APP_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def is_configured() -> bool:
    return bool(os.environ.get("AMLKIT_SMTP_HOST", "").strip())


def verify_url(token: str) -> str:
    return f"{app_base_url()}/verify-email?token={token}"


def send_verification_email(to_email: str, name: str, token: str) -> bool:
    """Send (or, with no SMTP configured, console-log) the verification link.

    Returns True if a real email was actually sent, False if it fell back to
    the console. Never raises -- a mail-server outage should not be the
    reason a registration attempt fails outright; the operator row already
    exists and can be reached again via the resend endpoint.
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
        return False

    host = os.environ["AMLKIT_SMTP_HOST"]
    port = int(os.environ.get("AMLKIT_SMTP_PORT", "587"))
    user = os.environ.get("AMLKIT_SMTP_USER", "")
    password = os.environ.get("AMLKIT_SMTP_PASSWORD", "")
    from_addr = os.environ.get("AMLKIT_SMTP_FROM", user or "no-reply@amlkit.local")
    use_tls = os.environ.get("AMLKIT_SMTP_USE_TLS", "1") != "0"

    msg = EmailMessage()
    msg["Subject"] = "Verify your amlkit account"
    msg["From"] = from_addr
    msg["To"] = to_email
    msg.set_content(
        f"Hi {name},\n\n"
        "Confirm this email address to activate your amlkit account:\n\n"
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
        return True
    except (OSError, smtplib.SMTPException):
        logger.exception("Failed to send verification email to %s", to_email)
        print(
            "\n" + "=" * 72 +
            f"\namlkit: SMTP send FAILED for {to_email} -- printing the link instead.\n\n"
            f"  {url}\n" +
            "=" * 72 + "\n"
        )
        return False
