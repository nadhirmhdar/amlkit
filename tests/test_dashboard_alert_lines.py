"""Dashboard 'Alerts by category': one line per category, one dot per alert.

Integration tests against a real SQLite database and the real app.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3

import pytest
from conftest import register_org


def _db():
    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    conn.row_factory = sqlite3.Row
    return conn


def _seed_alerts(specs):
    """specs: [(topics, status, listed_name[, screened_name])] -> one entity,
    screening and alert each. The screened name differs from the listed one so
    tests can tell the subject of the screen from the person it matched."""
    from amlkit.db import upsert_dataset, utcnow
    conn = _db()
    org_id = conn.execute("SELECT id FROM organizations ORDER BY id LIMIT 1").fetchone()["id"]
    ds = upsert_dataset(conn, "dash_list", "Dash List", is_mandatory=True)
    now = utcnow()
    for i, spec in enumerate(specs):
        topics, status, name = spec[:3]
        screened = spec[3] if len(spec) > 3 else name
        eid = conn.execute(
            """INSERT INTO entities (dataset_id, source_id, schema_type, caption, countries,
               birth_date, gender, topics, programs, raw, first_seen, last_seen)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ds, f"D-{i}-{os.urandom(3).hex()}", "Person", name, '["ae"]', "1980-01-01", "male",
             json.dumps(topics), "[]", "{}", now, now),
        ).lastrowid
        sid = conn.execute(
            """INSERT INTO screenings (org_id, query_name, trigger, algorithm, threshold, run_at)
               VALUES (?,?,?,?,?,?)""",
            (org_id, screened, "adhoc", "jaro_winkler", 0.8, now),
        ).lastrowid
        conn.execute(
            """INSERT INTO alerts (org_id, screening_id, entity_id, score, score_detail,
               matched_name, status, created_at) VALUES (?,?,?,?,?,?,?,?)""",
            (org_id, sid, eid, 0.9 - i * 0.01, "{}", name, status, now),
        )
    conn.execute("UPDATE datasets SET last_refresh=?, entity_count=? WHERE id=?",
                 (now, len(specs), ds))
    conn.commit()
    conn.close()


@pytest.fixture()
def mlro(tmp_path, monkeypatch):
    monkeypatch.setenv("AMLKIT_DB", str(tmp_path / "t.db"))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    c = TestClient(app)
    register_org(c, "Lines Firm", "lines_mlro", "mlro@lines.ae")
    return c


def _line_count(html: str, key: str) -> int:
    m = re.search(rf'cat-line--{key}[ "].*?cat-line__n">(\d+)<', html, re.S)
    assert m, f"no line for {key}"
    return int(m.group(1))


def test_empty_queue_states_what_is_waiting_never_all_clear(mlro):
    html = mlro.get("/dashboard").text
    assert "Queue empty" in html
    assert "All clear" not in html and "all clear" not in html
    assert _line_count(html, "sanction") == 0
    assert "Open the queue" not in html


def test_alerts_are_grouped_by_category(mlro):
    _seed_alerts([(["sanction"], "open", "Sample A"), (["sanction"], "open", "Sample B"),
                  (["role.pep"], "open", "Sample C")])
    html = mlro.get("/dashboard").text
    assert _line_count(html, "sanction") == 2
    assert _line_count(html, "pep") == 1
    assert _line_count(html, "terrorism") == 0
    assert html.count('class="cat-dot') == 3
    assert "Open the queue" in html
    # Adverse media has its own line, but with nothing open it is a zero row and
    # adds no dots and does not change the alert queue count.
    assert _line_count(html, "adverse") == 0
    assert "adverse media finding" not in html


def test_staged_alerts_are_not_counted_as_waiting_for_you(mlro):
    _seed_alerts([(["sanction"], "open", "Sample A"), (["sanction"], "pending_review", "Sample B")])
    html = mlro.get("/dashboard").text
    assert "1 waiting for a decision" in html
    assert "1 awaiting second review" in html
    assert "cat-dot--staged" in html


def test_dots_are_capped_and_the_rest_is_stated(mlro):
    _seed_alerts([(["sanction"], "open", f"Sample {i}") for i in range(15)])
    html = mlro.get("/dashboard").text
    assert _line_count(html, "sanction") == 15
    assert html.count('class="cat-dot') == 12
    assert "+3" in html
    # Rows are capped like the dots, and the rest are one click away.
    assert html.count('data-alert-id="') == 12
    assert "3 more &middot; Open all Sanctions alerts in the queue" in html and "/alerts?category=sanction" in html


