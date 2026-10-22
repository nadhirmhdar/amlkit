# Proposal (HELD): noindex on signed-in pages, Disallow private paths, configurable canonical host

Status: HELD for Nadhir. Not applied: it edits existing templates and a route (`robots_txt`), which the lead routine may not do.
Master: `0d56f72` (#427). Repro: `repro_lead/checks_2026_10_22.py` (SE1, HC both reproduce).

## L-88 (LOW): signed-in pages are indexable in principle
`customer.html:5` puts `c.full_name` in `<title>`. Since #427, `base.html:9,16` also adds a canonical and `og:url` to every page,
signed-in ones included. No signed-in page sends `<meta name="robots">` or `X-Robots-Tag`, and `robots.txt` (`app.py:2921`) is
`Allow: /`. A crawler normally sees only the login redirect, so this needs a cached or shared authenticated response or a link-preview bot to leak.
It is defence in depth, not an open leak.

Proposed diff (sketch):

```diff
--- a/amlkit/web/templates/base.html
+++ b/amlkit/web/templates/base.html
-{% block robots %}{% endblock %}
+{% block robots %}{% if operator is defined and operator %}<meta name="robots" content="noindex, nofollow">{% endif %}{% endblock %}
```
Check the variable name that `base.html` already uses to detect a signed-in operator, and use that one.
Alternative: a middleware that sets `X-Robots-Tag: noindex, nofollow` on every response whose session is authenticated. That also covers JSON and CSV exports.

```diff
--- a/amlkit/api/app.py  (robots_txt)
-    body = "User-agent: *\nAllow: /\nSitemap: https://groaml.grovisor.ae/sitemap.xml\n"
+    body = ("User-agent: *\nDisallow: /customers\nDisallow: /audit\nDisallow: /reports\n"
+            "Disallow: /admin\nDisallow: /alerts\nDisallow: /api/\nAllow: /\n"
+            "Sitemap: https://groaml.grovisor.ae/sitemap.xml\n")
```
Note: `Disallow` stops crawling but not indexing of a URL that is linked elsewhere. The noindex header is the real control. Do not rely on `robots.txt` alone.

Test: GET `/customers/{id}` as an MLRO and assert a `noindex` meta tag or header; assert that `/about` has none.

## L-89 (INFO): canonical and og:url host hard-coded
`base.html:9,16,17,21` print `https://groaml.grovisor.ae` whatever the serving host is. A staging or preview deploy therefore declares production as its canonical.
The SEO effect is small, but it should come from config. Proposed: add one `AMLKIT_PUBLIC_BASE_URL` setting (default `https://groaml.grovisor.ae`),
expose it as a Jinja global, and use it in `base.html`, the sitemap and `robots.txt`. If a base-URL setting already exists for the mail links, reuse it.
The mail links currently print `http://127.0.0.1:8000` in dev, so one may exist; check `mail.py` before adding a new variable.

## L-90 (INFO): `/blog?topic=` canonicalises to itself, `/blog?q=` to `/blog`
Both are `noindex`, so this has no search effect. Make both canonicalise to `/blog` when convenient.
