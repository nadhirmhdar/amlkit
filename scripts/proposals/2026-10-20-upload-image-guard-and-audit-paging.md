# HELD proposal 2026-10-20 (lead): L-82 scan-upload guard, L-83 page clamp, L-84/L-85 copy

Not applied: these touch route logic and a template. Repro: `repro_lead/checks_2026_10_20.py`
(exits 0 on master `0129848` while the defects exist). Builds on red-team's
`scripts/proposals/2026-10-20-new-findings.md` (branch `routine/2026-10-20-red-team`).

## 1. L-82 (B1) one shared guard for every image/document scan route

Routes reached today with no byte cap, no pixel cap and no rate limit:
`app.py:1878` `/customers/scan-passport` (and the legal-person and trade-licence
variants below it), `mobile.py:676` `/api/v1/customers/scan-passport`,
`mobile.py:691` `/api/v1/customers/scan-emirates-id`. The web passport route
also skips `validate_file_mime` entirely (it calls `extract_passport_data`
straight after `file.read()`).

Two corrections to the red-team proposal:
- `extract_passport_data` first calls passporteye `read_mrz`, which decodes via
  `skimage.io.imread(..., plugin='imageio')`, not via our own `Image.open`.
  Setting `Image.MAX_IMAGE_PIXELS` alone is not a reliable guard for that path
  (and Pillow only *errors* at 2x the limit). Check dimensions ourselves,
  with a header-only `Image.open(...).size`, before any extractor runs.
- Put it in one helper so every upload route uses it (skeptic's "family" point;
  same helper can later serve DOC1/U3/L-64).

Proposed helper (new function in `amlkit/validation.py`):

```python
MAX_SCAN_BYTES = 10 * 1024 * 1024          # 10 MB
MAX_SCAN_PIXELS = 40_000_000               # ~ 8000 x 5000, far above any phone photo

def read_scan_upload(upload, default_name: str) -> bytes:
    """Read an uploaded scan with a hard byte cap and a header-only pixel check.

    Raises ValueError (callers map it to 400/413) before any decoder runs.
    """
    content = upload.file.read(MAX_SCAN_BYTES + 1)
    if len(content) > MAX_SCAN_BYTES:
        raise ValueError("File is too large (10 MB maximum).")
    kind = validate_file_mime(content, upload.filename or default_name)
    if kind != "application/pdf":
        import io
        from PIL import Image
        try:
            with Image.open(io.BytesIO(content)) as im:   # reads the header only
                w, h = im.size
        except Exception:
            raise ValueError("The image could not be read.")
        if w * h > MAX_SCAN_PIXELS:
            raise ValueError("Image dimensions are too large.")
    return content
```

Route change (each scan route, web and mobile):

```diff
-    content = passport_file.file.read()
-    # Validate MIME type
-    try:
-        validate_file_mime(content, passport_file.filename or "passport.jpg")
-    except ValueError as exc:
-        raise HTTPException(status_code=400, detail=str(exc))
+    try:
+        content = read_scan_upload(passport_file, "passport.jpg")
+    except ValueError as exc:
+        raise HTTPException(status_code=400, detail=str(exc))
```

plus `@limiter.limit("10/minute")` on the web routes (mobile has no limiter
key today; see L-78 for the same gap). The PDF path (`_pdf_first_page_to_image_bytes`,
300 dpi) needs the same pixel check after rendering; a huge page size in a PDF
is the PDF variant of this bomb (not probed).

Tests to add with the fix: a 9000x9000 PNG and an 11 MB body each get 400/413
on all three routes, and a normal 800x600 PNG still returns 200.

## 2. L-83 (AU1/AU2) clamp `page` on `/audit` and `/feedback`

`app.py:3048` `audit_view` and `app.py:2982` `feedback_view` compute
`offset = (page - 1) * per_page` from an unbounded int; SQLite rejects values
above 2^63-1 (`OverflowError` -> 500), and `page<=0` gives a negative offset.

```diff
-def audit_view(request: Request, db: DB, page: int = 1):
+def audit_view(request: Request, db: DB, page: Annotated[int, Query(ge=1, le=100_000)] = 1):
```

Same for `feedback_view`. Out-of-range then becomes FastAPI's 422; if a friendly
page is preferred, clamp instead: `page = max(1, min(page, 100_000))`.

## 3. L-84 (AU3) consistent denial on `/audit/export` and `/feedback/export`

Both return a bare `Response(status_code=403)` while the HTML views use
`back("/", err=...)`. Either redirect the same way, or keep 403 with a short
text body ("Only the MLRO can export the audit log."). Copy only.

## 4. L-85 (PV1) privacy page cookie list

`web/templates/privacy.html:19` says "groAML sets three cookies". Add rows for
`amlkit_trusted_device` (set only when an MLRO ticks "remember this device";
HttpOnly; 30 days; holds a random token, revocable) and `amlkit_uaepass_state`
(set only during a UAE PASS sign-in or verification; HttpOnly; minutes; one-time
OAuth state), and change "three" to "up to five". Both are strictly necessary,
so no consent change is needed. Wording should be checked by Nadhir before it
ships, since it is a published data-protection statement.