def test_row_subject_is_the_screened_party_not_the_listed_person(mlro):
    _seed_alerts([(["sanction"], "open", "Listed Person X", "Acme Trading LLC")])
    html = mlro.get("/dashboard").text
    primary = re.search(r'<div class="primary">(.*?)</div>', html, re.S).group(1).strip()
    assert primary == "Acme Trading LLC"
    assert "matched Listed Person X" in html


def test_zero_lines_are_plain_rows_not_disclosures(mlro):
    _seed_alerts([(["sanction"], "open", "Sample A")])
    html = mlro.get("/dashboard").text
    assert html.count("<details class=\"cat-line") == 1
    assert "cat-line--terrorism cat-line--zero" in html


def test_greeting_uses_uae_time_not_utc():
    from datetime import datetime, timezone
    from amlkit.queries import dubai_greeting
    # 22:30 UTC on 1 Oct is already 02:30 on Fri 2 Oct in the UAE.
    g = dubai_greeting(datetime(2026, 10, 1, 22, 30, tzinfo=timezone.utc))
    assert g == {"period": "morning", "date": "Friday · 2 October 2026"}
    # 10:00 UTC is 14:00 UAE: afternoon, where a UTC clock would say morning.
    assert dubai_greeting(datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc))["period"] == "afternoon"
    assert dubai_greeting(datetime(2026, 10, 1, 16, 0, tzinfo=timezone.utc))["period"] == "evening"


def test_rows_are_oldest_first_and_show_waiting_time(mlro):
    _seed_alerts([(["sanction"], "open", "Listed One", "Subject One"),
                  (["sanction"], "open", "Listed Two", "Subject Two"),
                  (["sanction"], "open", "Listed Three", "Subject Three")])
    conn = _db()
    for i, name in enumerate(["Subject One", "Subject Two", "Subject Three"]):
        conn.execute("UPDATE alerts SET created_at=? WHERE screening_id=(SELECT id FROM screenings WHERE query_name=?)",
                     (f"2026-09-{20 + i:02d}T08:00:00+00:00", name))
    conn.commit(); conn.close()
    html = mlro.get("/dashboard").text
    order = re.findall(r'<div class="primary">(Subject \w+)</div>', html)
    assert order == ["Subject One", "Subject Two", "Subject Three"]
    assert re.search(r"opened \d+ d ago", html)


def test_alert_lines_waiting_helper_hours_and_days():
    from datetime import datetime, timezone
    from amlkit.queries import _waiting
    now = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    assert _waiting("2026-10-01T11:40:00+00:00", now) == "under 1 h"
    assert _waiting("2026-10-01T09:00:00+00:00", now) == "3 h"
    assert _waiting("2026-09-28T12:00:00+00:00", now) == "3 d"


def test_mobile_dashboard_payload_does_not_carry_web_only_lines():
    """The mobile API returns queries.dashboard() whole; the per-category
    lines are web-only and would duplicate every open alert in that payload."""
    from amlkit import queries
    from amlkit.db import connect, utcnow
    conn = connect(":memory:")
    org_id = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?) RETURNING id",
        ("Mobile Firm", "mobile-firm", "active", utcnow())).fetchone()["id"]
    payload = queries.dashboard(conn, org_id)
    assert "alert_lines" not in payload and "greeting" not in payload


def test_each_category_line_has_a_text_summary_for_screen_readers(mlro):
    _seed_alerts([(["sanction"], "open", "A"), (["sanction"], "pending_review", "B")])
    html = mlro.get("/dashboard").text
    assert "alerts, 1 awaiting second review" in html


def test_a_queue_over_the_cap_keeps_the_oldest_and_says_so(mlro):
    _seed_alerts([(["sanction"], "open", f"Listed {i}", f"Subject {i:03d}") for i in range(205)])
    conn = _db()
    # Subject 204 is the oldest alert and has the lowest score.
    for i in range(205):
        conn.execute("UPDATE alerts SET created_at=? WHERE screening_id=(SELECT id FROM screenings WHERE query_name=?)",
                     (f"2026-08-{1 + (204 - i) // 24:02d}T{(204 - i) % 24:02d}:00:00+00:00", f"Subject {i:03d}"))
    conn.commit(); conn.close()
    html = mlro.get("/dashboard").text
    assert "showing the oldest 200" in html
    assert "Subject 204" in html          # the oldest alert is not cut off
    assert "Subject 000" not in html      # the newest is the one left out
    # The numbers are the real queue, not the 200 fetched for the rows.
    assert "205 waiting for a decision" in html
    assert "Open the queue (205)" in html
    assert _line_count(html, "sanction") == 205
    assert "193 more &middot; Open all" in html   # 205 alerts, 12 shown


