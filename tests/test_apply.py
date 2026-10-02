"""/apply: the public quotation-request form.

A request is saved and emailed to the Grovisor inbox (Reply-To the applicant).
It must never create an organization, an operator or any access.
"""
from __future__ import annotations

import os
import re
import smtplib
import sqlite3

import pytest

GOOD = {
    "applicant_type": "Single entity",
    "org_name": "Gulf Gold Trading LLC",
    "category": "Dealer in precious metals or stones",
    "jurisdiction": "Dubai",
    "contact_name": "Layla Haddad",
    "job_title": "MLRO",
    "email": "Layla@GulfGold.example",
    "phone": "+971 4 555 0100",
    "team_size": "2-5",
    "customers_per_year": "100-500",
    "screenings_per_month": "100-500",
    "needs": ["Sanctions and PEP screening", "goAML STR/SAR reporting", "Not a real option"],
    "message": "We need this before our next MoE inspection.",
    "consent": "yes",
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AMLKIT_DB", str(tmp_path / "t.db"))
    for var in ("AMLKIT_SMTP_HOST", "AMLKIT_QUOTE_TO", "AMLKIT_REGISTRATION_INVITE_CODE"):
        monkeypatch.delenv(var, raising=False)
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    c = TestClient(app)
    c.get("/apply")  # sets the CSRF cookie
    return c


def _post(client, **overrides):
    data = {**GOOD, **overrides, "csrf_token": client.cookies.get("amlkit_csrf")}
    data = {k: v for k, v in data.items() if v is not None}
    return client.post("/apply", data=data, follow_redirects=False)


def _rows(table="applications"):
    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(f"SELECT * FROM {table}").fetchall()
    finally:
        conn.close()


class FakeSMTP:
    sent: list = []
    fail = False

    def __init__(self, host, port, timeout=None):
        self.host = host

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        pass

    def send_message(self, msg):
        if FakeSMTP.fail:
            raise smtplib.SMTPException("provider down")
        FakeSMTP.sent.append(msg)


@pytest.fixture()
def smtp(monkeypatch):
    FakeSMTP.sent, FakeSMTP.fail = [], False
    monkeypatch.setenv("AMLKIT_SMTP_HOST", "smtp.test")
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    return FakeSMTP


def test_form_renders_with_every_field_a_quotation_needs(client):
    html = client.get("/apply").text
    for name in ("applicant_type", "org_name", "category", "jurisdiction", "contact_name", "email", "phone",
                 "team_size", "customers_per_year", "screenings_per_month", "needs", "message", "consent"):
        assert f'name="{name}"' in html, name
    assert "does not create an account" in html


def test_sign_in_page_sends_new_organizations_to_the_form(client):
    html = client.get("/login").text
    assert 'href="/apply"' in html
    assert 'href="/register-organization"' not in html


def test_valid_request_is_emailed_to_the_grovisor_inbox_with_reply_to_the_applicant(client, smtp):
    r = _post(client)
    assert r.status_code == 303 and r.headers["location"] == "/apply/thanks"
    assert len(smtp.sent) == 1
    msg = smtp.sent[0]
    assert msg["To"] == "info@grovisor.ae"
    assert "layla@gulfgold.example" in msg["Reply-To"]
    assert msg["Subject"] == "groAML quotation request: Gulf Gold Trading LLC"
    body = msg.get_content()
    for expected in ("Gulf Gold Trading LLC", "Dealer in precious metals or stones", "Dubai",
                     "Layla Haddad (MLRO)", "2-5", "100-500", "goAML STR/SAR reporting",
                     "before our next MoE inspection"):
        assert expected in body, expected
    assert "Not a real option" not in body
    row = _rows()[0]
    assert row["email_delivery"] == "sent" and row["status"] == "new"
    assert row["email"] == "layla@gulfgold.example"


def test_recipient_is_configurable(client, smtp, monkeypatch):
    monkeypatch.setenv("AMLKIT_QUOTE_TO", "sales@grovisor.ae, ceo@grovisor.ae")
    _post(client)
    assert smtp.sent[0]["To"] == "sales@grovisor.ae, ceo@grovisor.ae"


def test_request_is_saved_even_when_mail_is_not_configured_or_failing(client, smtp, monkeypatch):
    smtp.fail = True
    r = _post(client)
    assert r.status_code == 303 and r.headers["location"] == "/apply/thanks"
    assert _rows()[0]["email_delivery"] == "failed"
    monkeypatch.delenv("AMLKIT_SMTP_HOST")
    _post(client, org_name="Second Firm LLC")
    assert [r["email_delivery"] for r in _rows()] == ["failed", "not_configured"]


def test_a_request_creates_no_organization_operator_or_access(client, smtp):
    before = (len(_rows("organizations")), len(_rows("operators")))
    _post(client)
    assert (len(_rows("organizations")), len(_rows("operators"))) == before


def test_confirmation_page_promises_nothing_it_cannot_keep(client):
    html = client.get("/apply/thanks").text
    assert "Request received" in html
    assert "Nothing has been created or charged" in html
    assert not re.search(r"within \d+ (hours?|days?)|24 hours|same day", html, re.I)


@pytest.mark.parametrize("overrides,field", [
    ({"consent": None}, "consent"),
    ({"email": "not-an-email"}, "email"),
    ({"org_name": "   "}, "org_name"),
    ({"category": "Casino"}, "category"),
    ({"jurisdiction": ""}, "jurisdiction"),
    ({"phone": "call me maybe"}, "phone"),
])
def test_invalid_submissions_are_rejected_with_the_field_named_and_nothing_saved(client, smtp, overrides, field):
    r = _post(client, **overrides)
    assert r.status_code == 200
    assert f'id="ap-{field}-err"' in r.text
    assert _rows() == [] and smtp.sent == []
    # What the person typed is kept, so they are not made to start again.
    if field != "org_name":
        assert "Gulf Gold Trading LLC" in r.text


def test_newlines_in_fields_cannot_inject_email_headers(client, smtp):
    _post(client, org_name="Evil LLC\r\nBcc: attacker@evil.example", contact_name="X\nCc: y@evil.example")
    msg = smtp.sent[0]
    assert msg["Bcc"] is None and msg["Cc"] is None
    assert "\n" not in msg["Subject"] and "\r" not in msg["Subject"]


def test_bots_that_fill_the_hidden_field_are_ignored_quietly(client, smtp):
    r = _post(client, company_website="http://spam.example")
    assert r.status_code == 303 and r.headers["location"] == "/apply/thanks"
    assert _rows() == [] and smtp.sent == []
    assert _rows("auth_log") == []   # a bot's hit leaves no trace, so bots cannot grow the table


def test_post_without_a_valid_csrf_token_is_refused(client, smtp):
    data = {k: v for k, v in GOOD.items()}
    r = client.post("/apply", data={**data, "csrf_token": "forged"}, follow_redirects=False)
    assert r.status_code == 200 and "stale page" in r.text
    assert _rows() == [] and smtp.sent == []


def test_a_burst_of_submissions_from_one_address_is_rate_limited(client, smtp):
    from amlkit.api.app import app
    app.state.limiter.enabled = True  # the suite switches it off globally
    try:
        app.state.limiter.reset()
        codes = [_post(client, org_name=f"Firm {i}").status_code for i in range(7)]
    finally:
        app.state.limiter.enabled = False
    assert codes[:5] == [303] * 5
    assert 429 in codes[5:]
    assert len(_rows()) == 5


def test_all_four_applicant_options_are_offered_with_a_plain_description(client):
    html = client.get("/apply").text
    for label in ("Single entity", "B2B consultant", "Natural person", "Professional"):
        assert f'value="{label}"' in html, label
    assert "running compliance for several client firms" in html
    assert "sole proprietor" in html
    assert "lawyer, accountant or auditor" in html


@pytest.mark.parametrize("applicant_type", ["Single entity", "Natural person", "Professional"])
def test_non_consultants_are_accepted_without_client_firms(client, smtp, applicant_type):
    r = _post(client, applicant_type=applicant_type, client_firms="21-50")
    assert r.status_code == 303
    row = _rows()[0]
    assert row["applicant_type"] == applicant_type
    assert row["client_firms"] is None            # only consultants are asked, so it is dropped
    assert f"Applying as:     {applicant_type}" in smtp.sent[0].get_content()
    assert "client firms" not in smtp.sent[0].get_content().split("Applying as:")[1].splitlines()[0]


def test_a_consultant_must_say_how_many_client_firms_they_would_run(client, smtp):
    r = _post(client, applicant_type="B2B consultant", client_firms="")
    assert r.status_code == 200 and 'id="ap-client_firms-err"' in r.text
    assert _rows() == []
    r = _post(client, applicant_type="B2B consultant", client_firms="6-20", org_name="Gulf Compliance Partners")
    assert r.status_code == 303
    assert _rows()[0]["client_firms"] == "6-20"
    assert "would run 6-20 client firms" in smtp.sent[0].get_content()


def test_a_professional_may_leave_the_practice_name_blank_and_use_their_own_name(client, smtp):
    _post(client, applicant_type="Professional", org_name="")
    assert _rows()[0]["org_name"] == "Layla Haddad"
    assert smtp.sent[0]["Subject"] == "groAML quotation request: Layla Haddad"


def test_a_natural_person_is_never_asked_for_a_firm_or_job_title_and_any_sent_are_ignored(client, smtp):
    _post(client, applicant_type="Natural person", org_name="Some Firm LLC", job_title="Director")
    row = _rows()[0]
    assert row["org_name"] == "Layla Haddad" and row["job_title"] is None
    body = smtp.sent[0].get_content()
    assert "Some Firm LLC" not in body and "Director" not in body
    assert "Firm:            (none: applying as an individual)" in body
    assert "Layla Haddad" in body and "Layla Haddad (" not in body  # no "(job title)" suffix
    assert smtp.sent[0]["Subject"] == "groAML quotation request: Layla Haddad"


def test_a_natural_person_form_redisplayed_after_an_error_still_hides_the_firm_fields(client, smtp):
    r = _post(client, applicant_type="Natural person", email="bad")
    assert r.status_code == 200
    assert re.search(r'id="ap-org-field"[^>]*\bhidden\b', r.text)
    assert re.search(r'id="ap-job-field"[^>]*\bhidden\b', r.text)
    assert "Your activity" in r.text
    # ...and a company applicant sees them.
    r = _post(client, applicant_type="Single entity", email="bad")
    assert not re.search(r'id="ap-org-field"[^>]*\bhidden\b', r.text)
    assert "Your firm" in r.text


@pytest.mark.parametrize("applicant_type", ["Single entity", "B2B consultant"])
def test_a_company_or_consultancy_must_name_itself(client, smtp, applicant_type):
    r = _post(client, applicant_type=applicant_type, client_firms="1-5", org_name="")
    assert r.status_code == 200 and 'id="ap-org_name-err"' in r.text
    assert _rows() == []


@pytest.mark.parametrize("bad", ["", "Government", "single entity"])
def test_an_unknown_or_missing_applicant_type_is_rejected(client, smtp, bad):
    r = _post(client, applicant_type=bad)
    assert r.status_code == 200 and 'id="ap-applicant_type-err"' in r.text
    assert _rows() == []


def test_a_professional_with_no_name_at_all_gets_one_clear_error_not_a_contradictory_pair(client, smtp):
    """The practice name is marked optional, so it must never be the field that errors."""
    r = _post(client, applicant_type="Professional", org_name="", contact_name="")
    assert r.status_code == 200
    assert 'id="ap-contact_name-err"' in r.text      # "Enter your name."
    assert 'id="ap-org_name-err"' not in r.text      # the optional field stays quiet
    assert _rows() == []


def test_email_validation_is_the_shared_auth_rule_so_the_forms_cannot_drift(monkeypatch):
    """/apply must not carry its own copy of the email pattern."""
    import re
    from amlkit import auth
    from amlkit.cases import applications as apps

    form = {"applicant_type": "Single entity", "org_name": "X LLC", "contact_name": "A B",
            "email": "someone@gmail.example", "category": apps.CATEGORIES[0],
            "jurisdiction": apps.JURISDICTIONS[0], "team_size": apps.TEAM_SIZES[0],
            "customers_per_year": apps.CUSTOMERS_PER_YEAR[0], "consent": "yes"}
    assert "email" not in apps.validate(form)[1]
    # Tighten the shared rule: /apply follows it immediately.
    monkeypatch.setattr(auth, "EMAIL_RE", re.compile(r"^[^@\s]+@corp\.ae$"))
    assert "email" in apps.validate(form)[1]
