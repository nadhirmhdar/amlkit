"""Red-team 2026-10-06: regression of F1 (fixed by #425) and bypass attempts against clean_name_text().
LOCAL ONLY (in-memory DB, synthetic watchlist from tests/test_matching.py)."""
exec(open(__import__('os').path.join(__import__('os').path.dirname(__file__),'probe_e2e.py')).read().split("def hit")[0])
from amlkit.cases import manager
def verdict(n):
    r = screen(c, n, org_id=1, persist=False)
    return ("UNSCREENABLE" if r.unscreenable else "HIT " if r.hits else "MISS"), round(max([h.score for h in r.hits], default=0),2)
T = "BILAL ALI AL-WAFI"
cases = {
 "baseline": T,
 "[fixed #425] ZWSP": "BI​LAL ALI AL-WAFI", "[fixed] soft hyphen": "BI­LAL ALI AL-WAFI", "[fixed] BOM": "BI﻿LAL ALI AL-WAFI",
 "[fixed] Arabic presentation forms": "ﺑﻼﻝ ﻋﻠﻲ ﺍﻟﻮﺍﻓﻲ",
 "variation selector VS16 (Mn)": "BI️LAL ALI AL-WAFI",
 "combining grapheme joiner U+034F (Mn)": "BI͏LAL ALI AL-WAFI",
 "C0 control BS (Cc)": "BI\x08LAL ALI AL-WAFI",
 "DEL (Cc)": "BI\x7fLAL ALI AL-WAFI",
 "Braille blank U+2800 (So)": "BI⠀LAL ALI AL-WAFI",
 "Hangul filler U+3164": "BIㅤLAL ALI AL-WAFI",
 "Mongolian vowel sep U+180E": "BI᠎LAL ALI AL-WAFI",
 "ideographic space inside token": "BI　LAL ALI AL-WAFI",
 "private use U+E000 (Co)": "BILAL ALI AL-WAFI",
 "combining dot above U+0307": "BİLAL ALI AL-WAFI",
 "Cyrillic consonant homoglyph (В)": "BILAL ALI AL-ВAFI",
 "Greek consonant homoglyph (Β)": "ΒILAL ALI AL-WAFI",
 "Arabic ext-A mark U+08D3 inside": "بلا࣓ل علي الوافي",
 "Arabic half-mark U+FE20 inside": "بلا︠ل علي الوافي",
 "Arabic Urdu yeh-barree": "بلال علے الوافے",
 "[S3] extra token": "BILAL ALI AL-WAFI HASSAN",
 "[S4] exact name + country mismatch (via kw)": T,
 "Cyrillic-only name": "Иван Петров",
 "Chinese-only name": "王小明",
 "Persian letters only (پچژگ)": "پچژگ",
}
for k, v in cases.items():
    kw = {}
    r = screen(c, v, org_id=1, persist=False, **({"country":"ae"} if "country mismatch" in k else {}))
    print(f"{('UNSCREENABLE' if r.unscreenable else 'HIT ' if r.hits else 'MISS'):12s} {round(max([h.score for h in r.hits], default=0),2):5} cand={r.candidates}  {k}")
print("== downstream handling of an UNSCREENABLE name ==")
c.execute("UPDATE datasets SET last_refresh=?, entity_count=5", (utcnow(),)); c.commit()
res = manager.onboard(c, org_id=1, reference="U-1", full_name="Иван Петров", actor="redteam")
print(" onboard('Иван Петров') ->", type(res).__name__, {k: getattr(res, k, None) for k in ("customer_id","hits","clear","screening_id","unscreenable","risk_rating","message") if hasattr(res,k)})
row = c.execute("select hits, candidates, datasets_used from screenings order by id desc limit 1").fetchone()
print(" persisted screening row:", dict(row) if row else None)
res2 = screen(c, "Иван Петров", org_id=1, persist=True, trigger="onboarding")
print(" persisted screen(): clear =", res2.clear, "| alerts_created =", res2.alerts_created, "| summary:", res2.summary())
from amlkit.match.engine import rescreen_all
print(" rescreen_all:", rescreen_all(c, 1))
