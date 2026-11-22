"""EV1 (mlro-user 2026-11-22): the first-login "Important Notice" dialog is
printed over page 1 of the evidence-pack PDF.

Lead repro. Scratch DB only (tmp dir), no network, no production.
Exits 0 when the defect reproduces: the PDF made by an operator who has not
acknowledged the disclaimer contains the dialog text, and the PDF made after
acknowledging does not (which also scopes the defect to the unacknowledged
state, as the skeptic argued).

Run from the repo root:  PYTHONPATH=.:tests python repro_lead/ev1_evidence_pdf_disclaimer_overlay_2026_11_22.py
"""
from __future__ import annotations

import io
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
os.environ.setdefault("AMLKIT_REGISTRATION_INVITE_CODE", "test-invite")
os.environ.pop("AMLKIT_SINGLE_OPERATOR_MODE", None)

tmp = Path(tempfile.mkdtemp(prefix="ev1_"))
db_file = tmp / "ev1.db"
os.environ["AMLKIT_DB"] = str(db_file)

from test_api import _csrf, _register, _seed_sanctions_data  # noqa: E402

_seed_sanctions_data(db_file)

from fastapi.testclient import TestClient  # noqa: E402
from amlkit.api.app import app  # noqa: E402
import pypdfium2 as pdfium  # noqa: E402

NOTICE = "Important Notice"


def page1_text(pdf_bytes: bytes) -> str:
    doc = pdfium.PdfDocument(io.BytesIO(pdf_bytes))
    return doc[0].get_textpage().get_text_range()


c = TestClient(app)
_register(c, "EV1 Firm", "ev1_mlro", "ev1@test.ae")
c.get("/customers/new")
c.post("/customers", data={"reference": "EV1-REF", "full_name": "Fatima Khan",
                           "customer_type": "natural", "nationality": "AE",
                           "csrf_token": _csrf(c)}, follow_redirects=True)
conn = sqlite3.connect(db_file)
cid = conn.execute("SELECT id FROM customers WHERE full_name='Fatima Khan'").fetchone()[0]
acked0 = conn.execute("SELECT disclaimer_acknowledged_at FROM operators").fetchone()[0]
conn.close()

r1 = c.get(f"/customers/{cid}/evidence.pdf")
assert r1.status_code == 200 and r1.content[:4] == b"%PDF", (r1.status_code, r1.text[:200])
t1 = page1_text(r1.content)

r_ack = c.post("/acknowledge-disclaimer", data={"csrf_token": _csrf(c)}, follow_redirects=False)
r2 = c.get(f"/customers/{cid}/evidence.pdf")
assert r2.status_code == 200
t2 = page1_text(r2.content)

before = NOTICE in t1
after = NOTICE in t2
print(f"EV1  operator disclaimer_acknowledged_at before export: {acked0!r}")
print(f"EV1  unacknowledged PDF page 1 contains {NOTICE!r}: {before}")
print(f"EV1  POST /acknowledge-disclaimer -> {r_ack.status_code}")
print(f"EV1  acknowledged PDF page 1 contains {NOTICE!r}: {after}")
print(f"EV1  page 1 text near 'Fatima' (unacked): {t1[max(0, t1.find('Fatima') - 60):t1.find('Fatima') + 40]!r}")
reproduces = before and not after
print("EV1 reproduces (scoped to unacknowledged session)" if reproduces else "EV1 does NOT reproduce")
sys.exit(0 if reproduces else 1)
