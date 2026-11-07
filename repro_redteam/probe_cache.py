import sys, gc, tempfile, os; sys.path.insert(0,__import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))
from amlkit.db import connect, utcnow
from amlkit.screening import kyt
d = tempfile.mkdtemp(); p = os.path.join(d,"a.db")
c0 = connect(p); c0.execute("INSERT INTO organizations (name,slug,status,created_at) VALUES ('t','t','active',?)",(utcnow(),)); c0.commit(); c0.close()
kyt._clear_config_cache()
# Request 1: a worker reads config (threshold 55,000) and its conn closes at request end
c1 = connect(p); print("req1 threshold:", kyt.get_rule_config(c1,1)["large_cash_threshold_aed"]); id1=id(c1); c1.close(); del c1; gc.collect()
# MLRO lowers the threshold via ANOTHER worker/process: simulate by writing straight to DB (other process => no cache invalidation here)
cw = connect(p); cw.execute("INSERT INTO org_settings (org_id, kyt_large_cash_threshold, updated_at) VALUES (1, 10000, ?) ON CONFLICT(org_id) DO UPDATE SET kyt_large_cash_threshold=10000", (utcnow(),)); cw.commit(); cw.close(); del cw; gc.collect()
hits=0; N=200
for i in range(N):
    c = connect(p)
    v = kyt.get_rule_config(c,1)["large_cash_threshold_aed"]
    if v != 10000: hits+=1
    c.close(); del c; gc.collect()
print(f"stale (55,000 instead of 10,000) on {hits}/{N} fresh connections; id reused from req1: ", end="")
c = connect(p); print(id(c)==id1); c.close()
# NaN threshold
c = connect(p)
try:
    kyt.save_rule_config(c,1,{"large_cash_threshold_aed": float("nan")}); c.commit(); print("NaN threshold ACCEPTED by save_rule_config")
    kyt._clear_config_cache(); print("effective after NaN:", kyt.get_rule_config(c,1)["large_cash_threshold_aed"])
except Exception as e: print("NaN threshold rejected/crashed:", type(e).__name__, e)
