import sys, math; sys.path.insert(0,__import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))
from datetime import datetime, timedelta, timezone
from amlkit.db import connect, utcnow
from amlkit.cases.manager import record_transaction
from amlkit.screening import kyt
def fresh():
    c = connect(":memory:"); now = utcnow()
    c.execute("INSERT INTO organizations (name,slug,status,created_at) VALUES ('t','t','active',?)",(now,))
    for i in (1,2):
        c.execute("""INSERT INTO customers (org_id,reference,customer_type,full_name,canonical_key,status,onboarded_at,created_at,updated_at)
                  VALUES (1,?, 'natural','X','x','active',?,?,?)""",(f"C{i}",now,now,now))
    c.commit(); kyt._clear_config_cache(); return c
T0 = datetime(2026,9,1,9,0,tzinfo=timezone.utc)
def at(d, h=0): return (T0+timedelta(days=d, hours=h)).isoformat()
def run(label, txns, cust=1, **kw):
    c = fresh(); out=[]
    for t in txns:
        try:
            _, trig = record_transaction(c, cust, 1, direction=t.get("dir","in"), method=t.get("m","cash"), amount=t["amt"], amount_aed=t.get("aed"), currency=t.get("cur","AED"), occurred_at=t["at"])
            out.append([r.rule_key for r in trig])
        except Exception as e: out.append(f"ERR {type(e).__name__}: {e}")
    print(f"{label:55s} {out}")
cash=lambda amt, d, **k: {"amt":amt,"at":at(d),**k}
run("baseline 2x54,999 same day cash", [cash(54999,0), cash(54999,0)])
run("slow: 54,999 every 8 days x4", [cash(54999,8*i) for i in range(4)])
run("slow: 54,999 every 7.1 days x4", [{"amt":54999,"at":at(7*i,2*i)} for i in range(4)])
run("out-of-order: later first, then earlier", [cash(54999,5), cash(54999,0)])
run("in-order same data", [cash(54999,0), cash(54999,5)])
run("wire 54,999 x5 same day", [{"amt":54999,"m":"wire","at":at(0,i)} for i in range(5)])
run("wire 54,999 x5/day for 3 days (15 txns)", [{"amt":54999,"m":"wire","at":at(d,i)} for d in range(3) for i in range(5)])
run("cash 54,999 + wire 54,999 (mixed)", [cash(54999,0), {"amt":54999,"m":"wire","at":at(0,1)}])
run("cash in 54,999 + cash out 54,999", [cash(54999,0), cash(54999,0,dir="out")])
run("cash 30k + cheque 30k", [cash(30000,0), {"amt":30000,"m":"cheque","at":at(0,1)}])
run("NaN amount", [{"amt":float('nan'),"at":at(0)}])
run("inf amount", [{"amt":float('inf'),"at":at(0)}])
run("1e30 amount", [{"amt":1e30,"at":at(0)}])
run("NaN amount_aed (amount real)", [{"amt":100000,"aed":float('nan'),"at":at(0)}])
run("AED=100,000 but amount_aed=1", [{"amt":100000,"aed":1.0,"at":at(0)}])
run("negative amount_aed offsets: 54,999,54,999,-60,000", [cash(54999,0), {"amt":1,"cur":"USD","aed":-60000.0,"at":at(0,1)}, cash(54999,0)])
run("zero amount_aed", [{"amt":100000,"cur":"USD","aed":0.0,"at":at(0)}])
run("54,999.999 rounds?", [cash(54999.999,0)])
run("55,000 exact", [cash(55000,0)])
run("TZ: +04:00 string", [{"amt":54999,"at":"2026-09-01T23:00:00+04:00"},{"amt":54999,"at":"2026-09-08T01:00:00+04:00"}])
run("space-separated ts", [{"amt":54999,"at":"2026-09-01 10:00:00"},{"amt":54999,"at":"2026-09-01 12:00:00"}])
run("future dated occurred_at (year 2099) then normal", [{"amt":54999,"at":"2099-01-01T00:00:00+00:00"},cash(54999,0)])
run("garbage occurred_at", [{"amt":54999,"at":"yesterday"}])
run("velocity: 6 tiny cash in 24h", [{"amt":10,"at":at(0,i)} for i in range(6)])
run("velocity evasion: 5 per 24h sliding for 3 days", [{"amt":10,"at":at(0,i*4.9)} for i in range(15)])
run("split across 2 customer records (27,500 x2 each)", [cash(30000,0)], cust=1)
c = fresh()
r1 = record_transaction(c,1,1,direction="in",method="cash",amount=30000,occurred_at=at(0))[1]
r2 = record_transaction(c,2,1,direction="in",method="cash",amount=30000,occurred_at=at(0,1))[1]
print("split across customer 1 & 2 (same person, duplicate record):", [x.rule_key for x in r1],[x.rule_key for x in r2])
