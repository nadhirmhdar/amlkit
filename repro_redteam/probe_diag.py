exec(open(__import__('os').path.join(__import__('os').path.dirname(__file__),'probe_e2e.py')).read().split("def hit")[0])
import time
from amlkit.cases.manager import add_ubo
from amlkit.cases.diagram import generate_ubo_diagram
now=utcnow()
c.execute("""INSERT INTO customers (org_id,reference,customer_type,full_name,canonical_key,status,onboarded_at,created_at,updated_at)
 VALUES (1,'L1','legal','Evil <b>&amp; "Co" </FONT><IMG SRC="file:///etc/passwd"/>','x','active',?,?,?)""",(now,now,now)); c.commit()
for nm in ['</FONT></TD></TR></TABLE>><script>alert(1)</script>', "O'Brien & <Sons>", '<IMG SRC="http://evil.example/x.png"/>', 'a'*5000]:
    add_ubo(c,1,org_id=1,person_name=nm,control_type="director")
svg = generate_ubo_diagram(c,1,1)
print("svg is None:", svg is None)
if svg:
    import re
    print("contains <script:", "<script" in svg.lower(), "| <image/<img:", bool(re.search(r"<image|<img|xlink:href=\"(http|file)", svg, re.I)), "| len", len(svg))
t=time.time()
for i in range(2000): add_ubo(c,1,org_id=1,person_name=f"Person {i}",control_type="director")
t1=time.time(); svg = generate_ubo_diagram(c,1,1); print(f"2000 UBO rows: render {time.time()-t1:.1f}s, svg {None if svg is None else len(svg)} bytes")
