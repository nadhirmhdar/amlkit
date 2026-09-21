"""Tests for amlkit.screening.knowledge_graph — Google KG PEP disambiguation."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import asdict
from unittest.mock import MagicMock, patch

import pytest

from amlkit.screening.knowledge_graph import (
    KgEntity,
    KgResult,
    KnowledgeGraphScreener,
)


MOCK_KG_RESPONSE = {
    "itemListElement": [
        {
            "result": {
                "@type": ["Thing", "Person"],
                "name": "Vijay Mallya",
                "description": "Indian businessman",
                "detailedDescription": {
                    "articleBody": "Vijay Mallya is an Indian fugitive businessman...",
                    "url": "https://en.wikipedia.org/wiki/Vijay_Mallya",
                },
                "@id": "kg:/m/04n7gc6",
            },
            "resultScore": 312.5,
        },
        {
            "result": {
                "@type": ["Thing", "Organization"],
                "name": "Mallya Hospital",
                "description": "Hospital in Bangalore",
            },
            "resultScore": 42.0,
        },
    ]
}


class TestSoftFailWhenUnconfigured:
    def test_returns_unconfigured_when_no_api_key(self):
        screener = KnowledgeGraphScreener(api_key=None)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_KG_API_KEY", None)
            result = screener.screen("Vijay Mallya")
        assert result.status == "unconfigured"
        assert result.entities == []

    def test_env_var_used_when_no_constructor_key(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"itemListElement": []}
        mock_resp.raise_for_status = MagicMock()

        with patch.dict(os.environ, {"GOOGLE_KG_API_KEY": "test-key-123"}):
            screener = KnowledgeGraphScreener()
            with patch("httpx.get", return_value=mock_resp) as mock_get:
                result = screener.screen("Nobody")
                mock_get.assert_called_once()
                call_url = mock_get.call_args[0][0]
                assert "key=test-key-123" in call_url or mock_get.call_args[1].get("params", {}).get("key") == "test-key-123"
        assert result.status == "ok"


class TestScreenWithMockedApi:
    def test_parses_entities_correctly(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_KG_RESPONSE
        mock_resp.raise_for_status = MagicMock()

        screener = KnowledgeGraphScreener(api_key="fake-key")
        with patch("httpx.get", return_value=mock_resp):
            result = screener.screen("Vijay Mallya")

        assert result.status == "ok"
        assert len(result.entities) == 2

        person = result.entities[0]
        assert person.name == "Vijay Mallya"
        assert "Person" in person.types
        assert person.description == "Indian businessman"
        assert person.wikipedia_url == "https://en.wikipedia.org/wiki/Vijay_Mallya"
        assert person.score == 312.5

        org = result.entities[1]
        assert org.name == "Mallya Hospital"
        assert "Organization" in org.types
        assert org.wikipedia_url is None

    def test_types_filter_passed_to_api(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"itemListElement": []}
        mock_resp.raise_for_status = MagicMock()

        screener = KnowledgeGraphScreener(api_key="fake-key")
        with patch("httpx.get", return_value=mock_resp) as mock_get:
            screener.screen("Vijay Mallya", types=["Person"])
            args, kwargs = mock_get.call_args
            url = args[0]
            assert "types=Person" in url

    def test_network_error_returns_unavailable(self):
        screener = KnowledgeGraphScreener(api_key="fake-key")
        with patch("httpx.get", side_effect=Exception("connection refused")):
            result = screener.screen("Vijay Mallya")
        assert result.status == "unavailable"
        assert result.entities == []

    def test_http_4xx_returns_unavailable(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.raise_for_status.side_effect = Exception("403 Forbidden")

        screener = KnowledgeGraphScreener(api_key="fake-key")
        with patch("httpx.get", return_value=mock_resp):
            result = screener.screen("Vijay Mallya")
        assert result.status == "unavailable"

    def test_kg_entity_wikidata_id_extracted(self):
        resp_data = {
            "itemListElement": [
                {
                    "result": {
                        "@type": ["Thing", "Person"],
                        "name": "Test Person",
                        "@id": "kg:/m/012345",
                    },
                    "resultScore": 100.0,
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = resp_data
        mock_resp.raise_for_status = MagicMock()

        screener = KnowledgeGraphScreener(api_key="fake-key")
        with patch("httpx.get", return_value=mock_resp):
            result = screener.screen("Test Person")
        assert result.entities[0].kg_id == "kg:/m/012345"

    def test_result_is_serializable(self):
        screener = KnowledgeGraphScreener(api_key="fake-key")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_KG_RESPONSE
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_resp):
            result = screener.screen("Vijay Mallya")
        d = asdict(result)
        assert isinstance(d, dict)
        assert d["status"] == "ok"
        assert len(d["entities"]) == 2


class TestKgScreenRoute:
    """Integration test for GET /customers/{id}/kg-screen."""

    @pytest.fixture()
    def client(self, tmp_path, monkeypatch):
        from amlkit.db import connect, upsert_dataset, utcnow
        from amlkit.names.arabic import blocking_keys, canonical_key

        db_file = tmp_path / "test.db"
        monkeypatch.setenv("AMLKIT_DB", str(db_file))
        monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)

        conn = connect(db_file)
        ds = upsert_dataset(conn, "test_list", "Test List", is_mandatory=True)
        now = utcnow()
        cur = conn.execute(
            """INSERT INTO entities (dataset_id, source_id, schema_type, caption,
               countries, birth_date, gender, topics, programs, raw, first_seen, last_seen)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ds, "T-1", "Person", "John Doe", '["ae"]', "1980-01-01", "male",
             '["sanction"]', '["TEST"]', "{}", now, now),
        )
        eid = cur.lastrowid
        conn.execute(
            "INSERT INTO entity_names (entity_id, name, name_type, canonical_key, script)"
            " VALUES (?,?,?,?,?)",
            (eid, "John Doe", "primary", canonical_key("John Doe"), "latin"),
        )
        for tok in blocking_keys("John Doe"):
            conn.execute(
                "INSERT OR IGNORE INTO name_tokens (token, entity_id) VALUES (?,?)",
                (tok, eid),
            )
        conn.execute(
            "UPDATE datasets SET last_refresh=?, entity_count=1 WHERE id=?",
            (now, ds),
        )
        conn.commit()
        conn.close()

        from fastapi.testclient import TestClient
        from amlkit.api.app import app
        import re

        c = TestClient(app)
        c.get("/register-organization")
        r = c.post("/register-organization", data={
            "org_name": "KG Test Firm", "name": "tester",
            "email": "tester@kgtest.ae", "password": "a-strong-password-1",
            "csrf_token": c.cookies.get("amlkit_csrf"),
        }, follow_redirects=True)
        m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r.text)
        assert m, "no dev verification link"
        c.get(f"/verify-email?token={m.group(1)}", follow_redirects=True)
        from conftest import settle_mfa  # p15: MLRO sessions start locked
        settle_mfa(c)
        return c

    def _first_customer_id(self) -> int:
        conn = sqlite3.connect(os.environ["AMLKIT_DB"])
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT id FROM customers ORDER BY id LIMIT 1").fetchone()
        conn.close()
        if row:
            return row["id"]
        return -1

    def _onboard_customer(self, client) -> int:
        client.get("/customers/new")
        client.post("/customers", data={
            "reference": "KG-TEST-001",
            "full_name": "Vijay Mallya Test",
            "customer_type": "natural",
            "nationality": "IN",
            "csrf_token": client.cookies.get("amlkit_csrf"),
        }, follow_redirects=True)
        return self._first_customer_id()

    def test_route_returns_json(self, client):
        cid = self._onboard_customer(client)
        assert cid > 0
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_KG_API_KEY", None)
            r = client.get(f"/customers/{cid}/kg-screen")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "unconfigured"

    def test_route_404_cross_org(self, client):
        r = client.get("/customers/999999/kg-screen")
        assert r.status_code == 404
