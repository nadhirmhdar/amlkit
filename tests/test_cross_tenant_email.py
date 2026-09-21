"""Issue #138: Cross-tenant MLRO email disclosure in sanctions staleness alerts.

check_and_notify_staleness() collects MLRO emails from ALL orgs into a single
recipient list, so every MLRO can see every other org's MLRO email address in
the To: header. This is a cross-tenant data leak.

Fix: send one alert per org so no MLRO ever sees another org's email.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.db import connect, upsert_dataset, utcnow  # noqa: E402
from amlkit.auth import hash_password  # noqa: E402
from amlkit.names.arabic import blocking_keys, canonical_key  # noqa: E402


@pytest.fixture()
def conn():
    c = connect(":memory:")
    ds = upsert_dataset(c, "test_list", "Test Sanctions List", is_mandatory=True)
    now = utcnow()
    c.execute("UPDATE datasets SET last_refresh=?, entity_count=1 WHERE id=?", (now, ds))
    cur = c.execute(
        """INSERT INTO entities (dataset_id, source_id, schema_type, caption,
           countries, birth_date, gender, topics, raw, first_seen, last_seen)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (ds, "SYN-1", "Person", "JOHN DOE", '["us"]', "1990-01-01", "male",
         '["sanction"]', "{}", now, now),
    )
    eid = cur.lastrowid
    c.execute(
        "INSERT INTO entity_names (entity_id, name, name_type, canonical_key, script)"
        " VALUES (?,?,?,?,?)",
        (eid, "JOHN DOE", "primary", canonical_key("JOHN DOE"), "latin"),
    )
    for tok in blocking_keys("JOHN DOE"):
        c.execute("INSERT OR IGNORE INTO name_tokens (token, entity_id) VALUES (?,?)", (tok, eid))
    c.commit()
    yield c
    c.close()


def _create_org_with_mlro(conn, org_name, slug, mlro_email):
    now = utcnow()
    row = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?) RETURNING id",
        (org_name, slug, "active", now),
    ).fetchone()
    org_id = row["id"]
    conn.execute(
        """INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at)
           VALUES (?,?,?,?,?,1,?)""",
        (org_id, "mlro", mlro_email, hash_password("test-password-1"), "mlro", now),
    )
    conn.commit()
    return org_id


def _make_dataset_stale(conn, key="test_list"):
    conn.execute(
        "UPDATE datasets SET last_refresh=datetime('now', '-48 hours'),"
        " staleness_notified_at=NULL WHERE key=?",
        (key,),
    )
    conn.commit()


class TestCrossTenantEmailIsolation:
    def test_staleness_alert_sent_per_org_not_globally(self, conn) -> None:
        """Each org's MLRO must receive a separate email, not one shared blast."""
        _create_org_with_mlro(conn, "Firm A", "firm-a", "mlro-a@firma.ae")
        _create_org_with_mlro(conn, "Firm B", "firm-b", "mlro-b@firmb.ae")
        _make_dataset_stale(conn)

        from amlkit.cases.scheduler import check_and_notify_staleness

        with patch("amlkit.mail.send_staleness_alert") as mock_send:
            mock_send.return_value = "SENT"
            check_and_notify_staleness(conn)

            assert mock_send.call_count >= 2, (
                f"Expected at least 2 calls (one per org), got {mock_send.call_count}. "
                "A single call with all emails is a cross-tenant leak."
            )

            all_recipients = []
            for call in mock_send.call_args_list:
                recipients = call[0][0]
                all_recipients.append(set(recipients))
                assert len(recipients) <= 1 or all(
                    r.endswith(recipients[0].split("@")[1]) for r in recipients
                ), f"Recipients from different orgs in one email: {recipients}"

    def test_single_org_still_notified(self, conn) -> None:
        """With only one org, staleness alert still works."""
        _create_org_with_mlro(conn, "Solo Firm", "solo-firm", "mlro@solo.ae")
        _make_dataset_stale(conn)

        from amlkit.cases.scheduler import check_and_notify_staleness

        with patch("amlkit.mail.send_staleness_alert") as mock_send:
            mock_send.return_value = "SENT"
            result = check_and_notify_staleness(conn)
            assert result["notified"] > 0
            mock_send.assert_called_once()
            recipients = mock_send.call_args[0][0]
            assert recipients == ["mlro@solo.ae"]