def test_alert_lines_does_not_mutate_the_dashboard_payload_dicts():
    from amlkit.queries import alert_lines
    alerts = [{"category": "sanction", "created_at": "2026-09-01T00:00:00+00:00", "score": 0.9,
               "status": "open", "query_name": "Q", "customer_name": None, "ubo_name": None}]
    alert_lines(alerts)
    assert "subject" not in alerts[0] and "waiting" not in alerts[0]


def test_status_line_states_the_age_of_the_stalest_list(mlro):
    _seed_alerts([(["sanction"], "open", "Sample A")])
    html = mlro.get("/dashboard").text
    assert "refreshed within the 24-hour window" in html
    assert "oldest under 1 h ago" in html


def test_alert_rows_have_distinct_accessible_names_and_a_labelled_score(mlro):
    _seed_alerts([(["sanction"], "open", "Listed One", "Subject One")])
    html = mlro.get("/dashboard").text
    assert 'aria-label="Open alert details: Subject One, Dash List, unassigned"' in html
    assert 'aria-expanded="false"' in html
    assert "Match score" in html


def test_audit_timestamps_say_which_time_zone_they_are_in(mlro):
    html = mlro.get("/dashboard").text
    assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC", html)


def test_dashboard_payload_counts_are_uncapped_even_when_the_lists_are(mlro):
    """The mobile API returns queries.dashboard() whole, so its counts must be right too."""
    _seed_alerts([(["sanction"], "open", f"L{i}", f"S{i:03d}") for i in range(205)]
                 + [(["role.pep"], "pending_review", "P", "Pep Subject")])
    from amlkit import queries
    conn = _db()
    org_id = conn.execute("SELECT id FROM organizations ORDER BY id LIMIT 1").fetchone()["id"]
    d = queries.dashboard(conn, org_id)
    conn.close()
    assert len(d["open_alerts"]) == 201     # 200 open (capped) + 1 staged: the lists still feed the rows
    assert d["alert_open_total"] == 205 and d["alert_staged_total"] == 1 and d["alert_total"] == 206
    assert d["open_by_category"] == {"sanction": 205, "pep": 1}
    assert d["alert_counts"]["pep"] == {"open": 0, "pending_review": 1}
    assert d["alerts_truncated"] is True


def test_home_banner_uses_the_real_queue_size(mlro):
    _seed_alerts([(["sanction"], "open", f"L{i}", f"S{i:03d}") for i in range(205)])
    html = mlro.get("/").text
    assert "205 alerts need your action" in html


def test_alerts_page_filters_by_category(mlro):
    _seed_alerts([(["sanction"], "open", "Sanc One"), (["sanction"], "open", "Sanc Two"),
                  (["role.pep"], "open", "Pep One")])
    everything = mlro.get("/alerts").text
    assert "Sanc One" in everything and "Pep One" in everything
    only = mlro.get("/alerts?category=pep").text
    assert "Pep One" in only and "Sanc One" not in only
    assert "Showing <strong>PEP</strong> alerts only" in only
    # The filter survives switching tab or view.
    assert "status=pending_review&amp;category=pep" in only
    assert "group_by=customer&amp;category=pep" in only


def test_alerts_category_filter_ignores_unknown_values(mlro):
    _seed_alerts([(["sanction"], "open", "Sanc One")])
    html = mlro.get("/alerts?category=bogus").text
    assert "Sanc One" in html and "alerts only" not in html


def test_category_filter_is_not_capped_by_the_sql_limit(mlro):
    from amlkit import queries
    _seed_alerts([(["role.pep"], "open", f"Pep {i}") for i in range(3)]
                 + [(["sanction"], "open", f"Sanc {i}") for i in range(5)])
    conn = _db()
    org_id = conn.execute("SELECT id FROM organizations ORDER BY id LIMIT 1").fetchone()["id"]
    got = queries.alert_queue(conn, org_id, status="open", limit=4, category="pep")
    conn.close()
    assert len(got) == 3 and {a["category"] for a in got} == {"pep"}


