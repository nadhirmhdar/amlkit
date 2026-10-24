# HELD proposal 2026-10-21 (B1 extension, B2) -- not applied, no application code edited
## B1 extension: same fix needed on /api/v1/customers/scan-emirates-id and web POST /customers/scan-passport, /scan-emirates-id, /scan-trade-licence (app.py ~1878-1960). Put the size/pixel cap and decode guard from 2026-10-20 into the shared extractors in amlkit/cases/ocr.py so every caller inherits it.
## B2 web scan routes skip the MIME magic-byte check (app.py:1895-1905)
Mobile calls `validation.validate_file_mime`; the web routes read the upload and hand it straight to the extractor. Call `validate_file_mime(content, filename)` in each web scan route and return 400 on ValueError.
