exec(open(__import__('os').path.join(__import__('os').path.dirname(__file__),'probe_e2e.py')).read().split("def hit")[0])
from amlkit.cases.manager import add_ubo, ownership_state
from amlkit.match.engine import rescreen_all
now = utcnow()
c.execute("""INSERT INTO customers (org_id,reference,customer_type,full_name,canonical_key,status,onboarded_at,created_at,updated_at)
 VALUES (1,'L1','legal','Clean Trading LLC','clean trading','active',?,?,?)""",(now,now,now)); c.commit()
S = "BILAL ALI AL-WAFI"   # listed in synthetic watchlist
cases = [("24.99% owner", dict(ownership_pct=24.99)), ("nominee flag", dict(ownership_pct=60, is_nominee=True)),
         ("director (control_type=director)", dict(control_type="director")), ("25% owner (UBO)", dict(ownership_pct=25))]
for label, kw in cases:
    c.execute("DELETE FROM ubo_links"); c.commit()
    add_ubo(c, 1, org_id=1, person_name=S, **kw)
    r = rescreen_all(c, 1)
    print(f"{label:35s} rescreen -> screened={r['screened']} alerts={r['alerts']}   is_ubo={c.execute('select is_ubo from ubo_links').fetchone()[0]}")
# cycle reachability
c.execute("DELETE FROM ubo_links"); c.commit()
a = add_ubo(c,1,org_id=1,person_name="A One",ownership_pct=10)
try: b = add_ubo(c,1,org_id=1,person_name="B Two",ownership_pct=10,parent_ubo_id=a); print("child ok", b)
except Exception as e: print("child err", e)
for bad in (a, 9999):
    try: add_ubo(c,1,org_id=1,person_name="C",parent_ubo_id=bad); print("parent", bad, "accepted")
    except Exception as e: print("parent", bad, "->", e)
import re,subprocess
print(subprocess.run("grep -rn 'UPDATE ubo_links' /home/user/amlkit/amlkit | head", shell=True, capture_output=True, text=True).stdout or "no code path UPDATEs ubo_links.parent_ubo_id => cycles unreachable")
