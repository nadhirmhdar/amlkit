"""From-address resolution in amlkit/mail.py (sender_address)."""

from __future__ import annotations

from amlkit.mail import DEFAULT_FROM, from_header, sender_address


def test_explicit_from_wins(monkeypatch):
    monkeypatch.setenv("AMLKIT_SMTP_FROM", "alerts@firm.ae")
    assert sender_address("mlro@firm.ae") == "alerts@firm.ae"


def test_login_used_when_it_is_an_address(monkeypatch):
    monkeypatch.delenv("AMLKIT_SMTP_FROM", raising=False)
    assert sender_address("mlro@firm.ae") == "mlro@firm.ae"


def test_non_address_login_is_never_the_sender(monkeypatch):
    # SendGrid's SMTP login is the literal string "apikey".
    monkeypatch.delenv("AMLKIT_SMTP_FROM", raising=False)
    assert sender_address("apikey") == DEFAULT_FROM


def test_blank_from_falls_back(monkeypatch):
    monkeypatch.setenv("AMLKIT_SMTP_FROM", "  ")
    assert sender_address("") == DEFAULT_FROM


def test_from_header_adds_product_name():
    assert from_header("noreply@grovisor.ae") == "groAML by Grovisor <noreply@grovisor.ae>"


def test_from_header_keeps_configured_display_name():
    assert from_header("Compliance Team <alerts@firm.ae>") == "Compliance Team <alerts@firm.ae>"


def test_alert_subjects_use_groaml_casing(monkeypatch):
    """Subjects are matched by external inbox filters, so pin their exact text."""
    from amlkit import mail

    captured = []

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): pass
        def login(self, *a): pass
        def send_message(self, msg): captured.append(msg)

    monkeypatch.setenv("AMLKIT_SMTP_HOST", "smtp.example.test")
    monkeypatch.delenv("AMLKIT_SMTP_FROM", raising=False)
    monkeypatch.setattr(mail.smtplib, "SMTP", FakeSMTP)

    mail.send_verification_email("a@example.test", "A", "tok")
    mail.send_staleness_alert(
        ["ops@example.test"],
        [{"title": "UN", "last_refresh": None, "hours_ago": 30}],
    )
    mail.send_screening_match_alert(
        ["mlro@example.test"], summary="s", alert_url="https://x.example.test/a"
    )

    assert [m["Subject"] for m in captured] == [
        "Verify your groAML account",
        "⚠️  groAML: 1 sanctions list(s) stale",
        "groAML: new screening match needs review",
    ]
