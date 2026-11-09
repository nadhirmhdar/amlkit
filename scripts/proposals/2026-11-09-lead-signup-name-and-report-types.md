# HELD: sign-up mail payload (L-134) and unsupported goAML report types (L-135..L-137)

Lead, 2026-11-09, master `9219e2623b3a3ba7e73a20e44c703ab80df7e900`. Not applied: each change
touches business logic or a route (routine rule 3). Repro: `repro_lead/checks_2026_11_09.py`
(exit 0 while any item reproduces).

## 1. L-134 (SS5, LOW; gate for Stripe go-live): visitor-chosen text in groAML's verification mail

**Defect.** `auth.check_operator_identity` (`amlkit/auth.py:214-239`) refuses control characters,
over-length and reserved names only. `mail.send_verification_email` writes the name verbatim:
`f"Hi {name},\n\n"` (`amlkit/mail.py:138`). In open sign-up (Stripe mode) an anonymous visitor
picks both the recipient and the greeting, so groAML's own sender delivers attacker text plus a
URL next to a genuine link. With no per-address cooldown (L-130) this works as a branded phishing
channel at 5 sign-ups/min/IP. Header injection is blocked (red-team, 2026-11-09).

Repro output (fake SMTP class in-process, nothing sent):
```
SS5   mail greeting line: 'Hi Mallory <b>bold</b> https://evil.test/pay,'
SS5   reproduces=True
```

**Proposed diff (smallest).** Don't greet an unverified address by name:
```diff
--- a/amlkit/mail.py
+++ b/amlkit/mail.py
@@ def send_verification_email(to_email: str, name: str, token: str) -> str:
     msg.set_content(
-        f"Hi {name},\n\n"
+        "Hello,\n\n"
         "Confirm this email address to activate your groAML account:\n\n"
```
(Also keep `name` in the signature so callers don't change. Do the same for any other mail sent
before the recipient has proved control of the address. `send_existing_account_notice` already
uses the stored owner name, so it is fine.)

**Optional hardening.** Also reject `://`, `<` and `>` in operator names in `check_operator_identity`.
Not recommended as the only fix: it changes validation for every operator path (web, mobile,
rename), and the mail fix alone removes the payload.

**Test to add with the fix** (fails on master today, so not committed):
```python
def test_verification_mail_does_not_echo_visitor_name(monkeypatch):
    sent = []
    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self, *a, **k): pass
        def login(self, *a, **k): pass
        def send_message(self, m, *a, **k): sent.append(m)
    monkeypatch.setenv("AMLKIT_SMTP_HOST", "smtp.invalid")
    monkeypatch.setattr(mail.smtplib, "SMTP", FakeSMTP)
    mail.send_verification_email("x@y.ae", "Mallory https://evil.test", "tok")
    assert "evil.test" not in sent[0].get_content()
```
Land it together with L-129 (timing) and L-130 (cooldown), from
`2026-11-08-lead-signup-timing-uaepass-env-scheduler.md`. All three concern the open sign-up form.

## 2. L-136 (RT2, LOW): builder renders for types that cannot be saved

**Defect.** `report_build_view` (`amlkit/api/routers/reports.py:92-131`) passes any `report_type`
query value to `str_builder.html`. Save then refuses it (`reporting/goaml.py:236-240`), after the
operator has filled in the form.
```
RT2   GET /reports/build (status, page warns type unsupported): {'STR': (200, False), 'DPMSR': (200, False), 'REAR': (200, False), 'HRCT': (200, False)}
```
**Proposed diff:**
```diff
--- a/amlkit/api/routers/reports.py
+++ b/amlkit/api/routers/reports.py
@@ def report_build_view(
     cust_data = queries.customer(db, customer_id, session.org_id)
     if not cust_data:
         return back("/reports", err="Customer not found")
+    from ...reporting.goaml import SUPPORTED_REPORT_TYPES
+    report_type = (report_type or "STR").upper()
+    if report_type not in SUPPORTED_REPORT_TYPES:
+        return back("/reports", err=f"{report_type} reports can't be created in groAML yet. "
+                                    "File them directly on goAML.")
```
Guard on `SUPPORTED_REPORT_TYPES`, not `CREATABLE_REPORT_TYPES`. FFR is freeze-flow-only and
missing from the creatable list, but `report_detail.html:17` sends FFR drafts to
`/reports/build?...&report_type=FFR` for editing. Using the creatable list would break that link.
(The router imports goaml names function-locally, as at line 86.) Test: GET
`/reports/build?customer_id=<id>&report_type=DPMSR` returns 303 to `/reports`. STR and FFR (with a `report_id`) still return 200.

## 3. L-135 (RT1, MEDIUM, product decision): no DPMSR / REAR

**Facts (CONFIRMED).** `SUPPORTED_REPORT_TYPES = {"STR", "SAR", "FFR"}` (`reporting/goaml.py:98`).
The module header lists PNMR, HRCT, HRCA, DPMSR, REAR and DTR (`:1-15`). The landing page sells to
"real-estate brokers, dealers in precious metals and stones" (`landing.html:16`). The KYT comment
calls AED 55,000 "the cash-reporting trigger" (`screening/kyt.py:42-43`).
```
RT1   DPMSR: Report type 'DPMSR' is not supported. Supported types: FFR, SAR, STR
RT1   REAR: Report type 'REAR' is not supported. Supported types: FFR, SAR, STR
```
**Not verifiable here (PLAUSIBLE).** Whether DPMSR/REAR are mandatory for these sectors, and at
what threshold. There is no `corpus/` and no FIU XSD.

**Options for Nadhir:**
- (a) Build DPMSR and REAR (the serialiser stub and builder fields exist). Needs the goAML schema
  and a legal reading. This is a feature, not a fix.
- (b) Until then, say so in the product: a note on `/reports/new` and on the KYT cash alert
  ("DPMSR/REAR: file on goAML directly"). Make the public "goAML reporting" claim name STR/SAR/CNMR.
- Recommended: (b) now, plus L-136. Do (a) once the schema and legal text are in the repo.
  RT1 and compliance item 3.1 (the configurable AED 55,000 threshold) belong in one design decision.

## 4. L-137 (RT3, INFO): HRCT, HRCA and PNMR are listed but not creatable
Same cause as RT1. PNMR is already tracked as CS-14. No separate action. Fold it into the decision in §3.
