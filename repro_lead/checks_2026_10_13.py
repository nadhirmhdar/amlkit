"""Lead repro, 2026-10-13: P1, a real DOCX policy can never be uploaded.

The form (policies.html:42-43) and upload_policy (manager.py:2347) accept
.pdf/.docx, but the route first runs validate_file_mime (app.py:3848-3850),
whose allow-list (validation.py:11-15) has no DOCX/zip signature.

Exit 0 when the defect reproduces, 1 when fixed. Run from the repo root:
    PYTHONPATH=. python repro_lead/checks_2026_10_13.py
No network, no database, no app code changed.
"""
from __future__ import annotations

import io
import sys
import zipfile

from amlkit.validation import validate_file_mime


def minimal_docx() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr("word/document.xml",
                   '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                   '<w:body><w:p><w:r><w:t>AML Policy</w:t></w:r></w:p></w:body></w:document>')
    return buf.getvalue()


def main() -> int:
    data = minimal_docx()
    try:
        mime = validate_file_mime(data, "aml-policy.docx")
    except ValueError as exc:
        print(f"P1   real DOCX (magic {data[:4]!r}) rejected by route validator: {str(exc)[:70]} -> reproduces=True")
        return 0
    print(f"P1   real DOCX accepted as {mime} -> reproduces=False (fixed)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
