"""Skeptic check of three stdlib behaviours that the app relies on without a guard.
No app code or network involved. Exit 0 only if all three behave as feared.
  1. EmailMessage rejects CR/LF in a header (mail.py builds Subject from a customer reference).
  2. secrets.compare_digest(str, str) raises on non-ASCII (app.py bearer checks at 3934/3998/4037/4084).
  3. ElementTree writes XML-illegal control characters raw (reporting/goaml.py uses ET)."""
import sys, secrets
import xml.etree.ElementTree as ET
from email.message import EmailMessage
ok = 0
try: EmailMessage()["Subject"] = "[URGENT] TFS Freeze Obligation - REF\r\nBcc: x@y"; print("1 accepted")
except ValueError as e: ok += 1; print("1 ValueError:", e)
try: secrets.compare_digest("Bearer é", "Bearer x"); print("2 compared")
except TypeError as e: ok += 1; print("2 TypeError:", e)
e = ET.Element("a"); e.text = "x\x0by"
try: ET.fromstring(ET.tostring(e)); print("3 well-formed")
except ET.ParseError as ex: ok += 1; print("3 ParseError:", ex)
sys.exit(0 if ok == 3 else 1)
