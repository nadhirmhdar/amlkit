import sys, gc; sys.path.insert(0,__import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__)))); sys.path.insert(0,__import__('os').path.join(sys.path[0],'tests'))
from amlkit.db import connect, upsert_dataset, utcnow
from amlkit.match.engine import screen
from amlkit.names.arabic import blocking_keys, canonical_key
import test_matching as tm

def mk():
    c = connect(":memory:")
    ds = upsert_dataset(c, "test_list", "Synthetic", is_mandatory=True); now = utcnow()
    for sid, schema, caption, aliases, country, dob, gender in tm.WATCHLIST:
        eid = c.execute("""INSERT INTO entities (dataset_id, source_id, schema_type, caption,countries,birth_date,gender,topics,raw,first_seen,last_seen)
          VALUES (?,?,?,?,?,?,?,?,?,?,?)""",(ds,sid,schema,caption,f'["{country}"]',dob,gender,'["sanction"]',"{}",now,now)).lastrowid
        for i,nm in enumerate([caption,*aliases]):
            c.execute("INSERT INTO entity_names (entity_id,name,name_type,canonical_key,script) VALUES (?,?,?,?,?)",(eid,nm,"primary" if i==0 else "alias",canonical_key(nm),"arabic" if i else "latin"))
            for t in blocking_keys(nm): c.execute("INSERT OR IGNORE INTO name_tokens (token,entity_id) VALUES (?,?)",(t,eid))
    c.execute("INSERT INTO organizations (name,slug,status,created_at) VALUES ('t','t','active',?)",(now,)); c.commit()
    return c
c = mk()
def hit(n): 
    r = screen(c, n, org_id=1, persist=False); return ("HIT " if r.hits else "MISS"), round(max([h.score for h in r.hits], default=0),2), r.candidates
tests = {
 "Latin exact": "BILAL ALI AL-WAFI",
 "Latin ZWSP in surname": "BILAL ALI AL-WA​FI",
 "Latin ZWSP in given": "BI​LAL ALI AL-WAFI",
 "Latin soft-hyphen": "BI­LAL ALI AL-WAFI",
 "Latin ZWJ": "BILAL ALI AL-WA‍FI",
 "Latin WORD JOINER": "BILAL ALI AL-WA⁠FI",
 "Latin BOM": "BILAL ALI AL-WA﻿FI",
 "Cyrillic consonant (В,А,Л)": "BILAL ALI AL-ВАЛFI",
 "Cyrillic с in Salehi": "FOAD ЅALEHI",
 "Cyrillic к/т in Mohammad Dawood Muzammil": "MOHAMMAD DAWOOD MUZAMMIL".replace("D","Д"),
 "Arabic exact": "بلال علي الوافي",
 "Arabic presentation forms": "ﺑﻼﻝ ﻋﻠﻲ ﺍﻟﻮﺍﻓﻲ",
 "Arabic presentation forms #2 (PDF copy)": "ﻣﺤﻤﺪ ﺩﺍﻭﺩ ﻣﺰﻣﻞ",
 "Arabic Urdu yeh-barree": "بلال علے الوافے",
 "Arabic noon-ghunna": "ﺑﻼﻝ علي الوافں",
 "Arabic Urdu heh-goal": "فؤاد صالحہ",
 "Arabic ZWNJ": "بلال‌ علي الوافي",
 "Arabic extra tatweel": "بـلال عـلي الـوافي",
 "Arabic Latin mixed": "بلال Ali الوافي",
 "digits-only": "12345",
 "name with FTS quotes": 'BILAL "ALI" AL-WAFI) OR (',
 "very long": "BILAL " * 20000,
}
for k,v in tests.items():
    import time; t=time.time()
    try: print(f"{hit(v)!s:24} {time.time()-t:5.2f}s  {k}")
    except Exception as e: print("CRASH", k, type(e).__name__, e)
