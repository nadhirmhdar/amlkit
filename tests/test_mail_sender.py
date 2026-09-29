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
