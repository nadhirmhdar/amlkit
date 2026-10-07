import asyncio, json, pyotp
from playwright.async_api import async_playwright
SECRET = open("/tmp/claude-0/pw7.secret").read().strip()
PAGES = ["/dashboard", "/alerts", "/customers", "/customers/1", "/screen", "/admin", "/admin/rule-config", "/freeze-obligations", "/reports", "/audit"]
JS = """() => {
  const sizes = {}; const small = []; const btn = {};
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const n = walker.currentNode; if (!n.textContent.trim()) continue;
    const el = n.parentElement; const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect(); if (r.width === 0 || r.height === 0) continue;
    const s = parseFloat(cs.fontSize); sizes[s] = (sizes[s] || 0) + 1;
    if (s < 11) small.push([el.tagName, s, n.textContent.trim().slice(0, 30)]);
  }
  document.querySelectorAll('button, a.btn, input[type=submit]').forEach(b => {
    const r = b.getBoundingClientRect(); if (r.width === 0) return; const h = Math.round(r.height); btn[h] = (btn[h] || 0) + 1; });
  return {sizes, small: small.slice(0, 6), nsmall: small.length, btn, overflow: document.documentElement.scrollWidth > window.innerWidth + 1, sw: document.documentElement.scrollWidth, iw: window.innerWidth};
}"""
async def main():
    out = {}
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/opt/pw-browsers/chromium", args=["--no-sandbox"])
        for name, vp in (("phone390", {"width": 390, "height": 844}), ("desktop", {"width": 1280, "height": 800})):
            ctx = await b.new_context(viewport=vp); pg = await ctx.new_page()
            await pg.goto("http://127.0.0.1:8766/login"); await pg.fill("input[name=email]", "layla@mlro-test.local"); await pg.fill("input[name=password]", "a-strong-password-1")
            await pg.click("button[type=submit]"); await pg.wait_for_load_state("networkidle")
            if "/mfa/verify" in pg.url:
                await pg.fill("input[name=code]", pyotp.TOTP(SECRET).now()); await pg.click("button[type=submit]"); await pg.wait_for_load_state("networkidle")
            out[name] = {"login_landed": pg.url}
            for path in PAGES:
                await pg.goto("http://127.0.0.1:8766" + path); await pg.wait_for_load_state("networkidle"); await pg.wait_for_timeout(300)
                try:
                    dismiss = pg.locator("text=Got it").first
                    if await dismiss.is_visible(): await dismiss.click()
                except Exception: pass
                try:
                    ok = pg.locator("text=I Understand").first
                    if await ok.is_visible(): await ok.click()
                except Exception: pass
                res = await pg.evaluate(JS); res["url"] = pg.url
                out[name][path] = res
                if path in ("/admin/rule-config", "/alerts", "/dashboard"):
                    await pg.screenshot(path=f"/tmp/claude-0/p7_{name}_{path.strip('/').replace('/','_')}.png")
            await ctx.close()
        await b.close()
    json.dump(out, open("/tmp/claude-0/pw7.json", "w"), indent=1)
    for n, d in out.items():
        print("==", n, d["login_landed"])
        for k, v in d.items():
            if k == "login_landed": continue
            print(k, "url=" + v["url"].replace("http://127.0.0.1:8766", ""), "overflow=", v["overflow"], v["sw"], v["iw"], "sizes=", dict(sorted(((float(a), c) for a, c in v["sizes"].items()))), "btnH=", v["btn"], "small=", v["nsmall"], v["small"][:2])
asyncio.run(main())
