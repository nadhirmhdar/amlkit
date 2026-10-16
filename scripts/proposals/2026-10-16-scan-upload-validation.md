# HELD proposal 2026-10-16 (lead): identity-document scan validation (mlro-user S1, S2)

Status: HELD for human review. Not applied: it changes route logic and front-end copy.
Master: `01298484a7bfed106e9b2bd3a6238f98a4d2514b`.

## Findings
- **S2 (Low).** `POST /customers/scan-passport` and `/customers/scan-trade-licence`
  (`amlkit/api/app.py:1898-1905`, `1935-1942`) read the whole upload with
  `file.file.read()` and hand it to the OCR extractor. They do not check the type
  or the size. Customer-document upload (`app.py:3848-3850`) calls
  `validation.validate_file_mime` (PDF/PNG/JPEG by magic bytes), and policy upload
  caps files at 10 MB. mlro-user's driver sent HTML, an empty file and a 25 MB file;
  all were accepted (`reports/daily/2026-10-16/mlro-user-evidence/log_scan.json`
  on `routine/2026-10-16-mlro-user`).
- **S1 (Low).** When nothing is read, the endpoint returns 200 with every field
  `null`. `amlkit/web/static/js/app.js:358-362` then shows
  "Scan complete (MRZ not read — fields extracted via OCR fallback have no
  authenticity check)", which says fields were extracted when none were.
  Mitigation: the form stays empty, so the operator can see nothing was filled.

## Proposed diff (sketch)
1. A shared guard in the two scan routes, before `extract_*`:
   ```python
   MAX_SCAN_BYTES = 10 * 1024 * 1024
   content = passport_file.file.read(MAX_SCAN_BYTES + 1)
   if len(content) > MAX_SCAN_BYTES:
       raise HTTPException(status_code=413, detail="File is larger than 10 MB.")
   from ..validation import validate_file_mime
   try:
       validate_file_mime(content, passport_file.filename or "scan.png")
   except ValueError as exc:
       raise HTTPException(status_code=400, detail=str(exc))
   ```
   Same block for `licence_file`.
2. `app.js` passport branch: when no extracted field is non-null, show
   "Nothing could be read from this file. Please enter the details manually."
   in place of "Scan complete ...".

## Before approving, check
- `validate_file_mime` recognises JPEG only by three signatures (`validation.py:13`);
  some phone JPEGs (for example EXIF with `\xff\xd8\xff\xee` or `\xe2`) would be refused.
  Widen the list to the `\xff\xd8\xff` prefix, or accept that loss.
- Tests need the OCR stack (passporteye, tesseract) for the success path; the
  rejection paths do not, so the new tests can run in CI without it.

## Related
The skeptic's 10-16 table: of five input paths, only policy upload has a size cap
(F6 `/feedback`, S2 scans, U3/DOC1 mobile document upload). One shared upload helper
(type, size, safe name) would close S2, U3/DOC1 and the L-43 overwrite together.
F6 has its own proposal: `scripts/proposals/2026-10-16-new-findings.md` on
`routine/2026-10-16-red-team`.