def test_alerts_csv_export_honours_the_category_filter(mlro):
    _seed_alerts([(["sanction"], "open", "Sanc One"), (["role.pep"], "open", "Pep One")])
    everything = mlro.get("/alerts.csv?status=open").text
    assert "Sanc One" in everything and "Pep One" in everything
    only = mlro.get("/alerts.csv?status=open&category=pep").text
    assert "Pep One" in only and "Sanc One" not in only
    page = mlro.get("/alerts?category=pep").text
    assert "/alerts.csv?status=open&amp;category=pep" in page


def _seed_adverse(specs):
    """specs: [(customer_name, severity, status)] -> customers with one finding each."""
    from amlkit.db import utcnow
    conn = _db()
    org_id = conn.execute("SELECT id FROM organizations ORDER BY id LIMIT 1").fetchone()["id"]
    now = utcnow()
    ids = []
    for i, (name, severity, status) in enumerate(specs):
        cid = conn.execute(
            "INSERT INTO customers (org_id, reference, customer_type, full_name, canonical_key, "
            "onboarded_at, created_at, updated_at) VALUES (?, ?, 'legal', ?, ?, ?, ?, ?)",
            (org_id, f"AM-{i}", name, name.lower(), now, now, now)).lastrowid
        sid = conn.execute(
            "INSERT INTO adverse_media_screenings (org_id, customer_id, query_name, trigger, window_months, "
            "status, run_at) VALUES (?, ?, ?, 'adhoc', 12, 'ok', ?)", (org_id, cid, name, now)).lastrowid
        conn.execute(
            "INSERT INTO adverse_media_findings (org_id, screening_id, customer_id, url, title, domain, "
            "severity, matched_terms, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, '[]', ?, ?)",
            (org_id, sid, cid, f"https://example.test/{i}", f"Headline {i}", "example.test", severity, status, now))
        ids.append(cid)
    conn.commit()
    conn.close()
    return ids


def test_adverse_media_is_a_category_line_after_pep(mlro):
    cids = _seed_adverse([("Alpha Trading", "financial_crime_alleged", "open"),
                          ("Beta Gold", "regulatory_action", "open"),
                          ("Gamma LLC", "reputational_only", "relevant")])
    html = mlro.get("/dashboard").text
    assert _line_count(html, "adverse") == 2          # only findings still open
    assert html.index("cat-line--pep") < html.index("cat-line--adverse")
    assert "2 adverse media findings to review" in html
    assert f'href="/customers/{cids[0]}#adverse-media"' in html
    # Not alerts: no alert panel hook, and the queue button and its count stay alert-only.
    block = html[html.index("cat-line--adverse"):]
    assert "data-alert-id" not in block.split("</details>")[0]
    assert "Open the queue" not in html
    assert "Queue empty" not in html


def test_adverse_media_does_not_inflate_the_alert_counts(mlro):
    _seed_alerts([(["sanction"], "open", "Sample A")])
    _seed_adverse([("Alpha Trading", "financial_crime_alleged", "open")])
    html = mlro.get("/dashboard").text
    assert "1 waiting for a decision" in html
    assert "1 adverse media finding to review" in html
    assert "Open the queue (1)" in html


def test_customer_page_has_the_adverse_media_anchor(mlro):
    cid = _seed_adverse([("Alpha Trading", "regulatory_action", "open")])[0]
    assert 'id="adverse-media"' in mlro.get(f"/customers/{cid}").text


def test_adverse_media_shows_the_most_serious_findings_first_when_capped(mlro):
    """Thirteen open findings, the newest one the most serious: it must be among
    the twelve shown, and the one that falls into "+1" must be a minor one."""
    specs = [(f"Minor {i}", "reputational_only", "open") for i in range(12)]
    specs.append(("Serious Newest", "financial_crime_alleged", "open"))
    _seed_adverse(specs)
    html = mlro.get("/dashboard").text
    block = html[html.index("cat-line--adverse"):].split("</details>")[0]
    assert _line_count(html, "adverse") == 13
    assert "Serious Newest" in block
    assert block.count('class="cat-dot') == 12
    assert "+1" in block
