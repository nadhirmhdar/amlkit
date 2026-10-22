import sys; sys.path.insert(0,__import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))
from amlkit.names.arabic import canonical_key, canonical_tokens
from amlkit.match.scorer import name_score
base = "Mohammed bin Rashid Al Maktoum"
cases = {
 "baseline": base,
 "zwsp inside": "Moham​med bin Rashid Al Maktoum",
 "zwnj inside": "Mohammed bin Ra‌shid Al Maktoum",
 "soft hyphen": "Moham­med bin Rashid Al Maktoum",
 "cyrillic o/a": "Mоhammеd bin Rashid Al Maktoum",
 "greek omicron": "Mοhammed bin Rashid Al Maktoum",
 "fullwidth": "Ｍｏｈａｍｍｅｄ bin Rashid Al Maktoum",
 "digit sub 0": "M0hammed bin Rashid Al Maktoum",
 "spaced": "Mo hammed bin Rashid Al Maktoum",
 "dots": "M.o.h.a.m.m.e.d bin Rashid Al Maktoum",
 "rtl mark": "Mohammed‏ bin Rashid Al Maktoum",
 "nbsp": "Mohammed bin Rashid Al Maktoum",
 "arabic tatweel": "مـحـمد بن راشد آل مكتوم",
 "arabic plain": "محمد بن راشد آل مكتوم",
 "arabic ZWNJ in word": "مح‌مد بن راشد آل مكتوم",
 "arabic ZWSP": "مح​مد بن راشد آل مكتوم",
 "arabic al-prefix tatweel": "الـمكتوم محمد",
 "arabic ya variants": "محمد بن راشد آل مكتومي",
 "arabic hamza": "مُحَمَّد بن رَاشِد آل مَكْتُوم",
 "arabic-indic ligature lam-alef": "ﻻ",
 "persian kaf/ya": "محمد بن راشد آل مکتوم",
 "arabic presentation forms": "ﻣﺤﻤﺪ ﺑﻦ ﺭﺍﺷﺪ ﺁﻝ ﻣﻜﺘﻮﻡ",
 "latin w/ combining": "Mohammed bin Rashid Al Maktouḿ",
 "reordered": "Maktoum Rashid Mohammed",
 "initials": "M. B. R. Al Maktoum",
 "mohd abbreviation": "Mohd B Rashid Maktoum",
}
for k,v in cases.items():
    s,d = name_score(base, v)
    print(f"{s:5.2f}  {k:32s} tokens={canonical_tokens(v)}")
