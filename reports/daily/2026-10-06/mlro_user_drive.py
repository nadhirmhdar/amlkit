"""MLRO-user walkthrough driver (local, throwaway DB, no production, no /system/*).

Run: AMLKIT_REGISTRATION_INVITE_CODE=test-invite python reports/daily/2026-10-04/mlro_user_drive.py
Drives the app over HTTP (Starlette TestClient) as a user would; writes evidence to out/.
"""
import os, re, sys, json, tempfile, pathlib
os.environ.setdefault("AMLKIT_REGISTRATION_INVITE_CODE", "test-invite")
tmp = pathlib.Path(tempfile.mkdtemp(prefix="mlro-"))
os.environ["AMLKIT_DB"] = str(tmp / "aml.db")
ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests"))
OUT = pathlib.Path(__file__).parent / "mlro-user-evidence"; OUT.mkdir(exist_ok=True)

import pyotp
from fastapi.testclient import TestClient
from amlkit.api.app import app
from amlkit import db as _db
from amlkit.db import connect, upsert_dataset, utcnow
from amlkit.names.arabic import blocking_keys, canonical_key
app.state.limiter.enabled = False

LOG = []
def note(step, status, detail=""):
    LOG.append({"step": step, "status": status, "detail": detail})
    print(f"[{status}] {step} {detail}")

