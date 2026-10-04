"""Build fixtures/seed.db via amlkit.db.connect() -- two tenants with data in
every tenant-scoped area. Idempotent: deletes and rebuilds the file.

Usage: python repro/make_seed.py [out_path]
Markers: every org-A string contains 'ALPHA-', every org-B string 'BRAVO-'.
Writes fixtures/seed_ids.json with the primary keys the repro scripts need.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "fixtures" / "seed.db"
PASSWORD = "a-strong-password-1"
LISTED = "Mohammed Al Testlisted"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        Path(str(OUT) + suffix).unlink(missing_ok=True)
    os.environ["AMLKIT_DB"] = str(OUT)

    from amlkit import auth, notifications
    from amlkit.db import connect, upsert_dataset, utcnow
    from amlkit.cases import manager
    from amlkit.cases.operators import register_organization
    from amlkit.names.arabic import blocking_keys, canonical_key

    conn = connect(OUT)
    now = utcnow()

    ds = upsert_dataset(conn, "test_list", "Test Sanctions List", is_mandatory=True)
    eid = conn.execute(
        """INSERT INTO entities (dataset_id, source_id, schema_type, caption, countries,
           birth_date, gender, topics, programs, raw, first_seen, last_seen)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ds, "T-1", "Person", LISTED, '["ly"]', "1975-03-12", "male",
         '["sanction"]', '["AE-UNSC1373"]', "{}", now, now)).lastrowid
    conn.execute(
        "INSERT INTO entity_names (entity_id, name, name_type, canonical_key, script)"
        " VALUES (?,?,?,?,?)", (eid, LISTED, "primary", canonical_key(LISTED), "latin"))
    for tok in blocking_keys(LISTED):
        conn.execute("INSERT OR IGNORE INTO name_tokens (token, entity_id) VALUES (?,?)", (tok, eid))
    conn.execute("UPDATE datasets SET last_refresh=?, entity_count=1 WHERE id=?", (now, ds))
    conn.commit()

    ids: dict = {}
    for tag, org_name in (("A", "Alpha Firm"), ("B", "Bravo Firm")):
        t = tag
        mark = {"A": "ALPHA", "B": "BRAVO"}[t]
        info = register_organization(conn, org_name, f"{mark}-mlro", f"mlro@{mark.lower()}.ae", PASSWORD)
        org_id = conn.execute("SELECT id FROM organizations WHERE name=?", (org_name,)).fetchone()[0]
        op_id = conn.execute("SELECT id FROM operators WHERE org_id=? AND role='mlro'", (org_id,)).fetchone()[0]
        conn.execute("UPDATE operators SET email_verified_at=? WHERE id=?", (now, op_id))
        off_id = conn.execute(
            "INSERT INTO operators (org_id,name,email,password_hash,role,is_active,email_verified_at,created_at)"
            " VALUES (?,?,?,?,?,1,?,?)",
            (org_id, f"{mark}-officer", f"officer@{mark.lower()}.ae",
             auth.hash_password(PASSWORD), "officer", now, now)).lastrowid
        conn.commit()

        clean = manager.onboard(conn, org_id=org_id, reference=f"{mark}-REF-1",
                                full_name=f"{mark}-SECRET Clean Customer", nationality="AE",
                                actor=f"{mark}-mlro")
        hit = manager.onboard(conn, org_id=org_id, reference=f"{mark}-REF-2",
                              full_name=LISTED, nationality="LY", actor=f"{mark}-mlro")
        cid, hid = clean.customer_id, hit.customer_id
        ubo_id = manager.add_ubo(conn, cid, org_id=org_id, person_name=f"{mark}-UBO Person",
                                 ownership_pct=60, actor=f"{mark}-mlro")
        note_id = manager.add_case_note(conn, cid, org_id, author=f"{mark}-mlro", body=f"{mark}-NOTE secret")
        txn_id, _ = manager.record_transaction(conn, cid, org_id, direction="in", method="cash",
                                               amount=75000, counterparty_name=f"{mark}-CPTY",
                                               actor=f"{mark}-mlro")
        doc_id = conn.execute(
            "INSERT INTO documents (org_id,customer_id,doc_type,filename,stored_path,sha256,uploaded_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (org_id, cid, "passport", f"{mark}-passport.pdf", f"{mark.lower()}/passport.pdf", "0" * 64, now)).lastrowid
        dl_id = conn.execute(
            "INSERT INTO compliance_deadlines (org_id,title,due_date,created_at) VALUES (?,?,?,?)",
            (org_id, f"{mark}-DEADLINE", "2030-01-01", now)).lastrowid
        alert = conn.execute("SELECT id FROM alerts WHERE org_id=? ORDER BY id LIMIT 1", (org_id,)).fetchone()
        alert_id = alert[0] if alert else None
        freeze_id = manager.create_freeze_obligation(
            conn, org_id, hid, alert_id=alert_id, obligation_type="sanctions",
            risk_category="high", identified_by=f"{mark}-mlro", notes=f"{mark}-FREEZE")
        conn.execute(
            "INSERT INTO notifications (org_id, operator_id, kind, title, body, link, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (org_id, op_id, "match", f"{mark}-NOTIF", "x", f"/customers/{cid}", now))
        notif_id = conn.execute("SELECT max(id) FROM notifications").fetchone()[0]
        # second sanctions hit, staged for second review by the officer (four-eyes state)
        hit2 = manager.onboard(conn, org_id=org_id, reference=f"{mark}-REF-3", full_name=LISTED,
                               nationality="LY", actor=f"{mark}-mlro")
        pend = conn.execute(
            "SELECT a.id FROM alerts a JOIN screenings s ON s.id=a.screening_id"
            " WHERE a.org_id=? AND s.customer_id=?", (org_id, hit2.customer_id)).fetchone()[0]
        from amlkit.cases.review import propose_disposition
        propose_disposition(conn, pend, org_id=org_id, status="false_positive",
                            reason_code="name_coincidence", operator=f"{mark}-officer")
        scr = conn.execute(
            "INSERT INTO adverse_media_screenings (org_id,customer_id,query_name,trigger,window_months,status,"
            "findings,severity,run_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (org_id, cid, f"{mark}-SECRET Clean Customer", "adhoc", 24, "ok", 1, "low", now)).lastrowid
        finding_id = conn.execute(
            "INSERT INTO adverse_media_findings (org_id,screening_id,customer_id,url,title,severity,"
            "matched_terms,status,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (org_id, scr, cid, f"https://x.test/{mark}", f"{mark}-HEADLINE", "low", "[]", "open", now)).lastrowid
        from amlkit.cases.reports import save_report
        rep = save_report(conn, org_id, f"{mark}-mlro", cid, "STR", f"{mark} Firm", f"{mark}-ENT",
                          f"{mark}-mlro", f"mlro@{mark.lower()}.ae", f"{mark}-FIRST",
                          reason_description=f"{mark}-REASON secret")
        assert rep.success, rep.error
        pol_id, _ = manager.upload_policy(conn, org_id, title=f"{mark}-POLICY", category="AML_Policy",
                                          filename=f"{mark}-policy.pdf", file_content=f"{mark}-POLICY BODY".encode(),
                                          uploaded_by=f"{mark}-mlro")
        conn.commit()
        ids[t] = dict(pending_alert_id=pend, finding_id=finding_id, report_id=rep.report_id,
                      policy_id=pol_id, hit2_customer_id=hit2.customer_id, org_id=org_id, mlro_id=op_id, officer_id=off_id, customer_id=cid,
                      hit_customer_id=hid, ubo_id=ubo_id, note_id=note_id, txn_id=txn_id,
                      doc_id=doc_id, deadline_id=dl_id, alert_id=alert_id, freeze_id=freeze_id,
                      notif_id=notif_id, mlro_email=f"mlro@{mark.lower()}.ae",
                      officer_email=f"officer@{mark.lower()}.ae", marker=mark)
    conn.close()
    (OUT.parent / "seed_ids.json").write_text(json.dumps(ids, indent=2))
    print(json.dumps(ids, indent=2))


if __name__ == "__main__":
    main()
