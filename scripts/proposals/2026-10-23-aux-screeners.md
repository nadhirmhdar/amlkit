# HELD: unlinked auxiliary screeners (`kg-screen`, `gdelt-bq`), 2026-10-23

Status: **HELD for Nadhir**. It edits existing route logic (`amlkit/api/app.py`) and a screening module, which the routine may not do.
Master: `0d56f72fb85a296c9882903c9552c13a2210a994`. Repro: `repro_lead/checks_2026_10_23.py` (AX2, AX3, KQ).

## Findings
| id | what | evidence |
|---|---|---|
| L-91 (AX1) | `GET /customers/{id}/kg-screen` (`app.py:2123`) and `GET /customers/{id}/gdelt-bq` (`app.py:2103`) are not linked from any template or JS | `grep -rn "kg-screen\|gdelt-bq"` matches only the route definitions |
| L-92 (AX2) | When unconfigured, both return HTTP 200 with empty results and `status: "unconfigured"` | repro AX2 |
| L-93 (AX3) | When configured, both send the customer's full name out of process (Google KG API over HTTPS; BigQuery SQL under the deployment's project) and write no `audit_log` row. Both are GETs, so they need no CSRF token and link prefetchers can trigger them | repro AX3 |
| L-94 (KQ, new) | `knowledge_graph.py:54` builds the URL as `f"{ENDPOINT}?query={name}&key={key}..."` with no encoding. A name with `&`, `#` or `+` changes the query: `Acme & Co #1` sends `query=Acme ` and drops the `key` parameter into the fragment | repro KQ |

**Production exposure today.** The Cloud Run deploy (`.github/workflows/source-canary.yml:499`, `--set-env-vars`, which replaces the whole list) sets neither `GOOGLE_KG_API_KEY` nor `GOOGLE_CLOUD_PROJECT`. Both screeners are therefore inert in production. I have not checked whether Cloud Run injects `GOOGLE_CLOUD_PROJECT` itself; it is not one of Cloud Run's documented reserved variables. This finding is latent, not live.

**BigQuery cost.** The GDELT query scans `gkg_partitioned` with `V2Persons LIKE '%name%'` across 90 days of partitions, which is a multi-TB scan per call. Once `GOOGLE_CLOUD_PROJECT` is set, any signed-in user can bill that scan with one unlimited GET. This is PLAUSIBLE (I have not measured bytes billed).

## Options (Nadhir decides)
- **(a) Remove** both routes. They have no UI, and adverse media already runs through `screening/adverse_media.py`. This is the smallest change and the recommended one.
- **(b) Keep them and harden.** Diff sketch:

```diff
--- a/amlkit/screening/knowledge_graph.py
+++ b/amlkit/screening/knowledge_graph.py
@@
-        url = f"{ENDPOINT}?query={name}&key={key}&limit=5&languages=en"
-        if types:
-            url += f"&types={','.join(types)}"
-
         try:
-            resp = httpx.get(
-                url,
+            params = {"query": name, "key": key, "limit": 5, "languages": "en"}
+            if types:
+                params["types"] = ",".join(types)
+            resp = httpx.get(
+                ENDPOINT, params=params,
                 headers={"User-Agent": USER_AGENT},
                 timeout=15.0,
             )
--- a/amlkit/api/app.py
+++ b/amlkit/api/app.py
@@
-@app.get("/customers/{customer_id}/gdelt-bq")
+@app.post("/customers/{customer_id}/gdelt-bq")   # + require_csrf, + @limiter.limit("10/minute")
@@
     result = screener.screen(cust["customer"]["full_name"])
+    if result.status == "unconfigured":
+        return JSONResponse(asdict(result), status_code=503)
+    audit(db, session.org_id, session.name, "gdelt_bq_screen", "customer", str(customer_id),
+          json.dumps({"status": result.status}))
+    db.commit()
```

Apply the same shape to `kg-screen`: POST, CSRF, rate limit, 503 when unconfigured, and an audit row on every call. Under (b), also name Google as a processor on the privacy page (folds into L-85/PV1), and set `maximum_bytes_billed` on the BigQuery job config.

Tests to add with the fix: a name containing `&`/`#` round-trips into `params`; an unconfigured call returns 503; a configured call (stubbed) adds one `audit_log` row; a GET returns 405.
