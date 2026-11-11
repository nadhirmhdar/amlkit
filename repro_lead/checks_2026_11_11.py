"""Lead repro, 2026-11-11: RP1 (goAML report finalise accepts invalid values)
and RP1g (exporter rewrites any gender other than 'male' as 'F').

Run from the repo root:  PYTHONPATH=. python repro_lead/checks_2026_11_11.py
Temp DB, invite mode, no network. Exit 0 = every defect reproduces;
exit 1 = at least one is fixed.

Goes through the same code the web and mobile routes use:
cases.reports.save_report -> cases.manager.report_finalize_error (the shared
finalise check) -> reporting.goaml.inject_reporting_entity + serialize_goaml_xml.
"""
from __future__ import annotations

import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

tmp = tempfile.mkdtemp()
db_file = Path(tmp) / "lead11.db"
os.environ["AMLKIT_DB"] = str(db_file)
os.environ.pop("AMLKIT_SINGLE_OPERATOR_MODE", None)
os.environ.pop("AMLKIT_SMTP_HOST", None)
os.environ.pop("STRIPE_SECRET_KEY", None)
os.environ["AMLKIT_REGISTRATION_INVITE_CODE"] = "test-invite"

from test_api import _register, _seed_sanctions_data  # noqa: E402

_seed_sanctions_data(db_file)
from fastapi.testclient import TestClient  # noqa: E402
from amlkit.api.app import app, limiter  # noqa: E402

limiter.enabled = False
client = TestClient(app)
_register(client, "Lead Firm", "lead", "lead@leadfirm.ae")

from amlkit.db import connect  # noqa: E402
from amlkit.cases.manager import onboard, report_finalize_error  # noqa: E402
from amlkit.cases.reports import save_report  # noqa: E402
from amlkit.reporting.goaml import inject_reporting_entity, serialize_goaml_xml  # noqa: E402
from amlkit import queries  # noqa: E402

conn = connect(str(db_file))
org_id = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()["id"]
cid = onboard(conn, org_id=org_id, reference="R-1", full_name="Ahmed Al Mansoori",
              customer_type="natural", nationality="AE", actor="lead").customer_id

BASE = dict(report_type="STR", reporting_entity_name="Lead Firm", entity_reference="ENT-1",
            reporter_name="Lead MLRO", reporter_email="lead@leadfirm.ae",
            first_name="Ahmed", last_name="Al Mansoori", nationality="AE",
            birth_date="1980-01-01", gender="male", id_type="passport", id_number="P123",
            amount="1000", transaction_type="cash", transaction_date="2026-11-01",
            source_account="AE070331234567890123456", destination_account="AE070331234567890123457",
            reason_description="Structured cash deposits below threshold.")


def finalise_and_export(**over):
    f = dict(BASE, **over)
    r = save_report(conn, org_id, "lead", cid, f["report_type"], f["reporting_entity_name"],
                    f["entity_reference"], f["reporter_name"], f["reporter_email"],
                    f["first_name"], f["last_name"], f["nationality"], f["birth_date"],
                    f["gender"], f["id_type"], f["id_number"], f["amount"],
                    f["transaction_type"], f["transaction_date"], f["source_account"],
                    f["destination_account"], f["reason_description"], "", "", None)
    if not r.success:
        return "save-refused", r.error, None
    rep = queries.report(conn, r.report_id, org_id)
    problem = report_finalize_error(rep, conn, org_id)
    if problem:
        return "finalise-refused", problem, None
    import json
    payload = json.loads(rep["payload"] or "{}")
    inject_reporting_entity(payload, conn, org_id)
    xml = serialize_goaml_xml(payload)
    return "finalise-accepted", None, ET.fromstring(xml)


results = {}

# RP1: invalid values that onboarding would refuse, one at a time.
RP1_CASES = {
    "birth_date=2999-01-01": dict(birth_date="2999-01-01"),
    "birth_date=not-a-date": dict(birth_date="not-a-date"),
    "transaction_date=2030-01-01": dict(transaction_date="2030-01-01"),
    "nationality=ZZ": dict(nationality="ZZ"),
    "reporter_email=not-an-email": dict(reporter_email="not-an-email"),
    "source_account=12345": dict(source_account="12345"),
}
accepted = 0
for label, over in RP1_CASES.items():
    outcome, err, _ = finalise_and_export(**over)
    print(f"RP1   {label:32s} -> {outcome}{'' if not err else ' (' + err[:60] + ')'}")
    accepted += outcome == "finalise-accepted"
results["RP1"] = accepted == len(RP1_CASES)
print(f"RP1   reproduces={results['RP1']} ({accepted}/{len(RP1_CASES)} invalid values finalise and export)")

# Control: onboarding refuses the same birth date.
try:
    onboard(conn, org_id=org_id, reference="R-2", full_name="Control Person",
            customer_type="natural", nationality="AE", birth_date="2999-01-01", actor="lead")
    print("RP1c  control: onboarding accepted birth_date=2999-01-01 (control has no power)")
except ValueError as exc:
    print(f"RP1c  control: onboarding refuses birth_date=2999-01-01 ({str(exc)[:60]})")

# RP1g: gender mapping. Only 'male' maps to M; every other non-empty value -> F.
rewrites = []
for g in ["male", "female", "M", "other", "unknown", "attack helicopter"]:
    outcome, err, root = finalise_and_export(gender=g)
    el = root.find(".//t_person/gender") if root is not None else None
    if el is None and root is not None:
        el = root.find(".//gender")
    out = el.text if el is not None else None
    print(f"RP1g  gender={g!r:22s} -> {outcome}, exported <gender>={out!r}")
    if g not in ("male", "female") and out == "F":
        rewrites.append(g)
results["RP1g"] = "M" in rewrites and len(rewrites) >= 3
print(f"RP1g  reproduces={results['RP1g']} (rewritten to F: {rewrites})")

conn.close()
n = sum(results.values())
print(f"{n}/{len(results)} reproduce")
sys.exit(0 if n == len(results) else 1)
