"""Skeptic repro: a genuine DOCX (zip, starts with 'PK\\x03\\x04') can never pass validate_file_mime, which every policy
upload runs (app.py:3848-3850), although the form (policies.html:42-43) and upload_policy (manager.py:2347) accept DOCX.
Builds a real minimal DOCX with the stdlib. Exit 0 only if the DOCX is rejected."""
import sys, os, io, zipfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from amlkit.validation import validate_file_mime
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
    z.writestr("word/document.xml", "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'/>")
data = buf.getvalue(); print("magic:", data[:4])
try: validate_file_mime(data, "aml-policy.docx"); print("accepted"); sys.exit(1)
except ValueError as e: print("rejected:", str(e)[:80]); sys.exit(0)
