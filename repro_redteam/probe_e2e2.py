exec(open(__import__('os').path.join(__import__('os').path.dirname(__file__),'probe_e2e.py')).read().split("tests = {")[0])
def h(n, **kw):
    r = screen(c, n, org_id=1, persist=False, **kw); return ("HIT " if r.hits else "MISS"), round(max([x.score for x in r.hits], default=0),2)
# Name padding
for n in ["BILAL ALI AL-WAFI","BILAL ALI AL-WAFI HASSAN","HASSAN BILAL ALI AL-WAFI","BILAL ALI HASSAN AL-WAFI","BILAL ALI AL-WAFI JR","BILAL ALI AL-WAFI TRADING",
          "MOHAMMAD DAWOOD MUZAMMIL","MOHAMMAD DAWOOD MUZAMMIL KHAN","MOHAMMAD DAWOOD MUZAMMIL KHAN SHAH","بلال علي الوافي الاماراتي"]:
    print(h(n), "pad:", n)
print("--- identity-attribute suppression (EXACT name match) ---")
for kw in [{}, {"country":"ae"}, {"country":"pk"}, {"gender":"female"}, {"birth_date":"1980-01-01"},{"birth_date":"1975-03-12"},{"birth_date":"1975-03-13"},{"birth_date":"1975-09-09"},{"birth_date":"1976-03-12"},{"country":"ae","gender":"female"}]:
    print(h("AHMED ABD AL-JALEEL AL-HASNAWI", **({"gender":"male"} if False else {}), **kw), kw)
print("--- organisation ---")
print(h("AL-IHSAN CHARITABLE SOCIETY"), h("AL-IHSAN CHARITABLE SOCIETY", country="ae"), h("AL IHSAN CHARITY"), h("IHSAN CHARITABLE SOCIETY LLC"))