def seed(db_path):
    c = connect(db_path)
    now = utcnow()
    rows = [
        ("eocn", "UAE Local Terrorist List", "AHMED ABD AL-JALEEL AL-HASNAWI", "Person", '["ae"]', "1975-03-12", '["sanction"]', ["أحمد عبد الجليل الحسناوي"]),
        ("un", "UN Consolidated", "Mohammed Ali Hassan Al-Rashid", "Person", '["ir"]', "1968-01-01", '["sanction"]', ["Muhammad Ali Hasan al-Rashid"]),
        ("ofac", "OFAC SDN", "Viktor Petrovich Sokolov", "Person", '["ru"]', "1971-06-30", '["sanction"]', []),
        ("cia", "CIA World Leaders", "Hassan Rouhani Test", "Person", '["ir"]', None, '["role.pep"]', []),
    ]
    for key, title, cap, schema, ctry, dob, topics, aliases in rows:
        ds = upsert_dataset(c, key, title, is_mandatory=True)
        c.execute("UPDATE datasets SET last_refresh=?, entity_count=1 WHERE id=?", (now, ds))
        eid = c.execute("""INSERT INTO entities (dataset_id,source_id,schema_type,caption,countries,birth_date,gender,topics,raw,first_seen,last_seen)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (ds, key.upper()+"-1", schema, cap, ctry, dob, "male", topics, "{}", now, now)).lastrowid
        for nm, nt in [(cap, "primary")] + [(a, "alias") for a in aliases]:
            c.execute("INSERT INTO entity_names (entity_id,name,name_type,canonical_key,script) VALUES (?,?,?,?,?)",
                      (eid, nm, nt, canonical_key(nm), "arabic" if re.search("[؀-ۿ]", nm) else "latin"))
            for t in blocking_keys(nm):
                c.execute("INSERT OR IGNORE INTO name_tokens (token,entity_id) VALUES (?,?)", (t, eid))
    c.commit(); c.close()

def csrf(cl): return cl.cookies.get("amlkit_csrf")
def post(cl, url, **data):
    data.setdefault("csrf_token", csrf(cl))
    return cl.post(url, data=data, follow_redirects=False)
def save(name, r):
    (OUT / name).write_text(r.text if hasattr(r, "text") else str(r), encoding="utf-8")

def stage1():
    seed(os.environ["AMLKIT_DB"])
    cl = TestClient(app, base_url="https://testserver")
    r = cl.get("/register-organization"); save("01_register.html", r)
    r = post(cl, "/register-organization", org_name="Grovisor Test DNFBP", name="Layla MLRO",
             email="layla@mlro-test.local", password="a-strong-password-1", invite_code="test-invite")
    save("02_register_post.html", r)
    # follow redirects manually
    r2 = cl.get(r.headers["location"]) if r.status_code in (302, 303) else r
    save("02b_after_register.html", r2)
    m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r2.text) or re.search(r"/verify-email\?token=([^\"&<\s]+)", r.text)
    note("register org", "worked" if r.status_code in (200, 302, 303) else "broken", f"status={r.status_code} verify_link_on_page={bool(m)}")
    if m:
        r = cl.get(f"/verify-email?token={m.group(1)}", follow_redirects=False)
        note("verify email", "info", f"status={r.status_code} loc={r.headers.get('location')}")
    r = cl.get("/mfa/setup", follow_redirects=False); save("03_mfa_setup.html", r)
    note("mfa setup page", "info", f"status={r.status_code} loc={r.headers.get('location')}")
    if r.status_code == 200:
        secret = re.search(r"\b([A-Z2-7]{32})\b", r.text).group(1)
        r = post(cl, "/mfa/setup", code=pyotp.TOTP(secret).now()); save("04_mfa_backup.html", r)
        note("mfa enrol", "worked" if "backup" in r.text.lower() else "broken", f"status={r.status_code}")
        cl._secret = secret
    return cl


def text(r):
    t = re.sub(r"(?s)<(script|style).*?</\1>", "", r.text)
    t = re.sub(r"<[^>]+>", " ", t)
    import html as _h
    return re.sub(r"\s+", " ", _h.unescape(t))

def flash(r):
    """pull msg/err banner from a redirect location or body"""
    loc = r.headers.get("location", "")
    import urllib.parse as up
    q = up.parse_qs(up.urlparse(loc).query)
    return {k: q[k][0] for k in ("msg", "err") if k in q}

def login(email, pw, secret=None):
    c = TestClient(app, base_url="https://testserver")
    c.get("/login")
    r = post(c, "/login", email=email, password=pw)
    loc = r.headers.get("location")
    if loc == "/mfa/verify" and secret:
        c.get("/mfa/verify")
        r = post(c, "/mfa/verify", code=pyotp.TOTP(secret).now())
        loc = r.headers.get("location")
    return c, r.status_code, loc

def stage2(cl):
    # org profile
    r = post(cl, "/admin/org-profile", org_address="Office 12, Business Bay, Dubai", reporting_person_name="Layla MLRO",
             reporting_person_title="MLRO", reporting_person_phone="+971501234567", goaml_entity_reference="TEST-ORG-0001")
    note("save goAML profile", "info", f"{r.status_code} {flash(r)}")
    # second operator (officer) for four-eyes
    r = post(cl, "/admin/operators", name="Omar Officer", email="omar@mlro-test.local", password="officer-password-1", role="officer")
    note("add officer", "info", f"{r.status_code} {flash(r)}")
    r = post(cl, "/admin/operators", name="Second MLRO", email="mlro2@mlro-test.local", password="mlro2-password-1", role="mlro")
    note("add 2nd MLRO", "info", f"{r.status_code} {flash(r)}")
    adm = cl.get("/admin"); save("10_admin_after_ops.html", adm)
    ids = re.findall(r"/admin/operators/(\d+)/rename", adm.text)
    note("operators listed with Rename", "info", f"ids={ids}")
    return ids


def banner(html):
    return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m)).strip()
            for m in re.findall(r'(?s)<div class="banner (?:ok|err)[^"]*"[^>]*>(.*?)</div>', html)]

def act(cl, url, follow=None, **data):
    """POST like a browser form, follow the 303, return (status, location, banners, page)."""
    r = post(cl, url, **data)
    loc = r.headers.get("location")
    page = None
    if r.status_code in (302, 303) and loc:
        page = cl.get(follow or loc)
        return r.status_code, loc, banner(page.text), page
    return r.status_code, loc, banner(r.text), r

def op_names(cl):
    h = cl.get("/admin").text
    return re.findall(r'aria-label="New name for ([^"]+)"', h), re.findall(r'name="name" value="([^"]*)" aria-label="New name for', h)

def rename_tests(cl, ids):
    mlro_id, officer_id, mlro2_id = ids
    base = f"/admin/operators/{officer_id}/rename"
    cases = [
        ("valid rename", "Omar Al Officer"),
        ("blank", ""),
        ("whitespace only", "     "),
        ("81 chars", "x" * 81),
        ("80 chars", "y" * 80),
        ("html/script", "<script>alert(1)</script>"),
        ("arabic name", "عمر الضابط"),
        ("same as another operator (exact)", "Layla MLRO"),
        ("same as another operator (case/space)", "  layla  mlro "),
        ("control chars / newline", "Omar\nOfficer"),
        ("restore", "Omar Officer"),
    ]
    for label, nm in cases:
        st, loc, b, page = act(cl, base, follow="/admin", name=nm)
        names, _ = op_names(cl)
        note(f"rename: {label}", "info", f"status={st} banners={b} operators_now={[n.split('@')[0] for n in names]}")
        # xss check on rendered page
        if "<script>alert(1)</script>" in cl.get("/admin").text:
            note("rename xss", "broken", "raw <script> in /admin")
    # rename without csrf
    r = cl.post(base, data={"name": "No Csrf"}, follow_redirects=False)
    note("rename without CSRF token", "info", f"status={r.status_code} loc={r.headers.get('location')} body={text(r)[:120]}")
    # nonexistent operator
    st, loc, b, page = act(cl, "/admin/operators/9999/rename", follow="/admin", name="Ghost")
    note("rename nonexistent id", "info", f"status={st} banners={b}")
    # header shows own name after self-rename?
    st, loc, b, page = act(cl, f"/admin/operators/{mlro_id}/rename", follow="/admin", name="Layla R. MLRO")
    hdr = re.findall(r"Layla[^<]{0,20}", cl.get("/dashboard").text)[:3]
    note("self-rename (MLRO renames self)", "info", f"status={st} banners={b} header_shows={hdr}")
    return


def onboard(cl, ref, name, **kw):
    cl.get("/customers/new")
    d = dict(reference=ref, customer_type="natural", full_name=name, nationality="AE", birth_date="1980-01-01",
             purpose_of_relationship="Property purchase", expected_activity="One-off AED 2m transfer",
             source_of_wealth="Salary", source_of_funds="Emirates NBD account")
    d.update(kw)
    r = post(cl, "/customers", **d)
    loc = r.headers.get("location")
    page = cl.get(loc) if loc else r
    return r.status_code, loc, banner(page.text), page

def stage4(cl, ids):
    mlro_id, officer_id, mlro2_id = ids
    # screening
    for q in ["Ahmed Abd Al-Jaleel Al-Hasnawi", "Ahmad Abdul Jalil Hasnawi", "احمد عبد الجليل الحسناوي", "Muhammad Ali Hasan Rashid", "John Smith", "Mohammed Ali"]:
        r = post(cl, "/screen", name=q)
        t = text(r)
        m = re.findall(r"(\d\.\d+|\d{1,3}%)", t)[:4]
        note(f"screen '{q}'", "info", f"status={r.status_code} scores={m} excerpt={t[t.find('Screen')+0:][:0]}")
        save(f"screen_{abs(hash(q))%10000}.html", r)
    # onboard
    cases = [("C-001", "Ahmed Abd Al-Jaleel Al-Hasnawi"), ("C-002", "Muhammad Ali Hasan Al Rashid"), ("C-003", "Fatima Khan"), ("C-004", "Viktor Sokolov")]
    cust = {}
    for ref, nm in cases:
        st, loc, b, page = onboard(cl, ref, nm)
        cust[ref] = loc
        note(f"onboard {nm}", "info", f"status={st} loc={loc} banners={b}")
        save(f"cust_{ref}.html", page)
    a = cl.get("/alerts"); save("20_alerts.html", a)
    t = text(a)
    note("alerts page", "info", t[t.find("Alerts"):][:700])
    return cust


def alert_ids(cl, status="open"):
    h = cl.get(f"/alerts?status={status}").text
    return sorted(set(int(x) for x in re.findall(r"/alerts/(\d+)/(?:disposition|confirm|assign)", h)))

def stage5(cl, ids):
    mlro_id, officer_id, mlro2_id = ids
    open_ids = alert_ids(cl)
    note("open alert ids", "info", str(open_ids))
    # history / audit evidence for the silent C-002 near-miss
    a = text(cl.get("/audit")); note("audit page excerpt", "info", a[a.find("Audit"):][:900])
    # MLRO proposes dismissal of C-001's alert (sanctions)
    cust_alert = None
    for i in open_ids:
        panel = text(cl.get(f"/alerts/{i}/panel"))
        if "C-001" in panel: cust_alert = i
    note("C-001 alert id", "info", str(cust_alert))
    # 1: dismiss without narrative / reason
    st, loc, b, pg = act(cl, f"/alerts/{cust_alert}/disposition", follow="/alerts", status="false_positive", reason_code="different_dob", narrative="")
    note("propose dismissal (sanction) as MLRO #1", "info", f"{st} {b}")
    st_alerts = alert_ids(cl, "pending_review")
    note("pending_review ids", "info", str(st_alerts))
    # 2: same operator tries to confirm own proposal
    st, loc, b, pg = act(cl, f"/alerts/{cust_alert}/confirm", follow="/alerts", agree="yes", narrative="")
    note("self-confirm own dismissal", "info", f"{st} {b}")
    # 3: self-rename then self-confirm (four-eyes by name?)
    st, loc, b, pg = act(cl, f"/admin/operators/{mlro_id}/rename", follow="/admin", name="Layla Renamed")
    note("MLRO renames self mid-review", "info", f"{b}")
    st, loc, b, pg = act(cl, f"/alerts/{cust_alert}/confirm", follow="/alerts", agree="yes", narrative="")
    note("self-confirm AFTER self-rename", "info", f"{st} {b}")
    detail = text(cl.get(f"/alerts/{cust_alert}/panel"))
    note("panel after", "info", detail[:600])
    return cust_alert


def audit_rows(cl, grep):
    t = text(cl.get("/audit?limit=500") if False else cl.get("/audit"))
    return [x for x in re.split(r"(?=20\d\d-\d\d-\d\d \d\d:\d\d:\d\d )", t) if re.search(grep, x)]

def stage6(cl, ids):
    for r in audit_rows(cl, r"rename|operator|alert"): note("audit", "info", r[:260])
    # bulk-dismiss on sanctions alerts for a new matching customer
    st, loc, b, page = onboard(cl, "C-005", "Ahmad Abdul Jalil Hasnawi", birth_date="1990-05-05", nationality="LY")
    note("onboard C-005 (DOB/nat mismatch)", "info", f"{st} {b}")
    cid = int(loc.rsplit("/", 1)[1]) if loc else 5
    note("C-005 alerts", "info", str(alert_ids(cl)))
    st, loc, b, pg = act(cl, "/alerts/bulk-dismiss", follow="/alerts", customer_id=str(cid), reason_code="name_coincidence", back_to="/alerts")
    note("bulk-dismiss sanctions alerts for C-005 (no narrative)", "info", f"{st} {b}")
    note("pending/dismissed after bulk", "info", f"pending={alert_ids(cl,'pending_review')} open={alert_ids(cl)} dismissed={alert_ids(cl,'false_positive')}")
    # second operators log in
    c2, st, loc = login("omar@mlro-test.local", "officer-password-1")
    note("officer login", "info", f"{st} {loc}")
    c3, st, loc = login("mlro2@mlro-test.local", "mlro2-password-1")
    note("2nd MLRO login (before MFA)", "info", f"{st} {loc}")
    r = c2.get("/admin", follow_redirects=False); note("officer GET /admin", "info", f"{r.status_code} {r.headers.get('location')}")
    r = c2.get("/admin/compliance", follow_redirects=False); note("officer GET /admin/compliance", "info", f"{r.status_code} {r.headers.get('location')}")
    r = post(c2, f"/admin/operators/{ids[0]}/rename", name="Hacked"); note("officer POST rename MLRO", "info", f"{r.status_code} {r.headers.get('location')} {text(r)[:100]}")
    return c2, c3, cid


def stage7(cl, ids, c2):
    mlro_id, officer_id, mlro2_id = ids
    # exact-DOB duplicate customer => sanction alert tied to a customer
    st, loc, b, page = onboard(cl, "C-006", "Ahmed Abd Al-Jaleel Al-Hasnawi", birth_date="1975-03-12", nationality="AE")
    cid = int(loc.rsplit("/", 1)[1]); note("onboard C-006 (exact DOB)", "info", f"{b}")
    new = [i for i in alert_ids(cl) if i not in (1, 2)]
    note("C-006 alert ids", "info", str(new))
    # bulk dismiss, no narrative, by single MLRO
    st, loc, b, pg = act(cl, "/alerts/bulk-dismiss", follow="/alerts", customer_id=str(cid), reason_code="name_coincidence", back_to="/alerts")
    note("bulk-dismiss sanctions alert (C-006), MLRO alone, no narrative", "info", f"{st} {b} pending={alert_ids(cl,'pending_review')} dismissed={alert_ids(cl,'false_positive')}")
    # assign to arbitrary name
    if alert_ids(cl):
        i = alert_ids(cl)[0]
        st, loc, b, pg = act(cl, f"/alerts/{i}/assign", follow="/alerts", operator="Nobody Atall")
        note("assign alert to a non-existent operator name", "info", f"{b}")
    # correct four-eyes: MLRO proposes, officer confirms
    # fresh alert: confirm_match path
    rest = alert_ids(cl)
    note("remaining open", "info", str(rest))
    return cid


def stage8(cl, c2, ids, cid):
    # officer confirms pending alert 4
    st, loc, b, pg = act(c2, "/alerts/4/confirm", follow="/alerts", agree="yes", narrative="")
    note("officer confirms MLRO's dismissal (alert 4)", "info", f"{st} {b}")
    t = text(cl.get("/alerts/4/panel")); note("alert 4 panel", "info", t[:500])
    # proposed true_positive without narrative
    st, loc, b, pg = act(cl, "/alerts/1/disposition", follow="/alerts", status="true_positive", reason_code="confirmed_match", narrative="")
    note("confirm match w/o narrative", "info", f"{b}")
    st, loc, b, pg = act(cl, "/alerts/1/disposition", follow="/alerts", status="escalated", reason_code="insufficient_data", narrative="Name only hit; no ID provided")
    note("escalate with narrative", "info", f"{b}")
    # transactions on C-001 (customer id 1)
    cl.get("/customers/1")
    for amt, meth in [(60000, "cash"), (9000, "cash"), (9500, "cash"), (9800, "cash")]:
        st, loc, b, pg = act(cl, "/customers/1/transactions", follow="/customers/1", direction="inbound", method=meth, amount=str(amt), counterparty="Test Cpty", counterparty_country="IR", txn_date="2026-10-01")
        note(f"txn {amt} {meth}", "info", f"{st} {b}")
    t = text(cl.get("/customers/1")); i = t.find("Transaction monitoring"); note("customer 1 txn section", "info", t[i:i+1200])
    return


def stage9(cl):
    for amt in (52000, 53000, 54000):
        st, loc, b, pg = act(cl, "/customers/1/transactions", follow="/customers/1", direction="outbound", method="cash", amount=str(amt), counterparty_name="Gulf Traders", counterparty_country="AE", occurred_at="2026-10-02")
        note(f"structuring txn {amt}", "info", f"{b}")
    r = cl.get("/reports/new"); save("30_reports_new.html", r)
    t = text(r); note("reports/new", "info", t[t.find("New report"):][:500] if "New report" in t else t[300:900])
    opts = re.findall(r'<option value="([^"]+)"', r.text); note("report types/customers options", "info", str(opts)[:300])
    b = cl.get("/reports/build?customer_id=1&report_type=STR"); save("31_str_builder.html", b)
    note("builder status", "info", str(b.status_code))
    vals = dict(re.findall(r'name="(reporting_entity_name|entity_reference|reporter_name|reporter_email|first_name|last_name|nationality|birth_date|id_type|id_number)" value="([^"]*)"', b.text))
    note("STR builder prefill", "info", json.dumps(vals))
    return b


def stage10(cl, ids):
    post(cl, "/admin/org-profile", org_address="Office 12, Business Bay, Dubai", reporting_person_name="Layla MLRO",
         reporting_person_title="MLRO", reporting_person_phone="+971501234567", goaml_entity_reference="TEST-ORG-0001")
    b = cl.get("/reports/build?customer_id=1&report_type=STR")
    d = dict(customer_id="1", report_type="STR", reporting_entity_name="Grovisor Test DNFBP", entity_reference="TEST-ORG-0001",
             reporter_name="Layla MLRO", reporter_email="layla@mlro-test.local", first_name="Ahmed", last_name="Abd Al-Jaleel Al-Hasnawi",
             nationality="AE", birth_date="1980-01-01", gender="male", id_type="Passport", id_number="P1234567",
             amount="60000", transaction_type="cash_deposit", transaction_date="2026-10-01", source_account="", destination_account="",
             reason_description="Customer name matches UAE Local Terrorist List entry; large cash deposit from Iran-linked counterparty.",
             action_taken="Onboarding paused; funds not released.", evidence_pack_attached="yes")
    st, loc, bn, pg = act(cl, "/reports", **d)
    note("create STR draft", "info", f"{st} {loc} {bn}")
    save("32_report_detail.html", pg)
    m = re.search(r"/reports/(\d+)", loc or "")
    rid = m.group(1) if m else "1"
    t = text(pg); note("report detail", "info", t[t.find("Report"):][:700])
    r = cl.get(f"/reports/{rid}/export", follow_redirects=False)
    note("export before submit", "info", f"{r.status_code} {r.headers.get('content-type')} {r.text[:200]!r}")
    st, loc, bn, pg = act(cl, f"/reports/{rid}/submit", follow=f"/reports/{rid}")
    note("submit/finalise", "info", f"{st} {loc} {bn}")
    r = cl.get(f"/reports/{rid}/export", follow_redirects=False)
    note("export after submit", "info", f"{r.status_code} {r.headers.get('content-type')} {r.headers.get('content-disposition')}")
    (OUT / "str_export.xml").write_text(r.text, encoding="utf-8")
    return rid


def stage11(cl, rid):
    # can a finalised report with the missing account be repaired?
    b = cl.get(f"/reports/build?customer_id=1&report_type=STR&report_id={rid}")
    note("edit finalised report (builder)", "info", f"{b.status_code} {text(b)[300:420]}")
    d = dict(customer_id="1", report_type="STR", report_id=rid, reporting_entity_name="Grovisor Test DNFBP", entity_reference="TEST-ORG-0001",
             reporter_name="Layla MLRO", reporter_email="layla@mlro-test.local", first_name="Ahmed", last_name="Abd Al-Jaleel Al-Hasnawi",
             nationality="AE", birth_date="1980-01-01", gender="male", id_type="Passport", id_number="P1234567",
             amount="60000", transaction_type="cash_deposit", transaction_date="2026-10-01", source_account="AE070331234567890123456", destination_account="AE460090000000123456789",
             reason_description="Edited after finalise", action_taken="x", evidence_pack_attached="yes")
    st, loc, bn, pg = act(cl, "/reports", **d)
    note("re-save finalised report", "info", f"{st} {loc} {bn}")
    r = cl.get(f"/reports/{rid}/export")
    note("export after repair attempt", "info", f"{r.status_code} {r.text[:120]!r}")
    # new draft with accounts
    d.pop("report_id"); d["reason_description"] = "Customer name matches UAE Local Terrorist List entry; large cash deposit."
    st, loc, bn, pg = act(cl, "/reports", **d)
    rid2 = re.search(r"/reports/(\d+)", loc).group(1)
    st, loc, bn, pg = act(cl, f"/reports/{rid2}/submit", follow=f"/reports/{rid2}")
    note("submit report 2", "info", f"{bn}")
    r = cl.get(f"/reports/{rid2}/export")
    note("export report 2", "info", f"{r.status_code} {r.headers.get('content-type')} {r.headers.get('content-disposition')} len={len(r.text)}")
    (OUT / "str_export.xml").write_text(r.text, encoding="utf-8")
    return rid2

if __name__ == "__main__" and not os.environ.get("ONLY"):
    cl = stage1()
    ids = stage2(cl)
    stage4(cl, ids)
    stage5(cl, ids)
    c2, c3, cid = stage6(cl, ids)
    stage7(cl, ids, c2)
    stage8(cl, c2, ids, cid)
    stage9(cl)
    rid = stage10(cl, ids)
    stage11(cl, rid)
    json.dump(LOG, open(OUT / "log11.json", "w"), indent=1)

# ---------------------------------------------------------------- 2026-10-05 additions
def mobile_paging():
    """Mobile API alert paging (#402) + web queue ordering, on a fresh org."""
    LOG.clear()
    cl = stage1()
    for i in range(30):
        onboard(cl, f"S-{i:03d}", "Ahmed Abd Al-Jaleel Al-Hasnawi", birth_date="1980-01-01")      # sanction, ~0.85
    for i in range(30):
        onboard(cl, f"P-{i:03d}", "Hassan Rouhani Test", birth_date="", nationality="IR")          # PEP, 1.0
    web = cl.get("/alerts?status=open")
    order = re.findall(r"<h\\d[^>]*>\\s*([^<]{3,60}?)\\s*</h\\d>|class=\"tag[^\"]*\">\\s*(sanction|pep|proliferation)", web.text)
    note("web /alerts first categories", "info", str([c for _, c in order][:8]))
    m = TestClient(app, base_url="https://testserver")
    r = m.post("/api/v1/auth/login", json={"email": "layla@mlro-test.local", "password": "a-strong-password-1"})
    tok = r.json()["token"]; H = {"Authorization": f"Bearer {tok}"}
    note("mobile login", "info", f"{r.status_code} mfa_required={r.json().get('mfa_required')}")
    r = m.get("/api/v1/alerts", headers=H); note("alerts while MFA-locked", "info", f"{r.status_code} {r.text[:100]}")
    r = m.post("/api/v1/auth/mfa/verify", json={"code": pyotp.TOTP(cl._secret).now()}, headers=H)
    note("mobile mfa verify", "info", f"{r.status_code}")
    seen = []
    for off in (0, 20, 40):
        r = m.get(f"/api/v1/alerts?limit=20&offset={off}", headers=H).json()
        cats = [(a["category"], a["score"]) for a in r["alerts"]]
        note(f"mobile page offset={off}", "info", f"total={r['total']} truncated={r['truncated']} cats={[c for c,_ in cats][:3]}..{[c for c,_ in cats][-3:]} scores={[s for _,s in cats][:2]}..{[s for _,s in cats][-2:]}")
        seen += [a["id"] for a in r["alerts"]]
    note("paging overlap/skip", "info", f"unique={len(set(seen))} of {len(seen)}")
    for q in ("limit=0", "limit=-5", "limit=abc", "offset=-1", "limit=9999"):
        r = m.get(f"/api/v1/alerts?{q}", headers=H)
        note(f"mobile alerts?{q}", "info", f"{r.status_code} {r.text[:90]}")
    d = m.get("/api/v1/dashboard", headers=H).json()
    note("mobile dashboard", "info", f"cap={d.get('alerts_cap')} truncated={d.get('alerts_truncated')} open_total={d.get('alert_open_total')} open_rows={len(d.get('open_alerts', []))}")
    json.dump(LOG, open(OUT / "log_mobile.json", "w"), indent=1)

if __name__ == "__main__" and os.environ.get("ONLY") == "mobile":
    mobile_paging()

def web_order():
    LOG.clear()
    cl = stage1()
    for i in range(30):
        onboard(cl, f"S-{i:03d}", "Ahmed Abd Al-Jaleel Al-Hasnawi", birth_date="1980-01-01")
    for i in range(30):
        onboard(cl, f"P-{i:03d}", "Hassan Rouhani Test", birth_date="", nationality="IR")
    t = text(cl.get("/alerts?status=open"))
    items = re.findall(r"(AHMED ABD AL-JALEEL AL-HASNAWI|Hassan Rouhani Test|HASSAN ROUHANI TEST)\s+(sanction|pep|role\.pep|[a-z ]{3,12})\s+(\d\.\d+)", t, re.I)
    note("web queue order (first 25)", "info", str([(a[:6], b, c) for a, b, c in items][:25]))
    d = text(cl.get("/dashboard")); i = d.find("open"); note("web dashboard text", "info", d[i:i+400])

if __name__ == "__main__" and os.environ.get("ONLY") == "web":
    web_order()

def new_workflows():
    LOG.clear()
    anon = TestClient(app, base_url="https://testserver")
    r = anon.get("/login"); save("login.html", r)
    t = text(r)
    note("sign-in page (anonymous)", "info", f"{r.status_code} list names present={[n for n in ('OFAC','UN Consolidated','EOCN','Local Terrorist','sanctions list') if n.lower() in t.lower()]} text={t[:520]}")
    note("signin-strands.js served", "info", str(anon.get("/static/js/signin-strands.js").status_code))
    cl = stage1()
    # PEP / high-risk onboarding
    st, loc, b, pg = onboard(cl, "E-001", "Hassan Rouhani Test", nationality="IR", birth_date="1948-11-12", sector="real_estate", jurisdiction_tier="high", cash_level="predominantly_cash", risk_level="")
    note("onboard PEP-name + IR + high-risk inputs", "info", f"{b}")
    t = text(pg); i = t.find("Risk assessment"); note("risk assessment panel", "info", t[i:i+500])
    # UBO add & screen (listed UBO)
    st, loc, b, pg = onboard(cl, "E-002", "Gulf Holdings LLC", customer_type="legal")
    cid = int(loc.rsplit("/", 1)[1]); note("onboard legal entity", "info", f"{st} {b}")
    st, loc, b, pg = act(cl, f"/customers/{cid}/ubo", follow=f"/customers/{cid}", person_name="Viktor Petrovich Sokolov", ownership_pct="60", control_type="ownership")
    note("add UBO matching OFAC entry", "info", f"{st} {b}")
    st, loc, b, pg = act(cl, f"/customers/{cid}/ubo", follow=f"/customers/{cid}", person_name="Nobody Clean", ownership_pct="45", control_type="ownership")
    note("add UBO to push total over 100%", "info", f"{b}")
    t = text(cl.get(f"/customers/{cid}")); i = t.find("Beneficial owners"); note("UBO section", "info", t[i:i+500])
    note("alerts after UBO", "info", str(alert_ids(cl)))
    # close / reactivate
    st, loc, b, pg = act(cl, f"/customers/{cid}/close", follow=f"/customers/{cid}", exit_reason="str_filed", exit_note="")
    note("close relationship (STR filed)", "info", f"{st} {b}")
    t = text(cl.get(f"/customers/{cid}")); note("closed page marker", "info", str("closed" in t.lower()) + " " + t[t.find("Reactivate"):][:160])
    st, loc, b, pg = act(cl, f"/customers/{cid}/reactivate", follow=f"/customers/{cid}")
    note("reactivate", "info", f"{st} {b}")
    st, loc, b, pg = act(cl, f"/customers/{cid}/close", follow=f"/customers/{cid}", exit_reason="bogus")
    note("close with invalid reason", "info", f"{st} {b}")
    # F4 re-check on new master
    ids = stage2(cl)
    for nm in ("LAYLA MLRO", "layla mlro"):
        st, loc, b, pg = act(cl, f"/admin/operators/{ids[1]}/rename", follow="/admin", name=nm)
        note(f"F4 rename officer to {nm!r}", "info", f"{b}")
    json.dump(LOG, open(OUT / "log_new_workflows.json", "w"), indent=1)

if __name__ == "__main__" and os.environ.get("ONLY") == "new":
    new_workflows()

def pep_onboard():
    LOG.clear()
    cl = stage1()
    st, loc, b, pg = onboard(cl, "E-001", "Hassan Rouhani Test", nationality="IR", birth_date="", jurisdiction_tier="fatf_greylist", cash_level="predominantly_cash")
    note("onboard PEP-list name, grey-list country, cash-heavy", "info", f"{st} {b}")
    t = text(pg); i = t.find("Risk assessment"); note("risk panel", "info", t[i:i+380])
    j = t.find("Alerts"); note("alerts queue", "info", str(alert_ids(cl)))
    a = text(cl.get(f"/alerts/{alert_ids(cl)[0]}/panel")) if alert_ids(cl) else ""
    note("PEP alert panel", "info", a[:420])
    al = text(cl.get("/alerts")); k = al.find("Hassan"); note("PEP alert row (wording)", "info", al[k-60:k+520] if k>0 else al[300:700])
if __name__ == "__main__" and os.environ.get("ONLY") == "pep":
    pep_onboard()
    json.dump(LOG, open(OUT / "log_pep.json", "w"), indent=1)

def run2():
    """Second 2026-10-05 run: single-operator mode, review-trail wording, org-profile save, rescreen vs pending_review."""
    LOG.clear()
    from amlkit.db import connect
    cl = stage1(); ids = stage2(cl)
    dbp = os.environ["AMLKIT_DB"]
    ref = lambda: dict(connect(dbp).execute("select goaml_entity_reference ref, org_address addr from organizations").fetchone())
    note("goAML profile after stage2", "info", str(ref()))
    # (a) browser-style re-save: the form renders the reference blank, so a browser posts it blank
    st, loc, b, pg = act(cl, "/admin/org-profile", follow="/admin", org_address="New address, Dubai", reporting_person_name="Layla MLRO",
                         reporting_person_title="MLRO", reporting_person_phone="+971501234567", goaml_entity_reference="")
    note("re-save profile with the (blank) form value", "info", f"{b} -> db {ref()}")
    # (b) four-eyes via rename: trail wording
    st, loc, b, pg = onboard(cl, "R-001", "Ahmed Abd Al-Jaleel Al-Hasnawi", birth_date="1975-03-12")
    cid = int(loc.rsplit("/", 1)[1]); aid = alert_ids(cl)[-1]
    def trail(c):
        t = text(cl.get(f"/customers/{c}")); i = t.find("propose"); return re.sub(r"\s+", " ", t[max(0, i-60):i+420]) if i >= 0 else t[:0]
    act(cl, f"/alerts/{aid}/disposition", follow="/alerts", status="false_positive", reason_code="different_dob", narrative="")
    act(cl, f"/admin/operators/{ids[0]}/rename", follow="/admin", name="Someone Else")
    st, loc, b, pg = act(cl, f"/alerts/{aid}/confirm", follow="/alerts", agree="yes", narrative="")
    note("rename-bypass confirm", "info", str(b))
    note("review trail shown to an inspector (rename bypass)", "info", trail(cid))
    # (c) honest single-operator mode on a fresh alert
    st, loc, b, pg = act(cl, "/admin/single-operator", follow="/admin", mode="on")
    note("turn single-operator mode on", "info", str(b))
    st, loc, b, pg = onboard(cl, "R-002", "Ahmed Abd Al-Jaleel Al-Hasnawi", birth_date="1975-03-12")
    cid2 = int(loc.rsplit("/", 1)[1]); aid2 = alert_ids(cl)[-1]
    st, loc, b, pg = act(cl, f"/alerts/{aid2}/disposition", follow="/alerts", status="false_positive", reason_code="different_dob", narrative="")
    note("single-operator dismissal banner", "info", str(b))
    note("review trail (single-operator mode)", "info", trail(cid2) or text(cl.get(f"/customers/{cid2}"))[:0])
    au = [r for r in audit_rows(cl, r"alert\.(propose|confirm|dismiss|disposition)") ][:3]
    for r in au: note("audit row", "info", r[:300])
    act(cl, "/admin/single-operator", follow="/admin", mode="off")
    # (d) rescreen while a dismissal awaits review
    st, loc, b, pg = onboard(cl, "R-003", "Ahmed Abd Al-Jaleel Al-Hasnawi", birth_date="1975-03-12")
    aid3 = alert_ids(cl)[-1]
    act(cl, f"/alerts/{aid3}/disposition", follow="/alerts", status="false_positive", reason_code="different_dob", narrative="")
    before = (alert_ids(cl), alert_ids(cl, "pending_review"))
    st, loc, b, pg = act(cl, "/admin/rescreen", follow="/admin")
    after = (alert_ids(cl), alert_ids(cl, "pending_review"))
    note("rescreen with a pending_review dismissal", "info", f"{b} open/pending before={before} after={after}")
    json.dump(LOG, open(OUT / "log_run2.json", "w"), indent=1)

if __name__ == "__main__" and os.environ.get("ONLY") == "run2":
    run2()

# ---------------------------------------------------------------- 2026-10-06 additions
def freeze_flow():
    """Not exercised before: confirmed match -> freeze obligation -> execute -> report -> resolve; plus /adverse-media (#403) and rescreen on an empty org."""
    LOG.clear()
    cl = stage1(); ids = stage2(cl)
    # rescreen on an org with NO customers: does the button report success?
    st, loc, b, pg = act(cl, "/admin/rescreen", follow="/admin")
    note("rescreen, org with zero customers", "info", str(b))
    st, loc, b, pg = onboard(cl, "F-001", "Ahmed Abd Al-Jaleel Al-Hasnawi", birth_date="1975-03-12")
    cid = int(loc.rsplit("/", 1)[1]); aid = alert_ids(cl)[-1]
    st, loc, b, pg = act(cl, "/admin/rescreen", follow="/admin")
    note("rescreen, 1 customer", "info", str(b))
    # disposition: confirmed match
    st, loc, b, pg = act(cl, f"/alerts/{aid}/disposition", follow="/alerts", status="true_positive", reason_code="confirmed_match", narrative="Name, DOB and nationality match the UAE Local Terrorist List entry.")
    note("confirm match (true positive) with narrative", "info", str(b))
    fo = cl.get("/freeze-obligations"); save("fo_list.html", fo)
    t = text(fo); i = t.find("Freeze"); note("freeze obligations list", "info", t[t.find("Obligations", 300):][:700])
    fids = sorted(set(int(x) for x in re.findall(r"/freeze-obligations/(\d+)", fo.text)))
    note("freeze ids", "info", str(fids))
    if not fids:
        note("no freeze obligation after confirmed match", "info", "stopping freeze walk")
        return
    fid = fids[0]
    d = cl.get(f"/freeze-obligations/{fid}"); save("fo_detail.html", d)
    td = text(d); j = td.find("Freeze"); note("freeze detail", "info", re.sub(r"\s+", " ", td[td.find("Log out", 300):][:1100]))
    opts = re.findall(r'<option value="([^"]+)"', d.text); note("detail option values", "info", str(opts)[:300])
    r = cl.get(f"/freeze-obligations/{fid}/execute", follow_redirects=False); note("GET execute form", "info", f"{r.status_code}")
    # execute freeze (blank asset first)
    st, loc, b, pg = act(cl, f"/freeze-obligations/{fid}/execute", follow=f"/freeze-obligations/{fid}", asset_type_1="bank_account", asset_identifier_1="", asset_amount_1="", notes="")
    note("execute freeze with no asset identifier", "info", f"{st} {b}")
    st, loc, b, pg = act(cl, f"/freeze-obligations/{fid}/execute", follow=f"/freeze-obligations/{fid}", asset_type_1="bank_account", asset_identifier_1="AE070331234567890123456", asset_amount_1="25000", notes="Account frozen 10:15, bank notified.")
    note("execute freeze with an account", "info", f"{st} {b}")
    td = text(cl.get(f"/freeze-obligations/{fid}")); note("freeze detail after execute", "info", re.sub(r"\s+", " ", td[td.find("Log out", 300):][:900]))
    st, loc, b, pg = act(cl, f"/freeze-obligations/{fid}/file-ffr", follow=f"/freeze-obligations/{fid}", reporter_email="layla@mlro-test.local")
    note("file FFR/CNMR report", "info", f"{st} {loc} {b}")
    td = text(cl.get(f"/freeze-obligations/{fid}")); note("freeze detail after report", "info", re.sub(r"\s+", " ", td[td.find("Log out", 300):][:700]))
    st, loc, b, pg = act(cl, f"/freeze-obligations/{fid}/resolve", follow=f"/freeze-obligations/{fid}", resolution_reason="bogus", authority_ref="", notes="")
    note("resolve with invalid reason", "info", f"{st} {b}")
    # adverse media list (#403)
    am = cl.get("/adverse-media"); ta = text(am)
    note("/adverse-media (empty state)", "info", f"{am.status_code} " + re.sub(r"\s+", " ", ta[ta.find("Log out", 300):][:520]))
    o = TestClient(app, base_url="https://testserver").get("/adverse-media", follow_redirects=False)
    note("/adverse-media anonymous", "info", f"{o.status_code} {o.headers.get('location')}")
    json.dump(LOG, open(OUT / "log_freeze.json", "w"), indent=1)

if __name__ == "__main__" and os.environ.get("ONLY") == "freeze":
    freeze_flow()

def unicode_variants():
    """#425: names pasted from PDFs (presentation forms, zero-width chars) must still screen."""
    import unicodedata
    LOG.clear()
    cl = stage1()
    def presentation(s):
        out = []
        for ch in s:
            alt = [chr(c) for c in range(0xFB50, 0xFEFF) if unicodedata.normalize("NFKC", chr(c)) == ch]
            out.append(alt[0] if alt else ch)
        return "".join(out)
    cases = {
        "plain Arabic alias": "أحمد عبد الجليل الحسناوي",
        "Arabic presentation forms (copy-paste from PDF)": presentation("أحمد عبد الجليل الحسناوي"),
        "Latin + zero-width space": "Ahmed​ Abd Al-Jaleel Al-Hasnawi",
        "Latin + zero-width joiner inside a token": "Ahmed Abd Al‍Jaleel Al-Hasnawi",
        "Latin + BOM": "﻿Ahmed Abd Al-Jaleel Al-Hasnawi",
        "fullwidth Latin": "Ａｈｍｅｄ Ａｂｄ Ａｌ-Ｊａｌｅｅｌ Ａｌ-Ｈａｓｎａｗｉ",
        "extra middle token": "Ahmed Mohammed Abd Al-Jaleel Al-Hasnawi",
    }
    for label, q in cases.items():
        r = post(cl, "/screen", name=q); t = text(r)
        hit = re.search(r"(\d+) match\(es\) for", t)
        note(f"screen: {label}", "info", f"matches={hit.group(1) if hit else ('none' if 'No match' in t else '?')} repr={q.encode('unicode_escape').decode()[:60]}")
    json.dump(LOG, open(OUT / "log_unicode.json", "w"), indent=1)

if __name__ == "__main__" and os.environ.get("ONLY") == "unicode":
    unicode_variants()

def csrf_and_draft_export():
    LOG.clear()
    cl = stage1()
    r = cl.post("/admin/org-profile", data={"org_address": "x", "goaml_entity_reference": "EVIL-REF"}, follow_redirects=False)
    note("POST /admin/org-profile without CSRF token", "info", f"{r.status_code} {text(r)[:90]}")
    r = cl.post("/logout", data={}, follow_redirects=False)
    note("POST /logout without CSRF token", "info", f"{r.status_code} {r.headers.get('location')}")
    r = cl.get("/dashboard", follow_redirects=False)
    note("still signed in after tokenless logout", "info", str(r.status_code))
    # incomplete draft: the 'Download goAML XML' link
    onboard(cl, "D-001", "Fatima Khan")
    d = dict(customer_id="1", report_type="STR", reporting_entity_name="Grovisor Test DNFBP", entity_reference="TEST", reporter_name="L", reporter_email="l@x.ae",
             first_name="Fatima", last_name="Khan", nationality="AE", reason_description="r", action_taken="a")
    st, loc, b, pg = act(cl, "/reports", **d)
    rid = re.search(r"/reports/(\d+)", loc).group(1)
    link = re.findall(r'href="(/reports/\d+/export)"', pg.text)
    r = cl.get(f"/reports/{rid}/export", follow_redirects=False)
    note("incomplete draft: Download goAML XML", "info", f"link_on_page={bool(link)} {r.status_code} {r.headers.get('content-type')} {r.text[:130]!r}")
    json.dump(LOG, open(OUT / "log_csrf_export.json", "w"), indent=1)

if __name__ == "__main__" and os.environ.get("ONLY") == "csrf":
    csrf_and_draft_export()
